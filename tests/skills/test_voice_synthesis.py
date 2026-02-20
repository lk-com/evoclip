from __future__ import annotations

from pathlib import Path

import pytest

from skills.voice_synthesis.server import VoiceSynthesisService


@pytest.mark.asyncio
async def test_synthesize_voice_empty_input() -> None:
    service = VoiceSynthesisService()
    result = await service.synthesize_voice(task_id="t1", sentences=[])
    assert result["error"] == "empty_sentences"


@pytest.mark.asyncio
async def test_synthesize_voice_marks_failed_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VoiceSynthesisService()
    service.clone_from_video = False

    async def fail(*_: object, **__: object) -> None:
        raise RuntimeError("tts_down")

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.adapter, "synthesize", fail)

    result = await service.synthesize_voice(task_id="task", sentences=[{"sentence_id": "t_0", "text": "hello"}])
    assert result["audio_segments"][0]["status"] == "failed"
    assert result["error"] == "all_tts_failed"
    assert result["ok_count"] == 0
    assert result["failed_count"] == 1
    assert "tts_down" in result["audio_segments"][0]["error"]


@pytest.mark.asyncio
async def test_synthesize_voice_success(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VoiceSynthesisService()
    service.clone_from_video = False

    async def ok(text: str, output_path: Path, voice: str | None = None) -> None:
        _ = voice
        output_path.write_bytes(b"mock-mp3")

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service.adapter, "synthesize", ok)
    monkeypatch.setattr("skills.voice_synthesis.server.read_duration_ms", lambda *_: 1234)
    monkeypatch.setattr(service.minio, "upload_file", lambda bucket, key, path, content_type: f"{bucket}/{key}")

    result = await service.synthesize_voice(task_id="task", sentences=[{"sentence_id": "t_0", "text": "hello"}])
    assert result["audio_segments"][0]["duration_ms"] == 1234
    assert result["audio_segments"][0]["status"] == "ok"
    assert result["ok_count"] == 1
    assert result["failed_count"] == 0
    assert "error" not in result


def test_rewrite_public_url_rejects_private_host() -> None:
    service = VoiceSynthesisService()
    service.clone_public_base_url = None
    assert (
        service._rewrite_public_url(
            "http://192.168.31.220:9000/intermediate/task/clone_sample.wav?X-Amz-Signature=abc"
        )
        is None
    )


@pytest.mark.asyncio
async def test_resolve_voice_profile_fallback_when_clone_fails_non_strict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = VoiceSynthesisService()
    service.adapter.provider = "dashscope_clone"
    service.clone_audio_url = "https://example.com/clone.wav"
    service.clone_strict = False
    service.clone_fixed_voice_id = None

    async def fail_clone(*_: object, **__: object) -> str:
        raise RuntimeError("clone_failed")

    monkeypatch.setattr(service.adapter, "clone_voice", fail_clone)

    profile, fallback = await service._resolve_voice_profile(task_id="task", source_video_keys=[], working_dir=tmp_path)
    assert profile is None
    assert fallback is True


@pytest.mark.asyncio
async def test_synthesize_voice_sets_fallback_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VoiceSynthesisService()
    service.clone_from_video = True

    async def ok(text: str, output_path: Path, voice: str | None = None) -> None:
        _ = text, voice
        output_path.write_bytes(b"mock-mp3")

    async def fake_resolve(*_: object, **__: object) -> tuple[str | None, bool]:
        return None, True

    monkeypatch.setattr(service.minio, "ensure_bucket", lambda *_: None)
    monkeypatch.setattr(service, "_resolve_voice_profile", fake_resolve)
    monkeypatch.setattr(service.adapter, "synthesize", ok)
    monkeypatch.setattr("skills.voice_synthesis.server.read_duration_ms", lambda *_: 1234)
    monkeypatch.setattr(service.minio, "upload_file", lambda bucket, key, path, content_type: f"{bucket}/{key}")

    result = await service.synthesize_voice(task_id="task", sentences=[{"sentence_id": "t_0", "text": "hello"}])
    assert result["voice_profile_fallback"] is True


def test_prepare_clone_audio_url_uses_public_presign(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = VoiceSynthesisService()
    service.clone_public_base_url = "https://public.example.com"

    monkeypatch.setattr(service.minio, "download_file", lambda *_: None)
    monkeypatch.setattr(
        service,
        "_extract_clone_sample",
        lambda *_args, **_kwargs: _kwargs["output_audio"].write_bytes(b"wav"),
    )
    monkeypatch.setattr(service.minio, "upload_file", lambda *_args, **_kwargs: "intermediate/task/clone_sample.wav")

    captured: dict[str, object] = {}

    def presign(bucket: str, key: str, *, expires, public_base_url: str | None = None) -> str:
        captured["bucket"] = bucket
        captured["key"] = key
        captured["expires"] = expires
        captured["public_base_url"] = public_base_url
        return "https://public.example.com/intermediate/task/clone_sample.wav?signature=ok"

    monkeypatch.setattr(service.minio, "presigned_get_object", presign)

    url = service._prepare_clone_audio_url(
        task_id="task",
        source_video_keys=["source_0.mp4"],
        working_dir=tmp_path,
    )
    assert url == "https://public.example.com/intermediate/task/clone_sample.wav?signature=ok"
    assert captured["bucket"] == service.buckets["intermediate"]
    assert captured["key"] == "task/clone_sample.wav"
    assert captured["public_base_url"] == "https://public.example.com"


def test_prepare_clone_audio_url_fallbacks_to_rewrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = VoiceSynthesisService()
    service.clone_public_base_url = "https://public.example.com/minio"

    monkeypatch.setattr(service.minio, "download_file", lambda *_: None)
    monkeypatch.setattr(
        service,
        "_extract_clone_sample",
        lambda *_args, **_kwargs: _kwargs["output_audio"].write_bytes(b"wav"),
    )
    monkeypatch.setattr(service.minio, "upload_file", lambda *_args, **_kwargs: "intermediate/task/clone_sample.wav")

    calls: list[tuple[str | None, str]] = []

    def presign(bucket: str, key: str, *, expires, public_base_url: str | None = None) -> str:
        _ = bucket, key, expires
        if public_base_url:
            calls.append((public_base_url, "fail"))
            raise ValueError("public_base_url_with_path_not_supported")
        calls.append((public_base_url, "ok"))
        return "http://192.168.31.220:9000/intermediate/task/clone_sample.wav?signature=raw"

    monkeypatch.setattr(service.minio, "presigned_get_object", presign)
    monkeypatch.setattr(
        service,
        "_rewrite_public_url",
        lambda raw: raw.replace("http://192.168.31.220:9000", "https://public.example.com/minio"),
    )

    url = service._prepare_clone_audio_url(
        task_id="task",
        source_video_keys=["source_0.mp4"],
        working_dir=tmp_path,
    )
    assert url == "https://public.example.com/minio/intermediate/task/clone_sample.wav?signature=raw"
    assert calls == [("https://public.example.com/minio", "fail"), (None, "ok")]
