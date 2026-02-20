from __future__ import annotations

from typing import Any

from skills.skill_optimization.server import service as optimization_service


class OptimizerAgent:
    """优化代理"""

    async def optimize(self, task_id: str, diagnosis: dict[str, Any]) -> dict[str, Any]:
        """优化技能参数"""
        auto_apply = int(diagnosis.get("overall_score", 0)) < 60
        return await optimization_service.optimize_skills(task_id=task_id, diagnosis=diagnosis, auto_apply=auto_apply)
