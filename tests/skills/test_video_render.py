from __future__ import annotations

from pathlib import Path

import pytest

from skills.video_render.server import VideoRenderService


@pytest.mark.asyncio
async def test_render_video_skips_failed_audio() -> None:
    service = VideoRenderService()

    scenes = [{"scene_id": "s_0", "start_ms": 0, "end_ms": 1000}]
    sentences = [{"sentence_id": "t_0", "scene_id": "s_0", "text": "x"}]
    audio = [{"sentence_id": "t_0", "status": "failed", "duration_ms": 0, "audio_path": None}]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.minio, "download_file", lambda *_: None)

    result = await service.render_video("task", "source.mp4", None, scenes, sentences, audio)
    assert result["error"] == "no_renderable_segments"
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_render_video_single_pass_speedup_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VideoRenderService()

    scenes = [{"scene_id": "s_0", "start_ms": 0, "end_ms": 1000}]
    sentences = [{"sentence_id": "t_0", "scene_id": "s_0", "text": "hello"}]
    audio = [{"sentence_id": "t_0", "status": "ok", "duration_ms": 1050, "audio_path": "audio/task/t_0.mp3"}]
    captured: dict[str, object] = {}

    def fake_download(bucket: str, obj: str, path: str) -> None:
        _ = bucket, obj
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"x")

    def fake_single_pass(**kwargs: object) -> None:
        captured.update(kwargs)
        output = kwargs["output_path"]
        Path(output).write_bytes(b"final")

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.minio, "download_file", fake_download)
    monkeypatch.setattr(service.minio, "upload_file", lambda bucket, key, path, content_type: f"{bucket}/{key}")
    monkeypatch.setattr(service.minio, "upload_bytes", lambda *args, **kwargs: "")
    monkeypatch.setattr("skills.video_render.server.probe_duration_ms", lambda *_args, **_kwargs: 1050)
    monkeypatch.setattr("skills.video_render.server.render_timeline_single_pass", fake_single_pass)

    result = await service.render_video("task", "source.mp4", None, scenes, sentences, audio)
    assert result["timeline"][0]["start_ms"] == 0
    assert result["timeline"][0]["end_ms"] == 1000
    assert result["timeline"][0]["target_duration_ms"] == 1000
    assert result["timeline"][0]["raw_audio_duration_ms"] == 1050
    assert result["timeline"][0]["final_audio_duration_ms"] == 1000
    assert result["timeline"][0]["audio_fit_strategy"] == "speedup"
    assert result["render_stats"]["speedup_count"] == 1
    segments = captured["segments"]
    assert segments


@pytest.mark.asyncio
async def test_render_video_trims_when_audio_far_longer(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VideoRenderService()

    scenes = [{"scene_id": "s_0", "start_ms": 0, "end_ms": 1000}]
    sentences = [{"sentence_id": "t_0", "scene_id": "s_0", "text": "long"}]
    audio = [{"sentence_id": "t_0", "status": "ok", "duration_ms": 3500, "audio_path": "audio/task/t_0.mp3"}]

    def fake_download(bucket: str, obj: str, path: str) -> None:
        _ = bucket, obj
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"x")

    def fake_single_pass(**kwargs: object) -> None:
        output = kwargs["output_path"]
        Path(output).write_bytes(b"final")

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.minio, "download_file", fake_download)
    monkeypatch.setattr(service.minio, "upload_file", lambda bucket, key, path, content_type: f"{bucket}/{key}")
    monkeypatch.setattr(service.minio, "upload_bytes", lambda *args, **kwargs: "")
    monkeypatch.setattr("skills.video_render.server.probe_duration_ms", lambda *_args, **_kwargs: 1300)
    monkeypatch.setattr("skills.video_render.server.render_timeline_single_pass", fake_single_pass)

    result = await service.render_video("task", "source.mp4", None, scenes, sentences, audio)
    assert result["timeline"][0]["audio_fit_strategy"] == "trim"
    assert result["timeline"][0]["audio_trimmed"] is True
    assert result["render_stats"]["trim_count"] == 1


@pytest.mark.asyncio
async def test_render_video_pads_short_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VideoRenderService()

    scenes = [{"scene_id": "s_0", "start_ms": 0, "end_ms": 1000}]
    sentences = [{"sentence_id": "t_0", "scene_id": "s_0", "text": "short"}]
    audio = [{"sentence_id": "t_0", "status": "ok", "duration_ms": 700, "audio_path": "audio/task/t_0.mp3"}]

    def fake_download(bucket: str, obj: str, path: str) -> None:
        _ = bucket, obj
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"x")

    def fake_single_pass(**kwargs: object) -> None:
        output = kwargs["output_path"]
        Path(output).write_bytes(b"final")

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.minio, "download_file", fake_download)
    monkeypatch.setattr(service.minio, "upload_file", lambda bucket, key, path, content_type: f"{bucket}/{key}")
    monkeypatch.setattr(service.minio, "upload_bytes", lambda *args, **kwargs: "")
    monkeypatch.setattr("skills.video_render.server.probe_duration_ms", lambda *_args, **_kwargs: 650)
    monkeypatch.setattr("skills.video_render.server.render_timeline_single_pass", fake_single_pass)

    result = await service.render_video("task", "source.mp4", None, scenes, sentences, audio)
    assert result["timeline"][0]["audio_fit_strategy"] == "pad_silence"
    assert result["render_stats"]["pad_count"] == 1


@pytest.mark.asyncio
async def test_render_video_uses_scene_source_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VideoRenderService()

    scenes = [
        {
            "scene_id": "s_0",
            "start_ms": 0,
            "end_ms": 2000,
            "source_video_key": "source_b.mp4",
            "source_start_ms": 1000,
            "source_end_ms": 2000,
        }
    ]
    sentences = [{"sentence_id": "t_0", "scene_id": "s_0", "text": "hello"}]
    audio = [{"sentence_id": "t_0", "status": "ok", "duration_ms": 800, "audio_path": "audio/task/t_0.mp3"}]
    captured: dict[str, object] = {}

    def fake_download(bucket: str, obj: str, path: str) -> None:
        _ = bucket, obj
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"x")

    def fake_single_pass(**kwargs: object) -> None:
        captured.update(kwargs)
        output = kwargs["output_path"]
        Path(output).write_bytes(b"final")

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.minio, "download_file", fake_download)
    monkeypatch.setattr(service.minio, "upload_file", lambda bucket, key, path, content_type: f"{bucket}/{key}")
    monkeypatch.setattr(service.minio, "upload_bytes", lambda *args, **kwargs: "")
    monkeypatch.setattr("skills.video_render.server.probe_duration_ms", lambda *_args, **_kwargs: 800)
    monkeypatch.setattr("skills.video_render.server.render_timeline_single_pass", fake_single_pass)

    result = await service.render_video("task", None, ["source_a.mp4", "source_b.mp4"], scenes, sentences, audio)
    assert result["timeline"][0]["source_video_key"] == "source_b.mp4"
    segments = captured["segments"]
    assert segments[0].source_start_ms == 1000
    assert segments[0].target_duration_ms == 1000


@pytest.mark.asyncio
async def test_render_video_fallbacks_to_legacy_when_single_pass_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VideoRenderService()
    service.allow_legacy_fallback = True
    service.pipeline_mode = "single_pass"

    scenes = [{"scene_id": "s_0", "start_ms": 0, "end_ms": 1000}]
    sentences = [{"sentence_id": "t_0", "scene_id": "s_0", "text": "hello"}]
    audio = [{"sentence_id": "t_0", "status": "ok", "duration_ms": 1000, "audio_path": "audio/task/t_0.mp3"}]

    def fake_download(bucket: str, obj: str, path: str) -> None:
        _ = bucket, obj
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"x")

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.minio, "download_file", fake_download)
    monkeypatch.setattr(service.minio, "upload_file", lambda bucket, key, path, content_type: f"{bucket}/{key}")
    monkeypatch.setattr(service.minio, "upload_bytes", lambda *args, **kwargs: "")
    monkeypatch.setattr("skills.video_render.server.probe_duration_ms", lambda *_args, **_kwargs: 1000)
    monkeypatch.setattr(
        "skills.video_render.server.render_timeline_single_pass",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr("skills.video_render.server.transcode_audio_to_wav", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "skills.video_render.server.cut_merge_segment",
        lambda **kwargs: Path(kwargs["output_path"]).write_bytes(b"segment"),
    )
    monkeypatch.setattr(
        "skills.video_render.server.concat_segments",
        lambda segment_paths, output_path: Path(output_path).write_bytes(b"final"),
    )

    result = await service.render_video("task", "source.mp4", None, scenes, sentences, audio)
    assert result["render_stats"]["pipeline_mode"] == "legacy_fallback"
