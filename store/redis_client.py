from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis


class RedisStore:
    """Redis 存储客户端"""

    def __init__(self, redis_url: str, task_prefix: str, sse_channel_prefix: str, session_ttl: int, progress_ttl: int) -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.task_prefix = task_prefix
        self.sse_channel_prefix = sse_channel_prefix
        self.session_ttl = session_ttl
        self.progress_ttl = progress_ttl

    def queue_key(self) -> str:
        """获取队列键"""
        return f"{self.task_prefix}:queue"

    def task_key(self, task_id: str) -> str:
        """获取任务元数据键"""
        return f"{self.task_prefix}:meta:{task_id}"

    def progress_key(self, task_id: str) -> str:
        """获取进度键"""
        return f"{self.task_prefix}:progress:{task_id}"

    def sse_channel(self, task_id: str) -> str:
        """获取 SSE 频道名"""
        return f"{self.sse_channel_prefix}:{task_id}"

    async def enqueue_task(self, task_id: str) -> None:
        """将任务加入队列"""
        await self.redis.rpush(self.queue_key(), task_id)

    async def set_task_meta(self, task_id: str, payload: dict[str, Any]) -> None:
        """设置任务元数据"""
        await self.redis.set(self.task_key(task_id), json.dumps(payload), ex=self.session_ttl)

    async def set_progress(self, task_id: str, payload: dict[str, Any]) -> None:
        """设置任务进度"""
        await self.redis.set(self.progress_key(task_id), json.dumps(payload), ex=self.progress_ttl)

    async def publish_event(self, task_id: str, payload: dict[str, Any]) -> None:
        """发布事件到 SSE 频道"""
        await self.redis.publish(self.sse_channel(task_id), json.dumps(payload, ensure_ascii=False))
