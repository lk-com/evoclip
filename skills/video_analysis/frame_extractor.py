from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import ffmpeg

SUPPORTED_EXTENSIONS = {".mp4", ".mov"}  # 支持的视频格式
MAX_VIDEO_SIZE_MB = 500  # 最大视频大小（MB）
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024  # 最大视频大小（字节）


@dataclass
class FrameInfo:
    path: Path
    timestamp_ms: int


class VideoValidationError(ValueError):
    pass


def validate_video_file(file_name: str, file_size: int) -> None:
    """验证视频文件格式和大小"""
    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise VideoValidationError("unsupported_format")
    if file_size > MAX_VIDEO_SIZE_BYTES:
        raise VideoValidationError("video_too_large")


def extract_frames(video_path: str, output_dir: str, fps: int = 1) -> list[FrameInfo]:
    """从视频中提取帧"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    frame_pattern = str(output_path / "frame_%06d.jpg")

    (
        ffmpeg.input(video_path)
        .output(frame_pattern, vf=f"fps={fps}", qscale=2)
        .overwrite_output()
        .run(quiet=True)
    )

    probe = ffmpeg.probe(video_path)
    duration = float(probe["format"]["duration"])
    frame_files = sorted(output_path.glob("frame_*.jpg"))
    result: list[FrameInfo] = []
    for index, frame_file in enumerate(frame_files):
        timestamp_ms = int(min(index / fps, duration) * 1000)
        result.append(FrameInfo(path=frame_file, timestamp_ms=timestamp_ms))
    return result


def get_video_duration_ms(video_path: str) -> int:
    """获取视频时长（毫秒）"""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    raw = subprocess.check_output(cmd, text=True).strip()
    return int(float(raw) * 1000)
