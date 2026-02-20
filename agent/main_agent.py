from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import shutil
import subprocess
from typing import Any

from agent.evaluator import EvaluatorAgent
from agent.mcp_client import MCPClientPool
from agent.optimizer import OptimizerAgent
from config import load_settings
from skills.copy_generation.server import service as copy_service
from skills.video_analysis.server import service as analysis_service
from skills.video_render.server import service as render_service
from skills.voice_synthesis.server import service as voice_service
from store.database import Database
from store.models import Task, TaskStatus
from store.redis_client import RedisStore

logger = logging.getLogger(__name__)


class MainAgent:
    """主代理类，协调所有技能执行"""

    def __init__(self) -> None:
        settings = load_settings()
        self.settings = settings
        self.db = Database(settings.postgres["dsn"])
        app_cfg = settings.app
        self.redis = RedisStore(
            redis_url=settings.redis["url"],
            task_prefix=app_cfg["task_queue_prefix"],
            sse_channel_prefix=app_cfg["sse_channel_prefix"],
            session_ttl=app_cfg["session_ttl_seconds"],
            progress_ttl=app_cfg["progress_ttl_seconds"],
        )
        self.evaluator = EvaluatorAgent()
        self.optimizer = OptimizerAgent()
        self.mcp = MCPClientPool()
        self.mcp.register_tool("video-analysis", analysis_service.analyze_video)
        self.mcp.register_tool("copy-generation", copy_service.generate_copy)
        self.mcp.register_tool("voice-synthesis", voice_service.synthesize_voice)
        self.mcp.register_tool("video-render", render_service.render_video)
        self.mcp.register_tool("quality-evaluation", self.evaluator.evaluate)
        self.mcp.register_tool("skill-optimization", self.optimizer.optimize)
        self.supervisorctl = shutil.which("supervisorctl")
        self.supervisord_conf = Path("supervisord.conf")
        self.supervisor_restart_disabled_reason: str | None = None
        self.skill_names = [
            "video-analysis",
            "copy-generation",
            "voice-synthesis",
            "video-render",
            "quality-evaluation",
            "skill-optimization",
        ]

    async def run_task(self, task_id: str) -> None:
        """运行任务流程"""
        async with self.db.session() as session:
            task = await session.get(Task, task_id)
            if not task:
                return
            task.status = TaskStatus.running

        try:
            await self._heartbeat(task_id)
            analysis = await self._run_with_checkpoint(task_id, "video-analysis", self._step_video_analysis)
            copies = await self._run_with_checkpoint(task_id, "copy-generation", self._step_copy_generation, analysis)
            audios = await self._run_with_checkpoint(task_id, "voice-synthesis", self._step_voice_synthesis, copies)
            rendered = await self._run_with_checkpoint(task_id, "video-render", self._step_video_render, analysis, copies, audios)
            diagnosis = await self._run_with_checkpoint(
                task_id,
                "quality-evaluation",
                self._step_quality_evaluation,
                rendered,
            )
            await self._run_with_checkpoint(task_id, "skill-optimization", self._step_skill_optimization, diagnosis)

            async with self.db.session() as session:
                task = await session.get(Task, task_id)
                if task:
                    task.status = TaskStatus.completed
                    task.progress = 100
                    task.output_video_key = rendered["output_video"]
                    task.checkpoint = "done"
            await self.redis.publish_event(task_id, {"status": "completed", "progress": 100})
        except Exception as exc:
            async with self.db.session() as session:
                task = await session.get(Task, task_id)
                if task:
                    task.status = TaskStatus.failed
                    detail = dict(task.detail or {})
                    detail["error"] = str(exc)
                    task.detail = detail
            await self.redis.publish_event(task_id, {"status": "failed", "error": str(exc)})
            logger.exception("任务 %s 失败: %s", task_id, exc)
            return

    async def _run_with_checkpoint(self, task_id: str, step_name: str, fn: Any, *args: Any) -> Any:
        """带检查点的步骤执行"""
        async with self.db.session() as session:
            task = await session.get(Task, task_id)
            if task and task.checkpoint == step_name:
                return task.detail.get(step_name)

        result = await fn(task_id, *args)
        await self._save_checkpoint(task_id, step_name, result)
        await self.redis.publish_event(task_id, {"status": step_name, "progress": self._progress_for(step_name)})
        return result

    async def _save_checkpoint(self, task_id: str, step_name: str, result: Any) -> None:
        """保存检查点"""
        async with self.db.session() as session:
            task = await session.get(Task, task_id)
            if not task:
                return
            detail = dict(task.detail or {})
            detail[step_name] = result
            task.detail = detail
            task.checkpoint = step_name
            task.progress = self._progress_for(step_name)

    def _progress_for(self, step_name: str) -> int:
        """计算步骤进度"""
        ordered = ["video-analysis", "copy-generation", "voice-synthesis", "video-render", "quality-evaluation", "skill-optimization"]
        idx = ordered.index(step_name) + 1
        return int(idx / len(ordered) * 100)

    def _task_video_keys(self, task: Task) -> list[str]:
        """获取任务的视频键列表"""
        if isinstance(task.detail, dict):
            keys = task.detail.get("input_video_keys")
            if isinstance(keys, list):
                normalized = [str(key) for key in keys if str(key)]
                if normalized:
                    return normalized
        return [task.input_video_key]

    async def _step_video_analysis(self, task_id: str) -> dict[str, Any]:
        """视频分析步骤"""
        async with self.db.session() as session:
            task = await session.get(Task, task_id)
            if not task:
                raise RuntimeError("task_not_found")

            async def _progress_callback(payload: dict[str, Any]) -> None:
                event = {"status": "video-analysis-progress", **payload}
                await self.redis.publish_event(task_id, event)
                await self.redis.set_progress(task_id, event)

            return await self.mcp.call_tool(
                "video-analysis",
                task_id=task_id,
                video_object_keys=self._task_video_keys(task),
                progress_callback=_progress_callback,
            )

    async def _step_copy_generation(self, task_id: str, analysis: dict[str, Any]) -> dict[str, Any]:
        """文案生成步骤"""
        async with self.db.session() as session:
            task = await session.get(Task, task_id)
            if not task:
                raise RuntimeError("task_not_found")
            return await self.mcp.call_tool(
                "copy-generation", product_description=task.product_description, scenes=analysis["scenes"]
            )

    async def _step_voice_synthesis(self, task_id: str, copies: dict[str, Any]) -> dict[str, Any]:
        """语音合成步骤"""
        async with self.db.session() as session:
            task = await session.get(Task, task_id)
            if not task:
                raise RuntimeError("task_not_found")
            voice_sample_keys = []
            if isinstance(task.detail, dict):
                voice_sample_keys = task.detail.get("voice_sample_keys") or []
            source_video_keys = voice_sample_keys or self._task_video_keys(task)
            audios = await self.mcp.call_tool(
                "voice-synthesis",
                task_id=task_id,
                sentences=copies["sentences"],
                source_video_keys=source_video_keys,
            )
            if audios.get("error"):
                reason = str(audios["error"])
                failed_reasons = audios.get("failed_reasons") or []
                if failed_reasons:
                    reason = f"{reason}:{failed_reasons[0]}"
                raise RuntimeError(f"voice_synthesis_failed:{reason}")
            audio_segments = audios.get("audio_segments")
            if not isinstance(audio_segments, list):
                raise RuntimeError("voice_synthesis_invalid_result")
            if not any(item.get("status") == "ok" for item in audio_segments):
                raise RuntimeError("voice_synthesis_failed:no_successful_audio_segments")
            return audios

    async def _step_video_render(
        self,
        task_id: str,
        analysis: dict[str, Any],
        copies: dict[str, Any],
        audios: dict[str, Any],
    ) -> dict[str, Any]:
        """视频渲染步骤"""
        async with self.db.session() as session:
            task = await session.get(Task, task_id)
            if not task:
                raise RuntimeError("task_not_found")
            audio_segments = audios.get("audio_segments")
            if not isinstance(audio_segments, list):
                raise RuntimeError("voice_synthesis_invalid_result")
            source_video_keys = self._task_video_keys(task)
            rendered = await self.mcp.call_tool(
                "video-render",
                task_id=task_id,
                source_video_key=source_video_keys[0],
                source_video_keys=source_video_keys,
                scenes=analysis["scenes"],
                sentences=copies["sentences"],
                audio_segments=audio_segments,
                voice_profile_fallback=bool(audios.get("voice_profile_fallback")),
            )
            if rendered.get("error"):
                raise RuntimeError(f"video_render_failed:{rendered['error']}")
            output_video = rendered.get("output_video")
            timeline_path = rendered.get("timeline_path")
            if not output_video or not timeline_path:
                raise RuntimeError("video_render_invalid_result")
            return rendered

    async def _step_quality_evaluation(self, task_id: str, rendered: dict[str, Any]) -> dict[str, Any]:
        """质量评估步骤"""
        timeline_path = rendered.get("timeline_path")
        output_video = rendered.get("output_video")
        if not timeline_path or not output_video:
            raise RuntimeError("video_render_result_missing_for_quality_evaluation")
        return await self.mcp.call_tool(
            "quality-evaluation",
            task_id=task_id,
            timeline_path=timeline_path,
            video_path=output_video,
        )

    async def _step_skill_optimization(self, task_id: str, diagnosis: dict[str, Any]) -> dict[str, Any]:
        """技能优化步骤"""
        return await self.mcp.call_tool("skill-optimization", task_id=task_id, diagnosis=diagnosis)

    async def _heartbeat(self, task_id: str) -> None:
        """发送心跳信号并检查技能状态"""
        for skill in self.skill_names:
            await self.redis.publish_event(task_id, {"status": "heartbeat", "skill": skill, "interval": 30})

        stale = self.mcp.stale_tools(timeout_seconds=30)
        for skill in stale:
            if self.supervisor_restart_disabled_reason:
                await self.redis.publish_event(
                    task_id,
                    {
                        "status": "restart_skipped",
                        "skill": skill,
                        "reason": self.supervisor_restart_disabled_reason,
                    },
                )
                continue
            if not self.supervisorctl:
                logger.warning("跳过过期技能重启，因为未安装 supervisorctl: %s", skill)
                await self.redis.publish_event(task_id, {"status": "restart_skipped", "skill": skill, "reason": "supervisorctl_not_found"})
                continue
            cmd = [self.supervisorctl]
            if self.supervisord_conf.exists():
                cmd.extend(["-c", str(self.supervisord_conf)])
            cmd.extend(["restart", skill])
            try:
                result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            except OSError as exc:
                logger.warning("通过 supervisorctl 重启过期技能 %s 失败: %s", skill, exc)
                await self.redis.publish_event(task_id, {"status": "restart_failed", "skill": skill, "error": str(exc)})
                continue
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip()
                lowered = err.lower()
                if "unix://" in lowered and "no such file" in lowered:
                    self.supervisor_restart_disabled_reason = "supervisord_socket_unavailable"
                    logger.warning("禁用过期技能重启: %s", err)
                    await self.redis.publish_event(
                        task_id,
                        {"status": "restart_skipped", "skill": skill, "reason": self.supervisor_restart_disabled_reason},
                    )
                    continue
                logger.warning("过期技能 %s 的重启命令失败: %s", skill, err)
                await self.redis.publish_event(task_id, {"status": "restart_failed", "skill": skill, "error": err or f"returncode_{result.returncode}"})
                continue
            await self.redis.publish_event(task_id, {"status": "restarted", "skill": skill})
        await self.redis.set_progress(task_id, {"heartbeat": "ok"})


agent = MainAgent()


async def run_forever() -> None:
    while True:
        task_id = await agent.redis.redis.lpop(agent.redis.queue_key())
        if not task_id:
            await asyncio.sleep(1)
            continue
        await agent.run_task(task_id)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run_forever())
