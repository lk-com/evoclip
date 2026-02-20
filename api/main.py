from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes.events import router as events_router
from api.routes.tasks import router as tasks_router
from store.database import DatabaseUnavailableError

app = FastAPI(title="EvoClip API", version="0.1.0")  # 创建 FastAPI 应用实例
app.include_router(tasks_router)
app.include_router(events_router)


@app.exception_handler(DatabaseUnavailableError)
async def handle_database_unavailable(_request: Request, exc: DatabaseUnavailableError):
    """处理数据库不可用异常"""
    return JSONResponse(status_code=503, content={"detail": str(exc)})

web_dist = Path("web/dist")
if web_dist.exists():
    # 挂载前端静态文件
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")
