from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from config import load_settings
from store.redis_client import RedisStore

router = APIRouter(prefix="/tasks", tags=["events"])


def get_settings():
    return load_settings()


def get_redis(settings=Depends(get_settings)) -> RedisStore:
    app_cfg = settings.app
    return RedisStore(
        redis_url=settings.redis["url"],
        task_prefix=app_cfg["task_queue_prefix"],
        sse_channel_prefix=app_cfg["sse_channel_prefix"],
        session_ttl=app_cfg["session_ttl_seconds"],
        progress_ttl=app_cfg["progress_ttl_seconds"],
    )


@router.get("/{task_id}/events")
async def stream_task_events(task_id: str, redis: RedisStore = Depends(get_redis)):
    """流式传输任务事件（SSE）"""
    pubsub = redis.redis.pubsub()
    await pubsub.subscribe(redis.sse_channel(task_id))

    async def event_generator():
        """生成事件流"""
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    yield f"data: {message['data']}\n\n"
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(redis.sse_channel(task_id))
            await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
