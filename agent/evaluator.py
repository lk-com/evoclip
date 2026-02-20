from __future__ import annotations

from typing import Any

from skills.quality_evaluation.server import service as quality_service


class EvaluatorAgent:
    """评估代理"""

    async def evaluate(self, task_id: str, timeline_path: str, video_path: str) -> dict[str, Any]:
        """评估视频质量"""
        return await quality_service.evaluate_quality(task_id=task_id, timeline_path=timeline_path, video_path=video_path)
