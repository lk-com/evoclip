from __future__ import annotations

import argparse
import asyncio
import re

import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from config import load_settings
from store.models import Base


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="初始化 EvoClip PostgreSQL 数据库")
    parser.add_argument(
        "--create-database",
        action="store_true",
        help="当目标 PostgreSQL 数据库不存在时创建它",
    )
    return parser.parse_args()


def _quote_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"unsupported database name for auto-create: {name!r}")
    return f'"{name}"'


async def ensure_database_exists(dsn: str) -> None:
    """确保数据库存在，不存在则创建"""
    url = make_url(dsn)
    database_name = url.database
    if not database_name:
        raise ValueError("postgres.dsn must include a database name")

    admin_database = "postgres" if database_name != "postgres" else "template1"
    # 构建 asyncpg 兼容的 DSN: postgresql://user:pass@host:port/db
    # asyncpg 只接受 "postgresql" 或 "postgres" 协议，不接受 "postgresql+asyncpg"
    # 使用 render_as_string(hide_password=False) 获取实际密码
    admin_url = url.set(drivername="postgresql", database=admin_database)
    conn = await asyncpg.connect(admin_url.render_as_string(hide_password=False))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database_name)
        if exists:
            return
        await conn.execute(f"CREATE DATABASE {_quote_ident(database_name)}")
    finally:
        await conn.close()


async def ensure_runtime_compat_columns(dsn: str) -> None:
    """为没有完整迁移工具的旧部署回填列"""
    url = make_url(dsn)
    db_url = url.set(drivername="postgresql")
    conn = await asyncpg.connect(db_url.render_as_string(hide_password=False))
    try:
        await conn.execute(
            """
            ALTER TABLE IF EXISTS tasks
            ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0
            """
        )
    finally:
        await conn.close()


async def main() -> None:
    """主函数"""
    args = parse_args()
    settings = load_settings()
    if args.create_database:
        await ensure_database_exists(settings.postgres["dsn"])

    engine = create_async_engine(settings.postgres["dsn"], pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    await ensure_runtime_compat_columns(settings.postgres["dsn"])


if __name__ == "__main__":
    asyncio.run(main())
