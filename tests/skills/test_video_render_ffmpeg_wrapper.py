from __future__ import annotations

from pathlib import Path

from skills.video_render import ffmpeg_wrapper


def test_render_timeline_single_pass_builds_expected_cmd(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, list[str]] = {}

    def fake_check_call(cmd: list[str]) -> None:
        captured["cmd"] = cmd

    monkeypatch.setattr(ffmpeg_wrapper.subprocess, "check_call", fake_check_call)

    source_a = tmp_path / "source_a.mp4"
    source_b = tmp_path / "source_b.mp4"
    audio_a = tmp_path / "a.mp3"
    audio_b = tmp_path / "b.mp3"
    for path in (source_a, source_b, audio_a, audio_b):
        path.write_bytes(b"x")

    segments = [
        ffmpeg_wrapper.TimelineSegment(
            source_video=source_a,
            audio_path=audio_a,
            source_start_ms=0,
            target_duration_ms=1000,
            audio_fit_strategy="speedup",
            speed_factor=1.05,
        ),
        ffmpeg_wrapper.TimelineSegment(
            source_video=source_b,
            audio_path=audio_b,
            source_start_ms=500,
            target_duration_ms=1500,
            audio_fit_strategy="pad_silence",
            speed_factor=1.0,
        ),
    ]
    output_path = tmp_path / "final.mp4"

    ffmpeg_wrapper.render_timeline_single_pass(
        source_videos=[source_a, source_b],
        segments=segments,
        output_path=output_path,
        output_fps=30,
        output_sample_rate=24000,
    )

    cmd = captured["cmd"]
    assert cmd[:2] == ["ffmpeg", "-y"]
    assert "-filter_complex" in cmd
    filter_graph = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=1" in filter_graph
    assert "atempo=1.050000" in filter_graph
    assert "apad=pad_dur=1.500" in filter_graph
    assert "-map" in cmd and "[vout]" in cmd and "[aout]" in cmd
    assert cmd[-1] == str(output_path)


def test_concat_segments_normalizes_audio_timestamps(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, list[str]] = {}

    def fake_check_call(cmd: list[str]) -> None:
        captured["cmd"] = cmd

    monkeypatch.setattr(ffmpeg_wrapper.subprocess, "check_call", fake_check_call)

    segment_paths = [tmp_path / "segment_0000.mp4", tmp_path / "segment_0001.mp4"]
    for path in segment_paths:
        path.write_bytes(b"x")
    output_path = tmp_path / "final.mp4"

    ffmpeg_wrapper.concat_segments(segment_paths, output_path)

    cmd = captured["cmd"]
    assert "-f" in cmd and "concat" in cmd
    assert "-fflags" in cmd and "+genpts" in cmd
    assert "-c:v" in cmd and "copy" in cmd
    assert "-c:a" in cmd and "aac" in cmd
    assert "-af" in cmd and "aresample=async=1:first_pts=0" in cmd
    assert cmd[-1] == str(output_path)


def test_transcode_audio_to_wav_builds_expected_cmd(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, list[str]] = {}

    def fake_check_call(cmd: list[str]) -> None:
        captured["cmd"] = cmd

    monkeypatch.setattr(ffmpeg_wrapper.subprocess, "check_call", fake_check_call)

    audio_path = tmp_path / "t_0.mp3"
    audio_path.write_bytes(b"x")
    wav_path = tmp_path / "t_0.wav"
    ffmpeg_wrapper.transcode_audio_to_wav(audio_path, wav_path, 1500, pad_to_duration=True)

    cmd = captured["cmd"]
    assert cmd[:3] == ["ffmpeg", "-y", "-i"]
    assert str(audio_path) in cmd
    assert "-af" in cmd
    assert "apad=pad_dur=1.500" in cmd
    assert "-t" in cmd and "1.500" in cmd
    assert "-c:a" in cmd and "pcm_s16le" in cmd
    assert cmd[-1] == str(wav_path)
