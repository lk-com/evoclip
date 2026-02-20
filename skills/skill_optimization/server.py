from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from openai import AsyncOpenAI
from sqlalchemy import select

from skills.common import get_credential, get_settings, parse_json_payload
from skills.skill_optimization.memory_store import MemoryStore
from store.database import Database
from store.models import SkillVersion

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None


def infer_target_skills(diagnosis: dict[str, Any]) -> list[str]:
    """根据诊断结果推断需要优化的技能"""
    targets: set[str] = set()
    if diagnosis.get("sync_errors"):
        targets.add("voice-synthesis")
    if diagnosis.get("visual_issues"):
        targets.add("video-render")
    if diagnosis.get("prohibited_words"):
        targets.add("copy-generation")
    return sorted(targets)


class SkillOptimizationService:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        llm_api_key = get_credential(settings, "llm_api_key", fallback_name="openai_api_key")
        llm_base_url = get_credential(settings, "llm_base_url", fallback_name="openai_base_url")
        llm_client_kwargs: dict[str, str] = {}
        if llm_api_key:
            llm_client_kwargs["api_key"] = llm_api_key
        if llm_base_url:
            llm_client_kwargs["base_url"] = llm_base_url
        self.client = AsyncOpenAI(**llm_client_kwargs)
        self.model = settings.data["llm"]["model"]
        self.embedding_model = settings.data["embedding"]["model"]
        embedding_api_key = get_credential(settings, "embedding_api_key", fallback_name="dashscope_api_key")
        embedding_base_url = get_credential(
            settings,
            "embedding_base_url",
            fallback_name="dashscope_compatible_base_url",
        )
        dashscope_api_key = get_credential(settings, "dashscope_api_key") or embedding_api_key
        dashscope_base_url = get_credential(settings, "dashscope_base_url")
        self.memory = MemoryStore(
            openai_api_key=embedding_api_key,
            openai_base_url=embedding_base_url,
            dashscope_api_key=dashscope_api_key,
            dashscope_base_url=dashscope_base_url,
        )
        self.db = Database(settings.postgres["dsn"])

    async def optimize_skills(
        self,
        task_id: str,
        diagnosis: dict[str, Any],
        auto_apply: bool = False,
    ) -> dict[str, Any]:
        """优化技能参数"""
        score = int(diagnosis.get("overall_score", 0))
        if score == 100:
            return {"optimizations": []}

        problem_text = json.dumps(diagnosis, ensure_ascii=False)
        embedding = await self.memory.embed(problem_text, self.embedding_model)
        retrieved = self.memory.query(embedding, top_k=3)

        prompt = self._build_prompt(diagnosis=diagnosis, retrieved=retrieved)
        suggestions = await self._request_suggestions(prompt)

        applied: list[dict[str, Any]] = []
        if auto_apply or score < 60:
            for suggestion in suggestions:
                applied_item = await self._apply_suggestion(task_id, suggestion)
                applied.append(applied_item)

        self.memory.add_document(
            doc_id=f"{task_id}-diagnosis",
            content={"diagnosis": diagnosis, "optimizations": suggestions},
            embedding=embedding,
        )
        return {"optimizations": suggestions, "retrieved": retrieved, "applied": applied}

    def _build_prompt(self, diagnosis: dict[str, Any], retrieved: list[dict[str, Any]]) -> str:
        """构建优化提示词"""
        targets = infer_target_skills(diagnosis)
        return (
            "生成优化建议，以 JSON 数组格式返回。"
            "每个项目包含 skill、optimization_type、param_path、new_value、expected_improvement。\n"
            f"targets={targets}\n"
            f"diagnosis={json.dumps(diagnosis, ensure_ascii=False)}\n"
            f"retrieved={json.dumps(retrieved, ensure_ascii=False)}"
        )

    async def _request_suggestions(self, prompt: str) -> list[dict[str, Any]]:
        """请求优化建议"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or "[]"
        payload = parse_json_payload(text)
        if isinstance(payload, list):
            return payload
        return []

    async def _apply_suggestion(self, task_id: str, suggestion: dict[str, Any]) -> dict[str, Any]:
        """应用优化建议"""
        path = suggestion.get("param_path", "")
        if ":" not in path:
            return {"status": "skipped", "reason": "invalid_param_path", "suggestion": suggestion}

        file_path, dot_path = path.split(":", 1)
        file_ref = Path(file_path)
        if not file_ref.exists():
            return {"status": "skipped", "reason": "file_not_found", "suggestion": suggestion}

        backup = file_ref.read_text(encoding="utf-8")
        try:
            old_value = self._read_dot_path(backup, dot_path)
        except Exception:
            old_value = None

        async with self.db.session() as session:
            version = SkillVersion(
                skill_name=str(suggestion.get("skill", "unknown")),
                optimization_type=str(suggestion.get("optimization_type", "param_update")),
                param_path=path,
                new_value=json.dumps(suggestion.get("new_value"), ensure_ascii=False),
                source_task_id=task_id,
                source_diagnosis_id=task_id,
            )
            session.add(version)
            await session.flush()

            try:
                self._write_dot_path(file_ref, dot_path, suggestion.get("new_value"))
            except Exception:
                # 从记录的历史上下文回滚到之前的文件状态
                if old_value is not None:
                    self._write_dot_path(file_ref, dot_path, old_value)
                else:
                    file_ref.write_text(backup, encoding="utf-8")
                raise

        return {"status": "applied", "suggestion": suggestion}

    def _read_dot_path(self, raw_yaml: str, dot_path: str) -> Any:
        """读取 YAML 中的点路径值"""
        data = yaml.safe_load(raw_yaml)
        current = data
        for key in dot_path.split("."):
            current = current[key]
        return current

    def _write_dot_path(self, path: Path, dot_path: str, value: Any) -> None:
        """写入 YAML 中的点路径值"""
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        keys = dot_path.split(".")
        current = data
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


service = SkillOptimizationService()
mcp = FastMCP("skill-optimization") if FastMCP else None

if mcp:

    @mcp.tool(name="optimize_skills")
    async def optimize_skills_tool(task_id: str, diagnosis: dict[str, Any], auto_apply: bool = False) -> dict[str, Any]:
        return await service.optimize_skills(task_id=task_id, diagnosis=diagnosis, auto_apply=auto_apply)


if __name__ == "__main__":  # pragma: no cover
    if not mcp:
        raise SystemExit("mcp sdk unavailable")
    mcp.run(transport="stdio")
