from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from skills.common import get_settings
from skills.video_render.ffmpeg_wrapper import (
    TimelineSegment,
    concat_segments,
    cut_merge_segment,
    probe_duration_ms,
    render_timeline_single_pass,
    transcode_audio_to_wav,
)
from store.minio_client import MinioStore

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None


def split_bucket_object(path: str | None) -> tuple[str, str] | None:
    """分割存储桶和对象路径"""
    if not path or "/" not in path:
        return None
    bucket, object_key = path.split("/", 1)
    return bucket, object_key


class VideoRenderService:
    def __init__(self) -> None:
        settings = get_settings()
        minio_cfg = settings.storage["minio"]
        render_cfg = settings.data.get("video_render", {})
        self.buckets = minio_cfg["buckets"]
        self.pipeline_mode = str(render_cfg.get("pipeline_mode", "single_pass")).strip().lower() or "single_pass"
        self.allow_legacy_fallback = bool(render_cfg.get("allow_legacy_fallback", True))
        self.audio_fit_max_speed = float(render_cfg.get("audio_fit_max_speed", 1.10))
        self.audio_short_pad_ms = int(render_cfg.get("audio_short_pad_ms", 250))
        self.output_fps = int(render_cfg.get("output_fps", 30))
        self.output_sample_rate = int(render_cfg.get("output_sample_rate", 24_000))
        self.minio = MinioStore(
            endpoint=minio_cfg["endpoint"],
            access_key=minio_cfg["access_key"],
            secret_key=minio_cfg["secret_key"],
            secure=minio_cfg.get("secure", False),
        )

    async def render_video(
        self,
        task_id: str,
        source_video_key: str | None,
        source_video_keys: list[str] | None,
        scenes: list[dict[str, Any]],
        sentences: list[dict[str, Any]],
        audio_segments: list[dict[str, Any]],
        voice_profile_fallback: bool | None = None,
    ) -> dict[str, Any]:
        scene_map = {item["scene_id"]: item for item in scenes}
        audio_map = {item["sentence_id"]: item for item in audio_segments}
        normalized_source_keys = self._normalize_video_keys(source_video_key, source_video_keys)
        if not normalized_source_keys:
            return {"error": "empty_source_video_keys"}

        self.minio.ensure_bucket(self.buckets["output"])

        with tempfile.TemporaryDirectory(prefix="evoclip-render-") as tmp:
            tmp_path = Path(tmp)
            source_videos: dict[str, Path] = {}
            for idx, key in enumerate(normalized_source_keys):
                local_video = tmp_path / f"source_{idx}_{Path(key).name}"
                self.minio.download_file(self.buckets["videos"], key, str(local_video))
                source_videos[key] = local_video

            timeline: list[dict[str, Any]] = []
            render_segments: list[TimelineSegment] = []
            legacy_segments: list[dict[str, Any]] = []
            offset_ms = 0
            speedup_count = 0
            trim_count = 0
            pad_count = 0

            for sentence in sentences:
                sentence_id = str(sentence["sentence_id"])
                scene_id = str(sentence["scene_id"])
                scene = scene_map.get(scene_id)
                if not scene:
                    continue

                scene_source_video_key = str(scene.get("source_video_key") or normalized_source_keys[0])
                source_video = source_videos.get(scene_source_video_key)
                if source_video is None:
                    local_video = tmp_path / f"source_extra_{len(source_videos)}_{Path(scene_source_video_key).name}"
                    self.minio.download_file(self.buckets["videos"], scene_source_video_key, str(local_video))
                    source_videos[scene_source_video_key] = local_video
                    source_video = local_video

                audio = audio_map.get(sentence_id)
                if not audio or audio.get("status") == "failed":
                    timeline.append(
                        {
                            "scene_id": scene_id,
                            "sentence_id": sentence_id,
                            "source_video_key": scene_source_video_key,
                            "start_ms": offset_ms,
                            "end_ms": offset_ms,
                            "audio_path": None,
                            "subtitle_text": sentence.get("text", ""),
                            "skipped": True,
                            "target_duration_ms": 0,
                            "raw_audio_duration_ms": 0,
                            "final_audio_duration_ms": 0,
                            "audio_fit_strategy": "none",
                            "speed_factor": 1.0,
                        }
                    )
                    continue

                audio_tuple = split_bucket_object(audio.get("audio_path"))
                if not audio_tuple:
                    timeline.append(
                        {
                            "scene_id": scene_id,
                            "sentence_id": sentence_id,
                            "source_video_key": scene_source_video_key,
                            "start_ms": offset_ms,
                            "end_ms": offset_ms,
                            "audio_path": None,
                            "subtitle_text": sentence.get("text", ""),
                            "skipped": True,
                            "target_duration_ms": 0,
                            "raw_audio_duration_ms": 0,
                            "final_audio_duration_ms": 0,
                            "audio_fit_strategy": "none",
                            "speed_factor": 1.0,
                        }
                    )
                    continue

                audio_bucket, audio_object = audio_tuple
                source_start_ms = int(scene.get("source_start_ms", scene["start_ms"]))
                source_end_ms = int(scene.get("source_end_ms", scene["end_ms"]))
                source_duration_ms = max(source_end_ms - source_start_ms, 1)
                target_duration_ms = source_duration_ms

                local_audio = tmp_path / f"{sentence_id}.mp3"
                self.minio.download_file(audio_bucket, audio_object, str(local_audio))

                try:
                    raw_audio_duration_ms = probe_duration_ms(local_audio)
                except Exception:
                    raw_audio_duration_ms = int(audio.get("duration_ms", target_duration_ms))

                audio_fit_strategy, speed_factor = self._decide_audio_fit(raw_audio_duration_ms, target_duration_ms)
                if audio_fit_strategy == "speedup":
                    speedup_count += 1
                elif audio_fit_strategy == "trim":
                    trim_count += 1
                elif audio_fit_strategy == "pad_silence":
                    pad_count += 1

                render_segments.append(
                    TimelineSegment(
                        source_video=source_video,
                        audio_path=local_audio,
                        source_start_ms=source_start_ms,
                        target_duration_ms=target_duration_ms,
                        audio_fit_strategy=audio_fit_strategy,
                        speed_factor=speed_factor,
                    )
                )
                legacy_segments.append(
                    {
                        "source_video": source_video,
                        "audio_path": local_audio,
                        "source_start_ms": source_start_ms,
                        "source_duration_ms": source_duration_ms,
                        "target_duration_ms": target_duration_ms,
                    }
                )

                timeline.append(
                    {
                        "scene_id": scene_id,
                        "sentence_id": sentence_id,
                        "source_video_key": scene_source_video_key,
                        "start_ms": offset_ms,
                        "end_ms": offset_ms + target_duration_ms,
                        "audio_path": audio["audio_path"],
                        "subtitle_text": sentence.get("text", ""),
                        "audio_trimmed": audio_fit_strategy == "trim",
                        "skipped": False,
                        "target_duration_ms": target_duration_ms,
                        "raw_audio_duration_ms": raw_audio_duration_ms,
                        "final_audio_duration_ms": target_duration_ms,
                        "audio_fit_strategy": audio_fit_strategy,
                        "speed_factor": speed_factor,
                    }
                )
                offset_ms += target_duration_ms

            if not render_segments:
                return {"error": "no_renderable_segments"}

            final_video = tmp_path / "final.mp4"
            pipeline_used = self.pipeline_mode
            if self.pipeline_mode == "single_pass":
                try:
                    render_timeline_single_pass(
                        source_videos=list(source_videos.values()),
                        segments=render_segments,
                        output_path=final_video,
                        output_fps=self.output_fps,
                        output_sample_rate=self.output_sample_rate,
                    )
                except Exception as exc:
                    if not self.allow_legacy_fallback:
                        return {"error": f"single_pass_render_failed:{exc}"}
                    pipeline_used = "legacy_fallback"
                    self._render_with_legacy(legacy_segments, tmp_path, final_video)
            else:
                pipeline_used = "legacy"
                self._render_with_legacy(legacy_segments, tmp_path, final_video)

            for index in range(1, len(timeline)):
                if timeline[index]["start_ms"] < timeline[index - 1]["start_ms"]:
                    return {"error": "timeline_non_monotonic"}

            video_key = f"{task_id}/final.mp4"
            timeline_key = f"{task_id}/timeline.json"
            self.minio.upload_file(self.buckets["output"], video_key, str(final_video), content_type="video/mp4")
            self.minio.upload_bytes(
                self.buckets["output"],
                timeline_key,
                json.dumps(timeline, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
            )

            render_stats = {
                "speedup_count": speedup_count,
                "trim_count": trim_count,
                "pad_count": pad_count,
                "voice_fallback": bool(voice_profile_fallback),
                "pipeline_mode": pipeline_used,
            }

            return {
                "output_video": f"{self.buckets['output']}/{video_key}",
                "timeline": timeline,
                "timeline_path": f"{self.buckets['output']}/{timeline_key}",
                "render_stats": render_stats,
            }

    def _render_with_legacy(self, segments: list[dict[str, Any]], tmp_path: Path, final_video: Path) -> None:
        segment_paths: list[Path] = []
        for index, segment in enumerate(segments):
            local_audio_wav = tmp_path / f"legacy_audio_{index:04d}.wav"
            transcode_audio_to_wav(
                segment["audio_path"],
                local_audio_wav,
                int(segment["target_duration_ms"]),
                pad_to_duration=True,
            )

            segment_output = tmp_path / f"segment_{index:04d}.mov"
            cut_merge_segment(
                source_video=segment["source_video"],
                audio_path=local_audio_wav,
                start_ms=int(segment["source_start_ms"]),
                source_scene_duration_ms=int(segment["source_duration_ms"]),
                target_duration_ms=int(segment["target_duration_ms"]),
                output_path=segment_output,
            )
            segment_paths.append(segment_output)

        if not segment_paths:
            raise RuntimeError("no_renderable_segments")
        concat_segments(segment_paths, final_video)

    def _decide_audio_fit(self, raw_audio_duration_ms: int, target_duration_ms: int) -> tuple[str, float]:
        if target_duration_ms <= 0:
            return "trim", 1.0

        if raw_audio_duration_ms > target_duration_ms:
            ratio = raw_audio_duration_ms / target_duration_ms
            if ratio <= max(1.0, self.audio_fit_max_speed):
                return "speedup", ratio
            return "trim", 1.0

        if raw_audio_duration_ms < target_duration_ms:
            return "pad_silence", 1.0

        return "none", 1.0

    def _normalize_video_keys(self, source_video_key: str | None, source_video_keys: list[str] | None) -> list[str]:
        if source_video_keys:
            return [str(key) for key in source_video_keys if str(key)]
        if source_video_key:
            return [source_video_key]
        return []


service = VideoRenderService()
mcp = FastMCP("video-render") if FastMCP else None

if mcp:

    @mcp.tool(name="render_video")
    async def render_video_tool(
        task_id: str,
        scenes: list[dict[str, Any]],
        sentences: list[dict[str, Any]],
        audio_segments: list[dict[str, Any]],
        source_video_key: str | None = None,
        source_video_keys: list[str] | None = None,
        voice_profile_fallback: bool | None = None,
    ) -> dict[str, Any]:
        return await service.render_video(
            task_id=task_id,
            source_video_key=source_video_key,
            source_video_keys=source_video_keys,
            scenes=scenes,
            sentences=sentences,
            audio_segments=audio_segments,
            voice_profile_fallback=voice_profile_fallback,
        )


if __name__ == "__main__":  # pragma: no cover
    if not mcp:
        raise SystemExit("mcp sdk unavailable")
    mcp.run(transport="stdio")
