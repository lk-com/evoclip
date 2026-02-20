from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from skills.skill_optimization.server import SkillOptimizationService


class _DummySession:
    def add(self, _: object) -> None:
        return None

    async def flush(self) -> None:
        return None


class _DummyDB:
    @asynccontextmanager
    async def session(self):
        yield _DummySession()


@pytest.mark.asyncio
async def test_optimize_skills_short_circuit_on_perfect_score() -> None:
    service = SkillOptimizationService()
    result = await service.optimize_skills("task", {"overall_score": 100})
    assert result["optimizations"] == []


@pytest.mark.asyncio
async def test_optimize_skills_cold_start(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SkillOptimizationService()
    monkeypatch.setattr(service, "db", _DummyDB())
    monkeypatch.setattr(service.memory, "embed", lambda *_: [0.1, 0.2])
    monkeypatch.setattr(service.memory, "query", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service.memory, "add_document", lambda *_args, **_kwargs: None)

    async def fake_request(prompt: str):
        assert "diagnosis=" in prompt
        return [{"skill": "copy-generation", "optimization_type": "prompt_update", "param_path": "config/config.yaml:llm.model", "new_value": "gpt-4o-mini", "expected_improvement": "safer output"}]

    monkeypatch.setattr(service, "_request_suggestions", fake_request)

    result = await service.optimize_skills("task", {"overall_score": 80, "prohibited_words": [{}]}, auto_apply=False)
    assert len(result["optimizations"]) == 1
    assert result["retrieved"] == []


@pytest.mark.asyncio
async def test_apply_suggestion_rolls_back_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = SkillOptimizationService()
    service.db = _DummyDB()

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("llm:\n  model: old-model\n", encoding="utf-8")

    original = service._write_dot_path

    def flaky_write(path: Path, dot_path: str, value):
        if value == "new-model":
            raise IOError("write failed")
        return original(path, dot_path, value)

    monkeypatch.setattr(service, "_write_dot_path", flaky_write)

    with pytest.raises(IOError):
        await service._apply_suggestion(
            "task",
            {
                "skill": "copy-generation",
                "optimization_type": "param_update",
                "param_path": f"{cfg}:llm.model",
                "new_value": "new-model",
            },
        )

    assert "old-model" in cfg.read_text(encoding="utf-8")
