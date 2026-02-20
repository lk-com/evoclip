from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import dashscope


class VisionAdapter:
    def __init__(
        self,
        model: str,
        timeout_seconds: int = 30,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        if api_key:
            dashscope.api_key = api_key
        if base_url:
            dashscope.base_http_api_url = base_url

    async def analyze_frame(self, frame_path: Path) -> dict[str, Any]:
        """分析视频帧，返回场景描述和可见对象"""
        # DashScope SDK 此端点是同步的，在线程中运行
        def _call() -> dict[str, Any]:
            result = dashscope.MultiModalConversation.call(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"image": str(frame_path)},
                            {"text": "描述场景并列出可见对象，以 JSON 格式返回，包含 description 和 objects 键。"},
                        ],
                    }
                ],
            )
            if result.status_code != 200:
                raise RuntimeError(f"vision_status_{result.status_code}")
            content = result.output.choices[0]["message"]["content"]
            text = content[0].get("text") if content else ""
            return {"description": text or "", "objects": []}

        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=self.timeout_seconds)
