from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


AudioFitStrategy = Literal["none", "speedup", "trim", "pad_silence"]


@dataclass(frozen=True)
class TimelineSegment:
    source_video: Path
    audio_path: Path
    source_start_ms: int
    target_duration_ms: int
    audio_fit_strategy: AudioFitStrategy
    speed_factor: float = 1.0


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


def render_timeline_single_pass(
    source_videos: list[Path],
    segments: list[TimelineSegment],
    output_path: Path,
    output_fps: int = 30,
    output_sample_rate: int = 24000,
) -> None:
    """单遍渲染时间线"""
    if not source_videos:
        raise ValueError("empty_source_videos")
    if not segments:
        raise ValueError("empty_segments")

    dedup_videos: list[Path] = []
    video_index_map: dict[str, int] = {}
    for source in source_videos:
        key = str(source)
        if key in video_index_map:
            continue
        video_index_map[key] = len(dedup_videos)
        dedup_videos.append(source)

    cmd: list[str] = ["ffmpeg", "-y"]
    for source in dedup_videos:
        cmd.extend(["-i", str(source)])
    for segment in segments:
        cmd.extend(["-i", str(segment.audio_path)])

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    audio_input_base = len(dedup_videos)

    for idx, segment in enumerate(segments):
        duration_s = max(segment.target_duration_ms, 1) / 1000
        start_s = max(segment.source_start_ms, 0) / 1000

        video_input_index = video_index_map[str(segment.source_video)]
        video_label = f"v{idx}"
        audio_label = f"a{idx}"

        filter_parts.append(
            f"[{video_input_index}:v:0]"
            f"trim=start={start_s:.3f}:duration={duration_s:.3f},"
            f"setpts=PTS-STARTPTS,fps={max(1, output_fps)},format=yuv420p"
            f"[{video_label}]"
        )

        audio_input_index = audio_input_base + idx
        strategy = segment.audio_fit_strategy
        speed_factor = max(segment.speed_factor, 0.01)
        if strategy == "speedup":
            audio_filter = (
                f"[{audio_input_index}:a:0]"
                f"aresample={max(8000, output_sample_rate)},"
                f"atempo={speed_factor:.6f},"
                f"apad=pad_dur={duration_s:.3f},"
                f"atrim=duration={duration_s:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates={max(8000, output_sample_rate)}:channel_layouts=mono"
                f"[{audio_label}]"
            )
        elif strategy == "pad_silence":
            audio_filter = (
                f"[{audio_input_index}:a:0]"
                f"aresample={max(8000, output_sample_rate)},"
                f"apad=pad_dur={duration_s:.3f},"
                f"atrim=duration={duration_s:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates={max(8000, output_sample_rate)}:channel_layouts=mono"
                f"[{audio_label}]"
            )
        else:
            # `none` 和 `trim` 都保持原始速度，但强制精确的目标时长
            audio_filter = (
                f"[{audio_input_index}:a:0]"
                f"aresample={max(8000, output_sample_rate)},"
                f"apad=pad_dur={duration_s:.3f},"
                f"atrim=duration={duration_s:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates={max(8000, output_sample_rate)}:channel_layouts=mono"
                f"[{audio_label}]"
            )
        filter_parts.append(audio_filter)
        concat_inputs.append(f"[{video_label}][{audio_label}]")

    filter_parts.append(
        f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a=1[vout][aout]"
    )
    filter_complex = ";".join(filter_parts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(max(1, output_fps)),
            "-c:a",
            "aac",
            "-ar",
            str(max(8000, output_sample_rate)),
            "-ac",
            "1",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    subprocess.check_call(cmd)


def cut_merge_segment(
    source_video: Path,
    audio_path: Path,
    start_ms: int,
    source_scene_duration_ms: int,
    target_duration_ms: int,
    output_path: Path,
) -> None:
    """裁剪并合并片段"""
    start_s = start_ms / 1000
    source_duration_s = max(source_scene_duration_ms, 1) / 1000
    target_duration_s = max(target_duration_ms, 1) / 1000

    if target_duration_ms <= source_scene_duration_ms:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_s:.3f}",
            "-i",
            str(source_video),
            "-i",
            str(audio_path),
            "-t",
            f"{target_duration_s:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-shortest",
            str(output_path),
        ]
    else:
        # 通过循环片段来延长短场景，然后与音频混合
        loop_count = max(int(target_duration_ms / max(source_scene_duration_ms, 1)) + 1, 2)
        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop",
            str(loop_count),
            "-ss",
            f"{start_s:.3f}",
            "-t",
            f"{source_duration_s:.3f}",
            "-i",
            str(source_video),
            "-i",
            str(audio_path),
            "-t",
            f"{target_duration_s:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(output_path),
        ]

    subprocess.check_call(cmd)


def transcode_audio_to_wav(
    audio_path: Path,
    output_path: Path,
    target_duration_ms: int,
    pad_to_duration: bool = False,
) -> None:
    """将音频转码为 WAV 格式"""
    duration_s = max(target_duration_ms, 1) / 1000
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "24000",
    ]
    if pad_to_duration:
        cmd.extend(["-af", f"apad=pad_dur={duration_s:.3f}"])
    cmd.extend(
        [
        "-t",
        f"{duration_s:.3f}",
        "-c:a",
        "pcm_s16le",
        str(output_path),
        ]
    )
    subprocess.check_call(cmd)


def concat_segments(segment_paths: list[Path], output_path: Path) -> None:
    """连接多个片段"""
    list_file = output_path.parent / "segments.txt"
    lines = [f"file '{path.as_posix()}'" for path in segment_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-fflags",
        "+genpts",
        "-i",
        str(list_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        # 在连接时重新编码音频一次，以规范化时间戳并
        # 避免来自每个片段 AAC 引导的非单调 DTS 警告
        "-c:a",
        "aac",
        "-ar",
        "24000",
        "-ac",
        "1",
        "-af",
        "aresample=async=1:first_pts=0",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.check_call(cmd)
