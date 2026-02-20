from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any


ToolHandler = Callable[..., Awaitable[dict[str, Any]]]  # 工具处理函数类型


class MCPClientPool:
    """MCP 客户端连接池"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolHandler] = {}
        self._last_seen: dict[str, float] = {}

    def register_tool(self, name: str, handler: ToolHandler) -> None:
        """注册工具"""
        self._tools[name] = handler
        self._last_seen[name] = time.time()

    async def call_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """调用工具"""
        if name not in self._tools:
            raise RuntimeError(f"tool_not_found:{name}")
        self._last_seen[name] = time.time()
        return await self._tools[name](**kwargs)

    def stale_tools(self, timeout_seconds: int) -> list[str]:
        """获取过期工具列表"""
        now = time.time()
        return [name for name, ts in self._last_seen.items() if now - ts > timeout_seconds]
