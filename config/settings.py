from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Settings:
    """应用配置类"""
    data: dict[str, Any]

    @property
    def app(self) -> dict[str, Any]:
        """获取应用配置"""
        return self.data["app"]

    @property
    def storage(self) -> dict[str, Any]:
        """获取存储配置"""
        return self.data["storage"]

    @property
    def redis(self) -> dict[str, Any]:
        """获取 Redis 配置"""
        return self.data["redis"]

    @property
    def postgres(self) -> dict[str, Any]:
        """获取 PostgreSQL 配置"""
        return self.data["postgres"]


def load_settings(path: str | None = None) -> Settings:
    """加载应用配置"""
    resolved_path = path or os.getenv("EVOCLIP_CONFIG_PATH") or "config/config.yaml"
    content = yaml.safe_load(Path(resolved_path).read_text(encoding="utf-8"))
    return Settings(data=content)
