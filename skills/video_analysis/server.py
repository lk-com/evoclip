from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from skills.common import RetryPolicy, get_settings, retry_async
from skills.video_analysis.frame_extractor import (
    FrameInfo,
    MAX_VIDEO_SIZE_BYTES,
    VideoValidationError,
    extract_frames,
    get_video_duration_ms,
    validate_video_file,
)
from skills.video_analysis.speech_recognizer import SpeechRecognizer
from skills.video_analysis.vision_adapter import VisionAdapter
from store.minio_client import MinioStore

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]
logger = logging.getLogger(__name__)


@dataclass
class Scene:
    scene_id: str
    start_ms: int
    end_ms: int
    description: str
    objects: list[str]
    transcription: str | None
    source_video_key: str | None = None
    source_start_ms: int | None = None
    source_end_ms: int | None = None


class VideoAnalysisService:
    def __init__(self) -> None:
        settings = get_settings()
        credentials = settings.data.get("credentials", {})
        analysis_cfg = settings.data.get("video_analysis", {})
        dashscope_api_key = str(credentials.get("dashscope_api_key", "")).strip() or None
        dashscope_base_url = str(credentials.get("dashscope_base_url", "")).strip() or None
        minio_cfg = settings.storage["minio"]
        self.buckets = minio_cfg["buckets"]
        self.min_scene_duration_ms = int(analysis_cfg.get("min_scene_duration_ms", 1800))
        self.scene_split_min_duration_ms = int(analysis_cfg.get("scene_split_min_duration_ms", 10_000))
        self.frame_sample_fps = max(1, int(analysis_cfg.get("frame_sample_fps", 1)))
        self.max_frames = max(1, int(analysis_cfg.get("max_frames", 12)))
        self.frame_analysis_concurrency = max(1, int(analysis_cfg.get("frame_analysis_concurrency", 3)))
        self.minio = MinioStore(
            endpoint=minio_cfg["endpoint"],
            access_key=minio_cfg["access_key"],
            secret_key=minio_cfg["secret_key"],
            secure=minio_cfg.get("secure", False),
        )
        self.vision = VisionAdapter(
            model=settings.data["vision"]["model"],
            timeout_seconds=int(settings.data["vision"]["timeout_seconds"]),
            api_key=dashscope_api_key,
            base_url=dashscope_base_url,
        )
        self.speech = SpeechRecognizer(
            model=settings.data["speech_recognition"]["model"],
            timeout_seconds=int(settings.data["speech_recognition"]["timeout_seconds"]),
            api_key=dashscope_api_key,
            base_url=dashscope_base_url,
        )

    async def analyze_video(
        self,
        task_id: str,
        video_object_key: str | None = None,
        video_object_keys: list[str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        normalized_video_keys = self._normalize_video_keys(video_object_key, video_object_keys)
        if not normalized_video_keys:
            return {"error": "empty_video_keys"}

        all_scenes: list[Scene] = []
        per_video_metrics: list[dict[str, Any]] = []
        total_extracted_frames = 0
        total_analyzed_frames = 0
        offset_ms = 0
        with tempfile.TemporaryDirectory(prefix="evoclip-video-") as tmp:
            tmp_dir = Path(tmp)
            for video_idx, input_video_key in enumerate(normalized_video_keys):
                file_name = Path(input_video_key).name
                await self._emit_progress(
                    progress_callback,
                    {
                        "stage": "video_started",
                        "video_index": video_idx,
                        "total_videos": len(normalized_video_keys),
                        "video_object_key": input_video_key,
                    },
                )
                stat = self.minio.client.stat_object(self.buckets["videos"], input_video_key)
                try:
                    validate_video_file(file_name, stat.size)
                except VideoValidationError as exc:
                    return {"error": str(exc), "max_size_bytes": MAX_VIDEO_SIZE_BYTES, "file_size_bytes": stat.size}

                video_path = tmp_dir / f"{video_idx}_{file_name}"
                frame_dir = tmp_dir / f"frames_{video_idx}"
                self.minio.download_file(self.buckets["videos"], input_video_key, str(video_path))

                frames = extract_frames(str(video_path), str(frame_dir), fps=self.frame_sample_fps)
                if not frames:
                    return {"error": "empty_video", "video_object_key": input_video_key}
                frames_for_analysis, frame_limited = self._limit_frames(frames)
                skipped_frames = max(0, len(frames) - len(frames_for_analysis))
                total_extracted_frames += len(frames)
                total_analyzed_frames += len(frames_for_analysis)
                await self._emit_progress(
                    progress_callback,
                    {
                        "stage": "frames_selected",
                        "video_index": video_idx,
                        "video_object_key": input_video_key,
                        "extracted_frames": len(frames),
                        "selected_frames": len(frames_for_analysis),
                        "skipped_frames": skipped_frames,
                        "frame_limit_applied": frame_limited,
                    },
                )

                frame_analysis_started = perf_counter()
                analyzed = await self._analyze_frames(
                    frames_for_analysis,
                    source_video_key=input_video_key,
                    progress_callback=progress_callback,
                )
                frame_analysis_elapsed_ms = int((perf_counter() - frame_analysis_started) * 1000)
                source_duration_ms = get_video_duration_ms(str(video_path))
                source_scenes = self._merge_frames_into_scenes(analyzed, source_duration_ms)

                transcription_fallback = False
                try:
                    transcription_segments = await retry_async(
                        lambda: self.speech.transcribe(str(video_path)),
                        RetryPolicy(retries=2, delays=(1.0, 2.0)),
                    )
                    self._align_transcription(source_scenes, transcription_segments)
                except Exception:
                    transcription_fallback = True
                    for scene in source_scenes:
                        scene.transcription = None

                for source_scene in source_scenes:
                    all_scenes.append(
                        Scene(
                            scene_id=f"s_{len(all_scenes)}",
                            start_ms=source_scene.start_ms + offset_ms,
                            end_ms=source_scene.end_ms + offset_ms,
                            description=source_scene.description,
                            objects=list(source_scene.objects),
                            transcription=source_scene.transcription,
                            source_video_key=input_video_key,
                            source_start_ms=source_scene.start_ms,
                            source_end_ms=source_scene.end_ms,
                        )
                    )
                per_video_metrics.append(
                    {
                        "video_index": video_idx,
                        "video_object_key": input_video_key,
                        "source_duration_ms": source_duration_ms,
                        "extracted_frames": len(frames),
                        "analyzed_frames": len(frames_for_analysis),
                        "skipped_frames": skipped_frames,
                        "frame_limit_applied": frame_limited,
                        "frame_analysis_elapsed_ms": frame_analysis_elapsed_ms,
                        "scene_count": len(source_scenes),
                        "transcription_fallback": transcription_fallback,
                    }
                )
                await self._emit_progress(
                    progress_callback,
                    {
                        "stage": "video_completed",
                        "video_index": video_idx,
                        "video_object_key": input_video_key,
                        "scene_count": len(source_scenes),
                        "analyzed_frames": len(frames_for_analysis),
                        "frame_analysis_elapsed_ms": frame_analysis_elapsed_ms,
                    },
                )
                offset_ms += source_duration_ms

            scene_dicts = [scene.__dict__ for scene in all_scenes]
            object_key = f"{task_id}/scene_analysis.json"
            self.minio.upload_bytes(
                self.buckets["intermediate"],
                object_key,
                json.dumps(scene_dicts, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
            )
            frame_limit_applied_videos = sum(1 for item in per_video_metrics if item["frame_limit_applied"])
            metrics = {
                "total_videos": len(normalized_video_keys),
                "total_scenes": len(scene_dicts),
                "total_extracted_frames": total_extracted_frames,
                "total_analyzed_frames": total_analyzed_frames,
                "frame_limit_applied_videos": frame_limit_applied_videos,
                "frame_sample_fps": self.frame_sample_fps,
                "max_frames_per_video": self.max_frames,
                "frame_analysis_concurrency": self.frame_analysis_concurrency,
                "videos": per_video_metrics,
            }
            await self._emit_progress(
                progress_callback,
                {
                    "stage": "analysis_completed",
                    "total_scenes": len(scene_dicts),
                    "total_analyzed_frames": total_analyzed_frames,
                    "total_extracted_frames": total_extracted_frames,
                },
            )
            return {
                "scenes": scene_dicts,
                "result_path": f"{self.buckets['intermediate']}/{object_key}",
                "analysis_metrics": metrics,
            }

    def _normalize_video_keys(
        self,
        video_object_key: str | None,
        video_object_keys: list[str] | None,
    ) -> list[str]:
        if video_object_keys:
            return [str(item) for item in video_object_keys if str(item)]
        if video_object_key:
            return [video_object_key]
        return []

    async def _analyze_frames(
        self,
        frames: list[FrameInfo],
        *,
        source_video_key: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        analyzed: list[dict[str, Any] | None] = [None] * len(frames)
        total = len(frames)
        processed = 0
        lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(self.frame_analysis_concurrency)

        async def _analyze_single(index: int, frame: FrameInfo) -> None:
            nonlocal processed
            async with semaphore:
                frame_started = perf_counter()
                try:
                    result = await retry_async(
                        lambda: self.vision.analyze_frame(frame.path),
                        RetryPolicy(retries=3, delays=(1.0, 2.0, 4.0)),
                    )
                except Exception as exc:
                    frame_elapsed_ms = int((perf_counter() - frame_started) * 1000)
                    async with lock:
                        processed += 1
                        processed_now = processed
                    await self._emit_progress(
                        progress_callback,
                        {
                            "stage": "frame_failed",
                            "video_object_key": source_video_key,
                            "frame_index": index,
                            "timestamp_ms": frame.timestamp_ms,
                            "processed_frames": processed_now,
                            "total_frames": total,
                            "frame_elapsed_ms": frame_elapsed_ms,
                            "error": str(exc),
                        },
                    )
                    raise RuntimeError("vision_api_unavailable") from exc

                frame_elapsed_ms = int((perf_counter() - frame_started) * 1000)
                analyzed[index] = {
                    "timestamp_ms": frame.timestamp_ms,
                    "description": str(result.get("description", "")).strip() or "unknown scene",
                    "objects": result.get("objects", []),
                }
                async with lock:
                    processed += 1
                    processed_now = processed
                await self._emit_progress(
                    progress_callback,
                    {
                        "stage": "frame_processed",
                        "video_object_key": source_video_key,
                        "frame_index": index,
                        "timestamp_ms": frame.timestamp_ms,
                        "processed_frames": processed_now,
                        "total_frames": total,
                        "frame_elapsed_ms": frame_elapsed_ms,
                    },
                )

        tasks = [asyncio.create_task(_analyze_single(index, frame)) for index, frame in enumerate(frames)]
        await asyncio.gather(*tasks)

        ordered: list[dict[str, Any]] = []
        for item in analyzed:
            if item is None:
                raise RuntimeError("vision_api_unavailable")
            ordered.append(item)
        return ordered

    def _limit_frames(self, frames: list[FrameInfo]) -> tuple[list[FrameInfo], bool]:
        if len(frames) <= self.max_frames:
            return list(frames), False
        if self.max_frames == 1:
            return [frames[len(frames) // 2]], True
        last_index = len(frames) - 1
        selected = [frames[(index * last_index) // (self.max_frames - 1)] for index in range(self.max_frames)]
        return selected, True

    async def _emit_progress(
        self,
        callback: ProgressCallback | None,
        payload: dict[str, Any],
    ) -> None:
        if callback is None:
            return
        try:
            await callback(payload)
        except Exception:
            logger.debug("video_analysis_progress_callback_failed", exc_info=True)

    def _merge_frames_into_scenes(self, frames: list[dict[str, Any]], duration_ms: int) -> list[Scene]:
        if duration_ms <= self.scene_split_min_duration_ms:
            return [self._build_single_scene(frames=frames, duration_ms=duration_ms)]

        scenes: list[Scene] = []
        for frame in frames:
            if not scenes:
                scenes.append(
                    Scene(
                        scene_id="s_0",
                        start_ms=frame["timestamp_ms"],
                        end_ms=duration_ms,
                        description=frame["description"],
                        objects=list(frame["objects"]),
                        transcription=None,
                    )
                )
                continue

            last = scenes[-1]
            if frame["description"] == last.description:
                continue

            last.end_ms = max(last.end_ms, frame["timestamp_ms"])
            new_scene_id = f"s_{len(scenes)}"
            scenes.append(
                Scene(
                    scene_id=new_scene_id,
                    start_ms=frame["timestamp_ms"],
                    end_ms=duration_ms,
                    description=frame["description"],
                    objects=list(frame["objects"]),
                    transcription=None,
                )
            )

        for index, scene in enumerate(scenes):
            if index < len(scenes) - 1:
                scene.end_ms = scenes[index + 1].start_ms
            else:
                scene.end_ms = duration_ms
        return self._merge_short_adjacent_scenes(scenes)

    def _merge_short_adjacent_scenes(self, scenes: list[Scene]) -> list[Scene]:
        if len(scenes) <= 1:
            return scenes

        merged = [scenes[0]]
        for scene in scenes[1:]:
            prev = merged[-1]
            prev_duration = max(prev.end_ms - prev.start_ms, 0)
            if prev_duration < self.min_scene_duration_ms:
                prev.end_ms = scene.end_ms
                prev.objects = self._merge_objects(prev.objects, scene.objects)
                continue
            merged.append(scene)

        if len(merged) > 2:
            tail = merged[-1]
            tail_duration = max(tail.end_ms - tail.start_ms, 0)
            if tail_duration < self.min_scene_duration_ms:
                penultimate = merged[-2]
                penultimate.end_ms = tail.end_ms
                penultimate.objects = self._merge_objects(penultimate.objects, tail.objects)
                merged.pop()

        for idx, scene in enumerate(merged):
            scene.scene_id = f"s_{idx}"
        return merged

    def _build_single_scene(self, frames: list[dict[str, Any]], duration_ms: int) -> Scene:
        if not frames:
            return Scene(
                scene_id="s_0",
                start_ms=0,
                end_ms=max(1, duration_ms),
                description="unknown scene",
                objects=[],
                transcription=None,
            )
        middle = frames[len(frames) // 2]
        merged_objects: list[str] = []
        for frame in frames:
            merged_objects = self._merge_objects(merged_objects, list(frame.get("objects", [])))
        return Scene(
            scene_id="s_0",
            start_ms=0,
            end_ms=max(1, duration_ms),
            description=str(middle.get("description", "")).strip() or "unknown scene",
            objects=merged_objects,
            transcription=None,
        )

    def _merge_objects(self, left: list[str], right: list[str]) -> list[str]:
        merged: list[str] = []
        for item in list(left) + list(right):
            text = str(item).strip()
            if text and text not in merged:
                merged.append(text)
        return merged

    def _align_transcription(self, scenes: list[Scene], segments: list[dict[str, Any]]) -> None:
        for scene in scenes:
            chunk_texts: list[str] = []
            for segment in segments:
                start_ms = int(segment.get("begin_time", 0))
                end_ms = int(segment.get("end_time", 0))
                if start_ms < scene.end_ms and end_ms > scene.start_ms:
                    chunk_texts.append(str(segment.get("text", "")).strip())
            joined = " ".join(text for text in chunk_texts if text)
            scene.transcription = joined if joined else None


service = VideoAnalysisService()
mcp = FastMCP("video-analysis") if FastMCP else None

if mcp:

    @mcp.tool(name="analyze_video")
    async def analyze_video_tool(
        task_id: str,
        video_object_key: str | None = None,
        video_object_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        return await service.analyze_video(
            task_id=task_id,
            video_object_key=video_object_key,
            video_object_keys=video_object_keys,
        )


if __name__ == "__main__":  # pragma: no cover
    if not mcp:
        raise SystemExit("mcp sdk unavailable")
    mcp.run(transport="stdio")
