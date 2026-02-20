from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO

from fastapi.testclient import TestClient

from api.main import app
from api.routes import tasks as task_routes
from store.database import DatabaseUnavailableError


class _TaskModel:
    def __init__(self, task_id: str, input_video_key: str, product_description: str) -> None:
        now = datetime.now(timezone.utc)
        self.id = task_id
        self.status = "queued"
        self.progress = 0
        self.retry_count = 0
        self.input_video_key = input_video_key
        self.product_description = product_description
        self.output_video_key = None
        self.checkpoint = None
        self.detail = {}
        self.created_at = now
        self.updated_at = now


class _FakeSession:
    def __init__(self, db: "_FakeDB") -> None:
        self.db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def add(self, task: _TaskModel) -> None:
        self.db.tasks[task.id] = task

    async def get(self, model, task_id: str):
        return self.db.tasks.get(task_id)


class _FakeDB:
    def __init__(self) -> None:
        self.tasks: dict[str, _TaskModel] = {}

    @asynccontextmanager
    async def session(self):
        yield _FakeSession(self)


class _UnavailableDB:
    @asynccontextmanager
    async def session(self):
        raise DatabaseUnavailableError(
            "PostgreSQL database is missing. Run `python scripts/init_db.py --create-database` first."
        )
        yield


class _FakeMinio:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def ensure_bucket(self, _bucket: str) -> None:
        return None

    def upload_bytes(self, bucket: str, object_key: str, data: bytes, content_type: str = "") -> str:
        self.objects[(bucket, object_key)] = data
        return f"{bucket}/{object_key}"

    def download_bytes(self, bucket: str, object_key: str) -> bytes:
        return self.objects[(bucket, object_key)]


class _FakeRedis:
    def __init__(self) -> None:
        self.queue: list[str] = []
        self.events: list[dict] = []

    async def enqueue_task(self, task_id: str) -> None:
        self.queue.append(task_id)

    async def publish_event(self, task_id: str, payload: dict) -> None:
        self.events.append({"task_id": task_id, **payload})


class _FakeSettings:
    app = {
        "task_queue_prefix": "test:task",
        "session_ttl_seconds": 3600,
        "progress_ttl_seconds": 3600,
        "sse_channel_prefix": "test:sse",
    }
    redis = {"url": "redis://localhost:6379/0"}
    postgres = {"dsn": "postgresql+asyncpg://postgres:postgres@localhost:5432/test"}
    storage = {
        "minio": {
            "buckets": {"videos": "videos", "audio": "audio", "intermediate": "intermediate", "output": "output"}
        }
    }


def make_client() -> tuple[TestClient, _FakeDB, _FakeMinio, _FakeRedis]:
    fake_db = _FakeDB()
    fake_minio = _FakeMinio()
    fake_redis = _FakeRedis()

    app.dependency_overrides[task_routes.get_settings] = lambda: _FakeSettings()
    app.dependency_overrides[task_routes.get_db] = lambda: fake_db
    app.dependency_overrides[task_routes.get_minio] = lambda: fake_minio
    app.dependency_overrides[task_routes.get_redis] = lambda: fake_redis

    return TestClient(app), fake_db, fake_minio, fake_redis


def test_create_and_get_task() -> None:
    client, fake_db, _fake_minio, fake_redis = make_client()
    with client:
        response = client.post(
            "/tasks",
            files={"video": ("demo.mp4", BytesIO(b"video"), "video/mp4")},
            data={"product_description": "good product"},
        )

        assert response.status_code == 200
        task_id = response.json()["task_id"]
        assert task_id in fake_db.tasks
        assert fake_redis.queue == [task_id]
        assert fake_db.tasks[task_id].detail["input_video_keys"]

        read_response = client.get(f"/tasks/{task_id}")
        assert read_response.status_code == 200
        assert read_response.json()["status"] == "queued"


def test_create_task_accepts_multiple_videos() -> None:
    client, fake_db, _fake_minio, _fake_redis = make_client()
    with client:
        response = client.post(
            "/tasks",
            files=[
                ("videos", ("demo_1.mp4", BytesIO(b"video-1"), "video/mp4")),
                ("videos", ("demo_2.mp4", BytesIO(b"video-2"), "video/mp4")),
            ],
            data={"product_description": "good product"},
        )

    assert response.status_code == 200
    task_id = response.json()["task_id"]
    task = fake_db.tasks[task_id]
    assert len(task.detail["input_video_keys"]) == 2
    assert task.input_video_key == task.detail["input_video_keys"][0]


def test_create_task_rejects_empty_description() -> None:
    client, _fake_db, _fake_minio, _fake_redis = make_client()
    with client:
        response = client.post(
            "/tasks",
            files={"video": ("demo.mp4", BytesIO(b"video"), "video/mp4")},
            data={"product_description": "   "},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "empty_product_description"


def test_create_task_returns_503_when_database_missing() -> None:
    fake_minio = _FakeMinio()
    fake_redis = _FakeRedis()
    app.dependency_overrides[task_routes.get_settings] = lambda: _FakeSettings()
    app.dependency_overrides[task_routes.get_db] = lambda: _UnavailableDB()
    app.dependency_overrides[task_routes.get_minio] = lambda: fake_minio
    app.dependency_overrides[task_routes.get_redis] = lambda: fake_redis

    with TestClient(app) as client:
        response = client.post(
            "/tasks",
            files={"video": ("demo.mp4", BytesIO(b"video"), "video/mp4")},
            data={"product_description": "good product"},
        )

    assert response.status_code == 503
    assert "init_db.py --create-database" in response.json()["detail"]


def test_retry_failed_task_success() -> None:
    """成功重试一个失败的任务"""
    client, fake_db, _fake_minio, fake_redis = make_client()

    # 先创建一个任务
    with client:
        response = client.post(
            "/tasks",
            files={"video": ("demo.mp4", BytesIO(b"video"), "video/mp4")},
            data={"product_description": "good product"},
        )
        task_id = response.json()["task_id"]

        # 模拟任务失败并设置 checkpoint
        task = fake_db.tasks[task_id]
        task.status = "failed"
        task.checkpoint = "video-analysis"
        task.detail = {"error": "some error", "video-analysis": {"result": "data"}}

        # 重试
        retry_response = client.post(f"/tasks/{task_id}/retry")
        assert retry_response.status_code == 200
        assert retry_response.json()["task_id"] == task_id

        # 验证状态已重置
        assert fake_db.tasks[task_id].status == "queued"
        assert fake_db.tasks[task_id].retry_count == 1
        assert "error" not in fake_db.tasks[task_id].detail

        # 验证已入队
        assert task_id in fake_redis.queue


def test_retry_nonexistent_task() -> None:
    """重试不存在的任务应返回 404"""
    client, _fake_db, _fake_minio, _fake_redis = make_client()
    with client:
        response = client.post("/tasks/nonexistent/retry")
        assert response.status_code == 404
        assert response.json()["detail"] == "task_not_found"


def test_retry_non_failed_task() -> None:
    """重试非失败状态的任务应返回 400"""
    client, fake_db, _fake_minio, _fake_redis = make_client()
    with client:
        response = client.post(
            "/tasks",
            files={"video": ("demo.mp4", BytesIO(b"video"), "video/mp4")},
            data={"product_description": "good product"},
        )
        task_id = response.json()["task_id"]

        # 任务状态是 queued，不是 failed
        retry_response = client.post(f"/tasks/{task_id}/retry")
        assert retry_response.status_code == 400
        assert retry_response.json()["detail"] == "task_not_failed"


def test_retry_task_without_checkpoint() -> None:
    """重试没有 checkpoint 的任务应返回 400"""
    client, fake_db, _fake_minio, _fake_redis = make_client()
    with client:
        response = client.post(
            "/tasks",
            files={"video": ("demo.mp4", BytesIO(b"video"), "video/mp4")},
            data={"product_description": "good product"},
        )
        task_id = response.json()["task_id"]

        # 手动设置为 failed 但没有 checkpoint
        task = fake_db.tasks[task_id]
        task.status = "failed"
        task.checkpoint = None

        retry_response = client.post(f"/tasks/{task_id}/retry")
        assert retry_response.status_code == 400
        assert retry_response.json()["detail"] == "no_checkpoint_available"


def test_retry_increments_count() -> None:
    """多次重试应递增 retry_count"""
    client, fake_db, _fake_minio, fake_redis = make_client()
    with client:
        response = client.post(
            "/tasks",
            files={"video": ("demo.mp4", BytesIO(b"video"), "video/mp4")},
            data={"product_description": "good product"},
        )
        task_id = response.json()["task_id"]

        # 设置为失败有 checkpoint
        task = fake_db.tasks[task_id]
        task.status = "failed"
        task.checkpoint = "video-analysis"
        task.retry_count = 2

        # 第一次重试
        client.post(f"/tasks/{task_id}/retry")
        assert fake_db.tasks[task_id].retry_count == 3

        # 再次设置为失败
        fake_db.tasks[task_id].status = "failed"

        # 第二次重试
        client.post(f"/tasks/{task_id}/retry")
        assert fake_db.tasks[task_id].retry_count == 4
