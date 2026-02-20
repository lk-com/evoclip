from __future__ import annotations

from pathlib import Path

import pytest

from skills.voice_synthesis import tts_adapter
from skills.voice_synthesis.tts_adapter import TTSAdapter


@pytest.mark.asyncio
async def test_synthesize_dashscope_legacy_sdk_compat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(tts_adapter.asyncio, "to_thread", fake_to_thread)

    class LegacySpeechSynthesizer:
        def __init__(self, model: str, voice: str, **kwargs: object) -> None:
            self.model = model
            self.voice = voice

        def call(self, text: str, timeout_millis: int | None = None) -> bytes:
            _ = timeout_millis
            return f"{self.model}:{self.voice}:{text}".encode("utf-8")

    monkeypatch.setattr(tts_adapter, "SpeechSynthesizer", LegacySpeechSynthesizer)

    adapter = TTSAdapter(
        provider="dashscope",
        openai_model="",
        volcengine_voice="",
        dashscope_api_key="k",
        dashscope_model="m",
        dashscope_voice="v",
    )

    out = tmp_path / "legacy.mp3"
    await adapter._synthesize_dashscope("hello", out)
    assert out.read_bytes() == b"m:v:hello"


@pytest.mark.asyncio
async def test_synthesize_dashscope_new_sdk_compat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(tts_adapter.asyncio, "to_thread", fake_to_thread)

    class FakeResult:
        def __init__(self) -> None:
            self.status_code = 200
            self.output = {"audio": {"data": b"audio-bytes"}}

    class NewSpeechSynthesizer:
        @staticmethod
        def call(**kwargs: object) -> FakeResult:
            assert kwargs["model"] == "m"
            assert kwargs["voice"] == "v"
            assert kwargs["text"] == "hello"
            return FakeResult()

    monkeypatch.setattr(tts_adapter, "SpeechSynthesizer", NewSpeechSynthesizer)

    adapter = TTSAdapter(
        provider="dashscope",
        openai_model="",
        volcengine_voice="",
        dashscope_api_key="k",
        dashscope_model="m",
        dashscope_voice="v",
    )

    out = tmp_path / "new.mp3"
    await adapter._synthesize_dashscope("hello", out)
    assert out.read_bytes() == b"audio-bytes"


def test_clone_voice_accepts_missing_status_code_when_voice_id_present(monkeypatch: pytest.MonkeyPatch) -> None:
    class CreateResult:
        status_code = None
        output = {"voice_id": "voice_123"}

    class FakeVoiceEnrollmentService:
        def create_voice(self, **kwargs: object) -> CreateResult:
            assert kwargs["prefix"] == "evoclip"
            assert kwargs["url"] == "https://example.com/clone.wav"
            return CreateResult()

        def query_voice(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            return {"output": {"status": "READY"}}

    monkeypatch.setattr(tts_adapter, "VoiceEnrollmentService", FakeVoiceEnrollmentService)

    adapter = TTSAdapter(
        provider="dashscope_clone",
        openai_model="",
        volcengine_voice="",
        dashscope_api_key="k",
        dashscope_model="m",
        dashscope_voice="v",
    )

    voice_id = adapter._clone_voice_sync(
        audio_url="https://example.com/clone.wav",
        prefix="evoclip",
        poll_interval_seconds=1,
        max_wait_seconds=0,
        language_hint=None,
    )
    assert voice_id == "voice_123"


def test_clone_voice_reports_rich_error_when_create_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    class CreateResult:
        status_code = None
        code = "InvalidParameter"
        message = "url is not reachable"
        request_id = "req-1"
        output = None

    class FakeVoiceEnrollmentService:
        def create_voice(self, **kwargs: object) -> CreateResult:
            _ = kwargs
            return CreateResult()

        def query_voice(self, **kwargs: object) -> dict[str, object]:
            _ = kwargs
            return {"output": {"status": "READY"}}

    monkeypatch.setattr(tts_adapter, "VoiceEnrollmentService", FakeVoiceEnrollmentService)

    adapter = TTSAdapter(
        provider="dashscope_clone",
        openai_model="",
        volcengine_voice="",
        dashscope_api_key="k",
        dashscope_model="m",
        dashscope_voice="v",
    )

    with pytest.raises(RuntimeError) as exc:
        adapter._clone_voice_sync(
            audio_url="https://example.com/clone.wav",
            prefix="evoclip",
            poll_interval_seconds=1,
            max_wait_seconds=0,
            language_hint=None,
        )
    assert "dashscope_clone_failed:" in str(exc.value)
    assert "code=InvalidParameter" in str(exc.value)
    assert "message=url is not reachable" in str(exc.value)


def test_clone_voice_legacy_sdk_string_result_and_query_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeVoiceEnrollmentService:
        def create_voice(self, **kwargs: object) -> str:
            assert kwargs["prefix"] == "evoclip"
            return "legacy_voice_1"

        def query_voice(self, voice_id: str) -> dict[str, object]:
            assert voice_id == "legacy_voice_1"
            return {"status": "READY"}

    monkeypatch.setattr(tts_adapter, "VoiceEnrollmentService", FakeVoiceEnrollmentService)

    adapter = TTSAdapter(
        provider="dashscope_clone",
        openai_model="",
        volcengine_voice="",
        dashscope_api_key="k",
        dashscope_model="m",
        dashscope_voice="v",
    )

    voice_id = adapter._clone_voice_sync(
        audio_url="https://example.com/clone.wav",
        prefix="evoclip",
        poll_interval_seconds=1,
        max_wait_seconds=2,
        language_hint=None,
    )
    assert voice_id == "legacy_voice_1"
