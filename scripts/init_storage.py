from __future__ import annotations

from config import load_settings
from store.minio_client import MinioStore


def main() -> None:
    """主函数"""
    settings = load_settings()
    minio_cfg = settings.storage["minio"]
    buckets = minio_cfg["buckets"]
    client = MinioStore(
        endpoint=minio_cfg["endpoint"],
        access_key=minio_cfg["access_key"],
        secret_key=minio_cfg["secret_key"],
        secure=minio_cfg.get("secure", False),
    )
    client.ensure_buckets([buckets["videos"], buckets["audio"], buckets["intermediate"], buckets["output"]])


if __name__ == "__main__":
    main()
