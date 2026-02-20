from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error


class MinioStore:
    """MinIO 存储客户端"""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure
        self.client = Minio(endpoint=endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    def ensure_bucket(self, bucket_name: str) -> None:
        """确保存储桶存在"""
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)

    def ensure_buckets(self, bucket_names: list[str]) -> None:
        """确保多个存储桶存在"""
        for bucket_name in bucket_names:
            self.ensure_bucket(bucket_name)

    def upload_bytes(self, bucket: str, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """上传字节数据"""
        try:
            self.client.put_object(bucket, object_name, BytesIO(data), len(data), content_type=content_type)
        except S3Error as exc:
            raise RuntimeError(f"failed_to_upload:{bucket}/{object_name}") from exc
        return f"{bucket}/{object_name}"

    def download_bytes(self, bucket: str, object_name: str) -> bytes:
        """下载字节数据"""
        try:
            response = self.client.get_object(bucket, object_name)
            return response.read()
        except S3Error as exc:
            raise FileNotFoundError(f"missing_object:{bucket}/{object_name}") from exc

    def download_file(self, bucket: str, object_name: str, file_path: str) -> None:
        """下载文件"""
        self.client.fget_object(bucket, object_name, file_path)

    def upload_file(self, bucket: str, object_name: str, file_path: str, content_type: str = "application/octet-stream") -> str:
        """上传文件"""
        self.client.fput_object(bucket, object_name, file_path, content_type=content_type)
        return f"{bucket}/{object_name}"

    def presigned_get_object(
        self,
        bucket: str,
        object_name: str,
        *,
        expires,
        public_base_url: str | None = None,
    ) -> str:
        """生成预签名获取 URL"""
        if not public_base_url:
            return self.client.presigned_get_object(bucket, object_name, expires=expires)

        parsed = urlparse(public_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("invalid_public_base_url")
        if parsed.path and parsed.path not in {"", "/"}:
            raise ValueError("public_base_url_with_path_not_supported")

        public_client = Minio(
            endpoint=parsed.netloc,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=parsed.scheme.lower() == "https",
        )
        return public_client.presigned_get_object(bucket, object_name, expires=expires)
