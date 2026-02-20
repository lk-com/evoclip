from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class DatabaseUnavailableError(RuntimeError):
    """数据库不可用错误"""
    pass


class Database:
    """数据库连接管理类"""

    def __init__(self, dsn: str) -> None:
        self._engine: AsyncEngine = create_async_engine(dsn, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """获取数据库会话"""
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if isinstance(exc, asyncpg.InvalidCatalogNameError):
                raise DatabaseUnavailableError(
                    "PostgreSQL 数据库缺失。请先运行 `python scripts/init_db.py --create-database`"
                ) from exc
            if isinstance(exc, DBAPIError) and isinstance(exc.orig, asyncpg.InvalidCatalogNameError):
                raise DatabaseUnavailableError(
                    "PostgreSQL 数据库缺失。请先运行 `python scripts/init_db.py --create-database`"
                ) from exc
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        """释放数据库连接"""
        await self._engine.dispose()
