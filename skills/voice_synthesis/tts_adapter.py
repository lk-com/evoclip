from __future__ import annotations

import asyncio
import base64
import inspect
from http import HTTPStatus
from pathlib import Path
import time
from typing import Any

import httpx
from openai import AsyncOpenAI

try:
    import dashscope
except Exception:  # pragma: no cover
    dashscope = None

try:
    from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer, VoiceEnrollmentService
except Exception:  # pragma: no cover
    AudioFormat = None
    SpeechSynthesizer = None
    VoiceEnrollmentService = None


class TTSAdapter:
    def __init__(
        self,
        provider: str,
        openai_model: str,
        volcengine_voice: str,
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        dashscope_model: str = "cosyvoice-v3-plus",
        dashscope_voice: str = "longxiaochun_v2",
        dashscope_api_key: str | None = None,
        dashscope_base_url: str | None = None,
    ) -> None:
        self.provider = provider
        self.openai_model = openai_model
        self.volcengine_voice = volcengine_voice
        self.dashscope_model = dashscope_model
        self.dashscope_voice = dashscope_voice
        self.dashscope_api_key = dashscope_api_key
        if dashscope is not None:
            if dashscope_base_url:
                dashscope.base_http_api_url = dashscope_base_url
            if dashscope_api_key:
                dashscope.api_key = dashscope_api_key
        self.openai_client: AsyncOpenAI | None = None
        if self.provider == "openai":
            client_kwargs: dict[str, str] = {}
            if openai_api_key:
                client_kwargs["api_key"] = openai_api_key
            if openai_base_url:
                client_kwargs["base_url"] = openai_base_url
            self.openai_client = AsyncOpenAI(**client_kwargs)

    async def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> None:
        if self.provider == "openai":
            await self._synthesize_openai(text, output_path)
        elif self.provider in {"dashscope", "dashscope_clone"}:
            await self._synthesize_dashscope(text, output_path, voice=voice)
        else:
            await self._synthesize_volcengine(text, output_path)

    async def _synthesize_openai(self, text: str, output_path: Path) -> None:
        if self.openai_client is None:
            raise RuntimeError("openai_client_not_initialized")
        response = await self.openai_client.audio.speech.create(model=self.openai_model, voice="alloy", input=text)
        output_path.write_bytes(response.read())

    async def _synthesize_volcengine(self, text: str, output_path: Path) -> None:
        """使用火山引擎合成语音"""
        # 使用占位端点；在实际部署中替换为区域特定的 URL
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://openspeech.bytedanceapi.com/api/v1/tts",
                json={"voice_type": self.volcengine_voice, "text": text},
            )
            resp.raise_for_status()
            payload = resp.json()
            audio_b64 = payload.get("data")
            if not audio_b64:
                raise RuntimeError("invalid_tts_response")
            output_path.write_bytes(base64.b64decode(audio_b64))
            await asyncio.sleep(0)

    async def _synthesize_dashscope(self, text: str, output_path: Path, voice: str | None = None) -> None:
        """使用 DashScope 合成语音"""
        if SpeechSynthesizer is None:
            raise RuntimeError("dashscope_sdk_unavailable")
        if not self.dashscope_api_key:
            raise RuntimeError("dashscope_api_key_missing")

        resolved_voice = voice or self.dashscope_voice
        if self._supports_dashscope_new_call_api():
            # 较新的 SDK 风格：带显式 kwargs 的类级调用
            result = await asyncio.to_thread(
                SpeechSynthesizer.call,
                model=self.dashscope_model,
                voice=resolved_voice,
                text=text,
                api_key=self.dashscope_api_key,
                format="mp3",
            )
        else:
            # 较旧的 SDK 风格：实例方法调用(self, text, timeout_millis=None)
            result = await asyncio.to_thread(
                self._synthesize_dashscope_legacy_sync,
                text,
                resolved_voice,
            )

        if isinstance(result, (bytes, bytearray)):
            output_path.write_bytes(bytes(result))
            return

        status_code = getattr(result, "status_code", None)
        if status_code != HTTPStatus.OK:
            code = self._extract_value(result, "code")
            message = self._extract_value(result, "message") or self._extract_value(result, "error_message")
            details = [str(status_code)]
            if code:
                details.append(str(code))
            if message:
                details.append(str(message))
            raise RuntimeError(f"dashscope_tts_failed:{':'.join(details)}")

        audio_payload = self._extract_audio_data(result)
        output_path.write_bytes(audio_payload)

    def _synthesize_dashscope_legacy_sync(self, text: str, voice: str) -> bytes:
        """使用旧版 DashScope SDK 同步合成语音"""
        assert SpeechSynthesizer is not None
        synth_kwargs: dict[str, Any] = {"model": self.dashscope_model, "voice": voice}
        if AudioFormat is not None and hasattr(AudioFormat, "MP3_24000HZ_MONO_256KBPS"):
            synth_kwargs["format"] = AudioFormat.MP3_24000HZ_MONO_256KBPS
        synthesizer = SpeechSynthesizer(**synth_kwargs)
        try:
            result = synthesizer.call(text=text)
        except TypeError:
            result = synthesizer.call(text)
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
        audio_payload = self._extract_audio_data(result)
        return audio_payload

    def _supports_dashscope_new_call_api(self) -> bool:
        """检查是否支持新版 DashScope 调用 API"""
        assert SpeechSynthesizer is not None
        try:
            sig = inspect.signature(SpeechSynthesizer.call)
        except (TypeError, ValueError):
            # 未知签名的保守默认值
            return True
        if "model" in sig.parameters:
            return True
        return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values())

    async def clone_voice(
        self,
        audio_url: str,
        prefix: str,
        poll_interval_seconds: int = 2,
        max_wait_seconds: int = 60,
        language_hint: str | None = None,
    ) -> str:
        """克隆语音"""
        if VoiceEnrollmentService is None:
            raise RuntimeError("dashscope_sdk_unavailable")
        if not self.dashscope_api_key:
            raise RuntimeError("dashscope_api_key_missing")

        return await asyncio.to_thread(
            self._clone_voice_sync,
            audio_url,
            prefix,
            poll_interval_seconds,
            max_wait_seconds,
            language_hint,
        )

    def _clone_voice_sync(
        self,
        audio_url: str,
        prefix: str,
        poll_interval_seconds: int,
        max_wait_seconds: int,
        language_hint: str | None,
    ) -> str:
        """同步克隆语音"""
        assert VoiceEnrollmentService is not None
        service = VoiceEnrollmentService()
        create_kwargs: dict[str, Any] = {
            "target_model": self.dashscope_model,
            "prefix": prefix,
            "url": audio_url,
        }
        if language_hint:
            create_kwargs["language_hints"] = [language_hint]
        try:
            result = service.create_voice(**create_kwargs)
        except Exception as exc:
            raise RuntimeError(f"dashscope_clone_failed:{exc}") from exc

        # 旧版 SDK 返回纯 voice_id 字符串；新版变体可能返回类似响应的对象/字典
        voice_id = self._extract_voice_id(result)
        if not voice_id and self._is_dashscope_result_failure(result):
            raise RuntimeError(f"dashscope_clone_failed:{self._dashscope_error_details(result)}")
        if not voice_id:
            result_type = type(result).__name__
            raise RuntimeError(f"dashscope_voice_id_missing:type={result_type},payload={self._safe_preview(result)}")
        voice_id = str(voice_id)

        if max_wait_seconds <= 0:
            return voice_id

        deadline = time.monotonic() + max_wait_seconds
        while time.monotonic() < deadline:
            query = self._query_voice_status(service, voice_id)
            query_status = self._extract_value(getattr(query, "output", None), "status")
            if query_status is None:
                query_status = self._extract_value(query, "status")
            if query_status is None:
                return voice_id
            status_text = str(query_status).upper()
            if status_text in {"READY", "SUCCESS", "SUCCEEDED", "AVAILABLE"}:
                return voice_id
            if status_text in {"FAILED", "ERROR"}:
                raise RuntimeError(f"dashscope_clone_status:{query_status}")
            time.sleep(max(1, poll_interval_seconds))

        return voice_id

    def _extract_audio_data(self, result: Any) -> bytes:
        """从 DashScope 响应中提取音频数据"""
        # DashScope SDK 可能返回带有属性的响应对象或类似字典的访问方式
        # 尝试常见模式来提取音频负载
        output = getattr(result, "output", None)
        audio = self._extract_value(output, "audio")
        if audio is None:
            raise RuntimeError("dashscope_tts_no_audio_in_output")
        # 某些 SDK 版本返回 base64 编码字符串；其他版本可能直接返回字节
        if isinstance(audio, bytes):
            return audio
        if isinstance(audio, str):
            return base64.b64decode(audio)
        raise RuntimeError("dashscope_tts_unexpected_audio_type")

    def _extract_value(self, obj: Any, key: str) -> Any:
        """从对象中提取值，支持字典和属性访问"""
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _is_dashscope_result_failure(self, result: Any) -> bool:
        """检查 DashScope 结果是否为失败状态"""
        status_code = self._extract_value(result, "status_code")
        if status_code is not None:
            try:
                return int(status_code) != int(HTTPStatus.OK)
            except (TypeError, ValueError):
                return str(status_code).strip() not in {"200", "OK", "ok"}

        code = self._extract_value(result, "code")
        if code is not None:
            normalized = str(code).strip().upper()
            if normalized in {"OK", "SUCCESS", "0"}:
                return False
            return True

        message = self._extract_value(result, "message") or self._extract_value(result, "error_message")
        return bool(message)

    def _dashscope_error_details(self, result: Any) -> str:
        """提取 DashScope 错误详情"""
        parts: list[str] = []
        for key in ("status_code", "code", "message", "error_message", "request_id"):
            value = self._extract_value(result, key)
            if value is not None and str(value).strip():
                parts.append(f"{key}={value}")
        if not parts:
            return "unknown"
        return ",".join(parts)

    def _query_voice_status(self, service: Any, voice_id: str) -> Any:
        """查询语音克隆状态"""
        # SDK 签名因版本而异：
        # - query_voice(voice=...)
        # - query_voice(voice_id=...)
        # - query_voice(<voice_id>)
        try:
            return service.query_voice(voice=voice_id)
        except TypeError:
            try:
                return service.query_voice(voice_id=voice_id)
            except TypeError:
                return service.query_voice(voice_id)

    def _extract_voice_id(self, result: Any) -> str | None:
        """从结果中提取语音 ID"""
        if isinstance(result, str):
            stripped = result.strip()
            return stripped or None

        output = self._extract_value(result, "output")
        for key in ("voice_id", "voice", "id"):
            value = self._extract_value(output, key)
            if value is not None and str(value).strip():
                return str(value).strip()

        for key in ("voice_id", "voice", "id"):
            value = self._extract_value(result, key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    def _safe_preview(self, value: Any, limit: int = 240) -> str:
        """安全地预览值，限制长度"""
        text = repr(value)
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."
