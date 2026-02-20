from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from typing import Any

import chromadb
from openai import AsyncOpenAI

try:
    import dashscope
except Exception:  # pragma: no cover
    dashscope = None


class MemoryStore:
    def __init__(
        self,
        path: str = "data/chroma",
        collection_name: str = "skill-optimization",
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        dashscope_api_key: str | None = None,
        dashscope_base_url: str | None = None,
    ) -> None:
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(collection_name)
        client_kwargs: dict[str, str] = {}
        if openai_api_key:
            client_kwargs["api_key"] = openai_api_key
        if openai_base_url:
            client_kwargs["base_url"] = openai_base_url
        self.embed_client = AsyncOpenAI(**client_kwargs)
        self.dashscope_api_key = dashscope_api_key
        self.dashscope_base_url = dashscope_base_url
        if dashscope is not None:
            if dashscope_api_key:
                dashscope.api_key = dashscope_api_key
            if dashscope_base_url:
                dashscope.base_http_api_url = dashscope_base_url

    async def embed(self, text: str, model: str) -> list[float]:
        """生成文本嵌入向量"""
        if self._is_multimodal_model(model):
            return await self._embed_dashscope_multimodal(text, model)
        result = await self.embed_client.embeddings.create(model=model, input=text)
        return list(result.data[0].embedding)

    def count(self) -> int:
        """获取文档数量"""
        return self.collection.count()

    def query(self, embedding: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        """查询相似文档"""
        if self.collection.count() == 0:
            return []
        raw = self.collection.query(query_embeddings=[embedding], n_results=top_k)
        docs = raw.get("documents", [[]])[0]
        ids = raw.get("ids", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        results: list[dict[str, Any]] = []
        for doc_id, doc, distance in zip(ids, docs, distances):
            similarity = 1 - float(distance)
            if similarity >= 0.75:
                results.append({"id": doc_id, "content": doc, "similarity": similarity})
        return results

    def add_document(self, doc_id: str, content: dict[str, Any], embedding: list[float]) -> None:
        """添加文档到存储"""
        self.collection.add(
            ids=[doc_id],
            documents=[json.dumps(content, ensure_ascii=False)],
            embeddings=[embedding],
        )

    def _is_multimodal_model(self, model: str) -> bool:
        """检查是否为多模态模型"""
        normalized = model.lower().strip()
        return (
            "vl-embedding" in normalized
            or "embedding-vision" in normalized
            or normalized.startswith("multimodal-embedding-")
        )

    async def _embed_dashscope_multimodal(self, text: str, model: str) -> list[float]:
        """使用 DashScope 多模态模型生成嵌入"""
        if dashscope is None:
            raise RuntimeError("dashscope_sdk_unavailable")
        if not self.dashscope_api_key:
            raise RuntimeError("dashscope_api_key_missing")
        if self.dashscope_base_url:
            dashscope.base_http_api_url = self.dashscope_base_url

        def _call() -> list[float]:
            response = dashscope.MultiModalEmbedding.call(
                api_key=self.dashscope_api_key,
                model=model,
                input=[{"text": text}],
            )
            status_code = getattr(response, "status_code", None)
            if status_code != HTTPStatus.OK:
                raise RuntimeError(f"dashscope_embedding_failed:{status_code}")
            output = getattr(response, "output", None)
            embeddings = output.get("embeddings") if isinstance(output, dict) else getattr(output, "embeddings", None)
            if not embeddings:
                raise RuntimeError("dashscope_embedding_payload_missing")
            item = embeddings[0]
            vector = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
            if vector is None:
                raise RuntimeError("dashscope_embedding_vector_missing")
            return list(vector)

        return await asyncio.to_thread(_call)
