from __future__ import annotations

import asyncio
from typing import Any

import dashscope


class SpeechRecognizer:
    def __init__(
        self,
        model: str,
        timeout_seconds: int = 60,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        if api_key:
            dashscope.api_key = api_key
        if base_url:
            dashscope.base_http_api_url = base_url

    async def transcribe(self, audio_or_video_path: str) -> list[dict[str, Any]]:
        """转录音频或视频文件"""
        def _call() -> list[dict[str, Any]]:
            task_response = dashscope.audio.asr.Transcription.async_call(model=self.model, file_urls=[audio_or_video_path])
            if task_response.status_code != 200:
                raise RuntimeError(f"asr_status_{task_response.status_code}")
            wait_response = dashscope.audio.asr.Transcription.wait(task=task_response.output.task_id)
            if wait_response.status_code != 200:
                raise RuntimeError(f"asr_wait_status_{wait_response.status_code}")
            return wait_response.output.get("sentences", [])

        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=self.timeout_seconds)
