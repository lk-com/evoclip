from __future__ import annotations

import asyncio

from config import load_settings
from store.redis_client import RedisStore


async def main() -> None:
    """主函数"""
    settings = load_settings()
    app_cfg = settings.app
    store = RedisStore(
        redis_url=settings.redis["url"],
        task_prefix=app_cfg["task_queue_prefix"],
        sse_channel_prefix=app_cfg["sse_channel_prefix"],
        session_ttl=app_cfg["session_ttl_seconds"],
        progress_ttl=app_cfg["progress_ttl_seconds"],
    )
    await store.redis.set(f"{store.task_prefix}:status", "ready", ex=store.session_ttl)
    await store.redis.close()


if __name__ == "__main__":
    asyncio.run(main())
