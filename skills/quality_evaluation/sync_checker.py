from __future__ import annotations

import subprocess
from pathlib import Path


def probe_duration_ms(media_path: Path) -> int:
    """探测媒体时长（毫秒）"""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    raw = subprocess.check_output(cmd, text=True).strip()
    return int(float(raw) * 1000)


def check_sync(timeline: list[dict], audio_duration_lookup: dict[str, int], tolerance_ms: int = 200) -> list[dict]:
    """检查音视频同步"""
    errors: list[dict] = []
    for item in timeline:
        if item.get("skipped"):
            continue
        audio_path = item.get("audio_path")
        if not audio_path and item.get("final_audio_duration_ms") is None:
            continue
        video_duration = int(item["end_ms"]) - int(item["start_ms"])
        if item.get("final_audio_duration_ms") is not None:
            audio_duration = int(item.get("final_audio_duration_ms") or 0)
        else:
            audio_duration = int(audio_duration_lookup.get(str(audio_path), video_duration))
        delta = abs(audio_duration - video_duration)
        if delta > max(0, int(tolerance_ms)):
            errors.append(
                {
                    "scene_id": item["scene_id"],
                    "audio_duration_ms": audio_duration,
                    "video_duration_ms": video_duration,
                    "delta_ms": delta,
                }
            )
    return errors
