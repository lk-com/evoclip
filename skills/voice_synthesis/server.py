from __future__ import annotations

import ipaddress
import logging
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from skills.common import RetryPolicy, get_credential, get_settings, retry_async
from skills.voice_synthesis.tts_adapter import TTSAdapter
from store.minio_client import MinioStore

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None

logger = logging.getLogger(__name__)


def read_duration_ms(audio_path: Path) -> int:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    raw = subprocess.check_output(cmd, text=True).strip()
    return int(round(float(raw) * 1000))


class VoiceSynthesisService:
    def __init__(self) -> None:
        settings = get_settings()
        tts_cfg = settings.data["tts"]
        openai_api_key = get_credential(settings, "openai_api_key")
        openai_base_url = get_credential(settings, "openai_base_url")
        dashscope_api_key = get_credential(settings, "dashscope_api_key")
        dashscope_base_url = get_credential(settings, "dashscope_base_url")
        minio_cfg = settings.storage["minio"]
        self.buckets = minio_cfg["buckets"]
        self.tts_cfg = tts_cfg
        self.clone_from_video = bool(tts_cfg.get("clone_from_video", True))
        self.clone_strict = bool(tts_cfg.get("clone_strict", False))
        self.clone_prefix = str(tts_cfg.get("clone_prefix", "evoclip")).strip() or "evoclip"
        self.clone_sample_seconds = int(tts_cfg.get("clone_sample_seconds", 15))
        self.clone_sample_max_seconds = int(tts_cfg.get("clone_sample_max_seconds", 60))
        self.clone_poll_seconds = int(tts_cfg.get("clone_poll_seconds", 2))
        self.clone_max_wait_seconds = int(tts_cfg.get("clone_max_wait_seconds", 60))
        self.clone_presign_expire_seconds = int(tts_cfg.get("clone_presign_expire_seconds", 3600))
        self.clone_public_base_url = str(tts_cfg.get("clone_public_base_url", "")).strip() or None
        self.clone_audio_url = str(tts_cfg.get("clone_audio_url", "")).strip() or None
        self.clone_fixed_voice_id = str(tts_cfg.get("dashscope_voice_id", "")).strip() or None
        self.clone_language_hint = str(tts_cfg.get("clone_language_hint", "")).strip() or None
        self.adapter = TTSAdapter(
            provider=tts_cfg["provider"],
            openai_model=tts_cfg["openai_model"],
            volcengine_voice=tts_cfg["volcengine_voice"],
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            dashscope_model=str(tts_cfg.get("dashscope_model", "cosyvoice-v3-plus")),
            dashscope_voice=str(tts_cfg.get("dashscope_voice", "longxiaochun_v2")),
            dashscope_api_key=dashscope_api_key,
            dashscope_base_url=dashscope_base_url,
        )
        self.minio = MinioStore(
            endpoint=minio_cfg["endpoint"],
            access_key=minio_cfg["access_key"],
            secret_key=minio_cfg["secret_key"],
            secure=minio_cfg.get("secure", False),
        )

    async def synthesize_voice(
        self,
        task_id: str,
        sentences: list[dict[str, Any]],
        source_video_key: str | None = None,
        source_video_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        if not sentences:
            return {"error": "empty_sentences"}

        self.minio.ensure_bucket(self.buckets["audio"])
        self.minio.ensure_bucket(self.buckets["intermediate"])
        output: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix="evoclip-tts-") as tmp:
            working_dir = Path(tmp)
            voice_profile, voice_profile_fallback = await self._resolve_voice_profile(
                task_id=task_id,
                source_video_keys=self._normalize_video_keys(source_video_key, source_video_keys),
                working_dir=working_dir,
            )
            for sentence in sentences:
                sentence_id = sentence["sentence_id"]
                text = str(sentence.get("text", "")).strip()
                if not text:
                    output.append(
                        {
                            "sentence_id": sentence_id,
                            "audio_path": None,
                            "duration_ms": 0,
                            "status": "failed",
                        }
                    )
                    continue

                local_path = working_dir / f"{sentence_id}.mp3"

                try:
                    await retry_async(
                        lambda: self.adapter.synthesize(text=text, output_path=local_path, voice=voice_profile),
                        RetryPolicy(retries=3, delays=(1.0, 2.0, 4.0)),
                    )
                    duration_ms = read_duration_ms(local_path)
                    object_key = f"{task_id}/{sentence_id}.mp3"
                    audio_path = self.minio.upload_file(
                        self.buckets["audio"], object_key, str(local_path), content_type="audio/mpeg"
                    )
                    output.append(
                        {
                            "sentence_id": sentence_id,
                            "audio_path": audio_path,
                            "duration_ms": duration_ms,
                            "status": "ok",
                        }
                    )
                except Exception as exc:
                    error_text = str(exc or "tts_failed")
                    logger.warning("TTS failed for sentence %s: %s", sentence_id, error_text)
                    output.append(
                        {
                            "sentence_id": sentence_id,
                            "audio_path": None,
                            "duration_ms": 0,
                            "status": "failed",
                            "error": error_text,
                        }
                    )

        payload: dict[str, Any] = {"audio_segments": output}
        ok_count = sum(1 for item in output if item.get("status") == "ok")
        if ok_count == 0:
            payload["error"] = "all_tts_failed"
            payload["failed_reasons"] = [item.get("error", "tts_failed") for item in output if item.get("status") == "failed"]
        payload["ok_count"] = ok_count
        payload["failed_count"] = len(output) - ok_count
        if voice_profile:
            payload["voice_profile"] = voice_profile
        if voice_profile_fallback:
            payload["voice_profile_fallback"] = True
        return payload

    async def _resolve_voice_profile(
        self,
        task_id: str,
        source_video_keys: list[str],
        working_dir: Path,
    ) -> tuple[str | None, bool]:
        if self.adapter.provider != "dashscope_clone":
            return None, False
        if self.clone_fixed_voice_id:
            return self.clone_fixed_voice_id, False
        if self.clone_audio_url:
            try:
                return await self._clone_from_audio_url(task_id=task_id, audio_url=self.clone_audio_url), False
            except Exception as exc:
                if self.clone_strict:
                    raise
                logger.warning("Configured clone_audio_url failed, fallback to default voice: %s", exc)
                return None, True
        if not self.clone_from_video:
            return None, False
        if not source_video_keys:
            if self.clone_strict:
                raise RuntimeError("clone_source_video_missing")
            return None, True

        clone_audio_url = self._prepare_clone_audio_url(
            task_id=task_id,
            source_video_keys=source_video_keys,
            working_dir=working_dir,
        )
        if not clone_audio_url:
            if self.clone_strict:
                raise RuntimeError("clone_audio_url_unavailable")
            return None, True
        try:
            return await self._clone_from_audio_url(task_id=task_id, audio_url=clone_audio_url), False
        except Exception as exc:
            if self.clone_strict:
                raise
            logger.warning("Clone from video sample failed, fallback to default voice: %s", exc)
            return None, True

    async def _clone_from_audio_url(self, task_id: str, audio_url: str) -> str:
        prefix = self._build_clone_prefix(task_id)
        return await self.adapter.clone_voice(
            audio_url=audio_url,
            prefix=prefix,
            poll_interval_seconds=self.clone_poll_seconds,
            max_wait_seconds=self.clone_max_wait_seconds,
            language_hint=self.clone_language_hint,
        )

    def _prepare_clone_audio_url(
        self,
        task_id: str,
        source_video_keys: list[str],
        working_dir: Path,
    ) -> str | None:
        if not source_video_keys:
            return None
        sample_durations = self._allocate_clone_durations(source_video_keys)
        sample_paths: list[Path] = []
        for idx, (video_key, duration_seconds) in enumerate(sample_durations):
            suffix = Path(video_key).suffix or ".mp4"
            source_video = working_dir / f"clone_source_{idx}{suffix}"
            self.minio.download_file(self.buckets["videos"], video_key, str(source_video))
            sample_audio = working_dir / f"clone_sample_{idx}.wav"
            self._extract_clone_sample(
                source_video=source_video,
                output_audio=sample_audio,
                duration_seconds=duration_seconds,
            )
            sample_paths.append(sample_audio)

        if not sample_paths:
            return None

        sample_audio = working_dir / "clone_sample.wav"
        if len(sample_paths) == 1:
            sample_audio.write_bytes(sample_paths[0].read_bytes())
        else:
            self._concat_clone_samples(sample_paths, sample_audio)

        clone_object_key = f"{task_id}/clone_sample.wav"
        self.minio.upload_file(
            self.buckets["intermediate"],
            clone_object_key,
            str(sample_audio),
            content_type="audio/wav",
        )

        try:
            return self.minio.presigned_get_object(
                self.buckets["intermediate"],
                clone_object_key,
                expires=timedelta(seconds=self.clone_presign_expire_seconds),
                public_base_url=self.clone_public_base_url,
            )
        except ValueError:
            # 向后兼容：用于公共入口点带有路径前缀的部署（例如 /minio 的反向代理）
            presigned_url = self.minio.presigned_get_object(
                self.buckets["intermediate"],
                clone_object_key,
                expires=timedelta(seconds=self.clone_presign_expire_seconds),
            )
            return self._rewrite_public_url(presigned_url)

    def _rewrite_public_url(self, presigned_url: str) -> str | None:
        if not self.clone_public_base_url:
            parsed = urlparse(presigned_url)
            if self._is_non_public_hostname(parsed.hostname):
                return None
            return presigned_url

        replacement = urlparse(self.clone_public_base_url)
        parsed = urlparse(presigned_url)
        new_scheme = replacement.scheme or parsed.scheme
        new_netloc = replacement.netloc or replacement.path or parsed.netloc
        return urlunparse((new_scheme, new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

    def _is_non_public_hostname(self, hostname: str | None) -> bool:
        if not hostname:
            return True
        lowered = hostname.strip().lower()
        if lowered in {"localhost"} or lowered.endswith(".local"):
            return True
        try:
            addr = ipaddress.ip_address(lowered)
        except ValueError:
            return False
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_unspecified
            or addr.is_reserved
        )

    def _extract_clone_sample(self, source_video: Path, output_audio: Path, duration_seconds: int | None = None) -> None:
        duration = duration_seconds or self.clone_sample_seconds
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-t",
            str(max(1, duration)),
            str(output_audio),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("clone_sample_extract_failed") from exc

    def _concat_clone_samples(self, sample_paths: list[Path], output_audio: Path) -> None:
        concat_list = output_audio.with_suffix(".txt")
        lines = [f"file '{path.as_posix()}'" for path in sample_paths]
        concat_list.write_text("\n".join(lines), encoding="utf-8")
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output_audio),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("clone_sample_concat_failed") from exc

    def _allocate_clone_durations(self, source_video_keys: list[str]) -> list[tuple[str, int]]:
        if not source_video_keys:
            return []
        total_seconds = max(1, self.clone_sample_seconds)
        total_seconds = min(total_seconds, max(1, self.clone_sample_max_seconds))
        if total_seconds < len(source_video_keys):
            return [(key, 1) for key in source_video_keys[:total_seconds]]
        base = total_seconds // len(source_video_keys)
        remainder = total_seconds % len(source_video_keys)
        allocated: list[tuple[str, int]] = []
        for idx, key in enumerate(source_video_keys):
            duration = base + (1 if idx < remainder else 0)
            allocated.append((key, max(1, duration)))
        return allocated

    def _normalize_video_keys(
        self,
        source_video_key: str | None,
        source_video_keys: list[str] | None,
    ) -> list[str]:
        if source_video_keys:
            return [str(key) for key in source_video_keys if str(key)]
        if source_video_key:
            return [source_video_key]
        return []

    def _build_clone_prefix(self, task_id: str) -> str:
        raw = (self.clone_prefix or "evoclip").lower()
        sanitized = "".join(ch for ch in raw if ch.isalnum())
        if not sanitized:
            sanitized = "evoclip"
        sanitized = sanitized[:10]
        suffix = "".join(ch for ch in task_id.lower() if ch.isalnum())[:4]
        if suffix and len(sanitized) < 10:
            remaining = 10 - len(sanitized)
            sanitized = f"{sanitized}{suffix[:remaining]}"
        return sanitized


service = VoiceSynthesisService()
mcp = FastMCP("voice-synthesis") if FastMCP else None

if mcp:

    @mcp.tool(name="synthesize_voice")
    async def synthesize_voice_tool(
        task_id: str,
        sentences: list[dict[str, Any]],
        source_video_key: str | None = None,
        source_video_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        return await service.synthesize_voice(
            task_id=task_id,
            sentences=sentences,
            source_video_key=source_video_key,
            source_video_keys=source_video_keys,
        )


if __name__ == "__main__":  # pragma: no cover
    if not mcp:
        raise SystemExit("mcp sdk unavailable")
    mcp.run(transport="stdio")
