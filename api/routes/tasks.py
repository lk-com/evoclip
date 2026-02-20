from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from api.schemas.task import TaskCreateResponse, TaskReadResponse
from config import load_settings
from store.database import Database
from store.minio_client import MinioStore
from store.models import Task, TaskStatus
from store.redis_client import RedisStore

router = APIRouter(prefix="/tasks", tags=["tasks"])  # 任务路由


def get_settings():
    """获取应用配置"""
    return load_settings()


def get_db(settings=Depends(get_settings)) -> Database:
    """获取数据库连接"""
    return Database(settings.postgres["dsn"])


def get_minio(settings=Depends(get_settings)) -> MinioStore:
    """获取 MinIO 存储客户端"""
    cfg = settings.storage["minio"]
    return MinioStore(cfg["endpoint"], cfg["access_key"], cfg["secret_key"], cfg.get("secure", False))


def get_redis(settings=Depends(get_settings)) -> RedisStore:
    """获取 Redis 存储客户端"""
    app_cfg = settings.app
    return RedisStore(
        redis_url=settings.redis["url"],
        task_prefix=app_cfg["task_queue_prefix"],
        sse_channel_prefix=app_cfg["sse_channel_prefix"],
        session_ttl=app_cfg["session_ttl_seconds"],
        progress_ttl=app_cfg["progress_ttl_seconds"],
    )


@router.post("", response_model=TaskCreateResponse)
async def create_task(
    video: UploadFile | None = File(None),
    videos: list[UploadFile] | None = File(None),
    voice_samples: list[UploadFile] | None = File(None),
    product_description: str = Form(...),
    db: Database = Depends(get_db),
    minio: MinioStore = Depends(get_minio),
    redis: RedisStore = Depends(get_redis),
    settings=Depends(get_settings),
) -> TaskCreateResponse:
    """创建新任务"""
    if not product_description.strip():
        raise HTTPException(status_code=400, detail="empty_product_description")

    uploaded_videos = [item for item in (videos or []) if item is not None]
    if not uploaded_videos and video is not None:
        uploaded_videos = [video]
    if not uploaded_videos:
        raise HTTPException(status_code=400, detail="empty_video_files")

    task_id = uuid.uuid4().hex
    buckets = settings.storage["minio"]["buckets"]
    minio.ensure_bucket(buckets["videos"])
    input_video_keys: list[str] = []
    for idx, uploaded in enumerate(uploaded_videos):
        suffix = Path(uploaded.filename or f"input_{idx}.mp4").suffix or ".mp4"
        object_key = f"{task_id}/source_{idx}{suffix}"
        data = uploaded.file.read()
        minio.upload_bytes(buckets["videos"], object_key, data, content_type=uploaded.content_type or "video/mp4")
        input_video_keys.append(object_key)

    voice_sample_keys: list[str] = []
    if voice_samples:
        for idx, sample in enumerate(voice_samples):
            suffix = Path(sample.filename or f"voice_sample_{idx}.mp4").suffix or ".mp4"
            sample_key = f"{task_id}/voice_sample_{idx}{suffix}"
            payload = sample.file.read()
            minio.upload_bytes(
                buckets["videos"],
                sample_key,
                payload,
                content_type=sample.content_type or "video/mp4",
            )
            voice_sample_keys.append(sample_key)

    async with db.session() as session:
        detail = {"input_video_keys": input_video_keys}
        if voice_sample_keys:
            detail["voice_sample_keys"] = voice_sample_keys
        task = Task(
            id=task_id,
            status=TaskStatus.queued,
            progress=0,
            input_video_key=input_video_keys[0],
            product_description=product_description.strip(),
            detail=detail,
        )
        session.add(task)

    await redis.enqueue_task(task_id)
    await redis.publish_event(task_id, {"status": "queued", "progress": 0})
    return TaskCreateResponse(task_id=task_id)


@router.get("/{task_id}", response_model=TaskReadResponse)
async def get_task(task_id: str, db: Database = Depends(get_db)) -> TaskReadResponse:
    async with db.session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task_not_found")
        return TaskReadResponse.model_validate(task, from_attributes=True)


@router.get("/{task_id}/download")
async def download_task_video(
    task_id: str,
    db: Database = Depends(get_db),
    minio: MinioStore = Depends(get_minio),
):
    async with db.session() as session:
        task = await session.get(Task, task_id)
        if not task or not task.output_video_key:
            raise HTTPException(status_code=404, detail="video_not_ready")

    bucket, object_key = task.output_video_key.split("/", 1)
    payload = minio.download_bytes(bucket, object_key)
    return StreamingResponse(iter([payload]), media_type="video/mp4")


@router.post("/{task_id}/retry", response_model=TaskCreateResponse)
async def retry_task(
    task_id: str,
    db: Database = Depends(get_db),
    redis: RedisStore = Depends(get_redis),
) -> TaskCreateResponse:
    async with db.session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task_not_found")

        if task.status != TaskStatus.failed:
            raise HTTPException(status_code=400, detail="task_not_failed")

        if not task.checkpoint:
            raise HTTPException(status_code=400, detail="no_checkpoint_available")

        # 重置任务状态为排队中
        task.status = TaskStatus.queued
        task.retry_count = (task.retry_count or 0) + 1

        # 清除错误信息，保留其他 detail 数据
        detail = dict(task.detail or {})
        detail.pop("error", None)
        task.detail = detail

    # 重新将任务加入队列
    await redis.enqueue_task(task_id)
    await redis.publish_event(task_id, {"status": "queued", "progress": task.progress, "retry_count": task.retry_count})

    return TaskCreateResponse(task_id=task_id)
