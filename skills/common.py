from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from config import Settings, load_settings

T = TypeVar("T")


@dataclass
class RetryPolicy:
    retries: int
    delays: tuple[float, ...]


async def retry_async(fn: Callable[[], Awaitable[T]], policy: RetryPolicy) -> T:
    """异步重试函数"""
    last_exc: Exception | None = None
    for index in range(policy.retries):
        try:
            return await fn()
        except Exception as exc:  # 通过测试覆盖
            last_exc = exc
            if index >= policy.retries - 1:
                break
            delay = policy.delays[min(index, len(policy.delays) - 1)]
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


def get_settings() -> Settings:
    return load_settings()


def get_credential(
    settings: Settings,
    name: str,
    fallback_name: str | None = None,
) -> str | None:
    """获取凭证信息，支持回退选项"""
    credentials = settings.data.get("credentials", {})
    value = str(credentials.get(name, "")).strip()
    if value:
        return value
    if fallback_name:
        fallback = str(credentials.get(fallback_name, "")).strip()
        if fallback:
            return fallback
    return None


def parse_json_payload(text: str) -> object:
    """解析 JSON 负载，支持 Markdown 代码块格式"""
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw)
