from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.main_agent import MainAgent
from store.models import TaskStatus


class DummyRedis:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.progress: list[tuple[str, dict[str, object]]] = []

    async def publish_event(self, task_id: str, payload: dict[str, object]) -> None:
        self.events.append((task_id, payload))

    async def set_progress(self, task_id: str, payload: dict[str, object]) -> None:
        self.progress.append((task_id, payload))


class DummyMCP:
    def __init__(self, stale: list[str]) -> None:
        self._stale = stale

    def stale_tools(self, timeout_seconds: int) -> list[str]:
        assert timeout_seconds == 30
        return self._stale


class DummySession:
    def __init__(self, task: object | None) -> None:
        self._task = task

    async def get(self, _model: object, _task_id: str) -> object | None:
        return self._task


class DummyDB:
    def __init__(self, task: object | None) -> None:
        self._task = task

    @asynccontextmanager
    async def session(self):
        yield DummySession(self._task)


@pytest.mark.asyncio
async def test_heartbeat_skips_restart_when_supervisorctl_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool) -> object:
        calls.append((cmd, check))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("agent.main_agent.subprocess.run", fake_run)

    agent = MainAgent.__new__(MainAgent)
    agent.skill_names = ["video-analysis"]
    agent.mcp = DummyMCP(["video-analysis"])
    agent.redis = DummyRedis()
    agent.supervisorctl = None
    agent.supervisor_restart_disabled_reason = None

    await agent._heartbeat("task-1")

    assert calls == []
    assert (
        "task-1",
        {"status": "restart_skipped", "skill": "video-analysis", "reason": "supervisorctl_not_found"},
    ) in agent.redis.events
    assert agent.redis.progress == [("task-1", {"heartbeat": "ok"})]


@pytest.mark.asyncio
async def test_heartbeat_restarts_stale_tool_when_supervisorctl_available(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool) -> object:
        calls.append((cmd, check))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("agent.main_agent.subprocess.run", fake_run)

    agent = MainAgent.__new__(MainAgent)
    agent.skill_names = ["video-analysis"]
    agent.mcp = DummyMCP(["video-analysis"])
    agent.redis = DummyRedis()
    agent.supervisorctl = "/usr/bin/supervisorctl"
    agent.supervisord_conf = Path("supervisord.conf")
    agent.supervisor_restart_disabled_reason = None

    await agent._heartbeat("task-1")

    assert calls == [(["/usr/bin/supervisorctl", "-c", "supervisord.conf", "restart", "video-analysis"], False)]
    assert ("task-1", {"status": "restarted", "skill": "video-analysis"}) in agent.redis.events
    assert agent.redis.progress == [("task-1", {"heartbeat": "ok"})]


@pytest.mark.asyncio
async def test_run_task_failure_does_not_crash_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    task = SimpleNamespace(
        id="task-1",
        status=TaskStatus.queued,
        progress=0,
        output_video_key=None,
        checkpoint=None,
        detail={},
    )
    agent = MainAgent.__new__(MainAgent)
    agent.db = DummyDB(task)
    agent.redis = DummyRedis()
    agent._heartbeat = lambda _task_id: __import__("asyncio").sleep(0)

    async def fail_run_with_checkpoint(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("video_render_failed:no_renderable_segments")

    agent._run_with_checkpoint = fail_run_with_checkpoint

    await agent.run_task("task-1")

    assert task.status == TaskStatus.failed
    assert task.detail == {"error": "video_render_failed:no_renderable_segments"}
    assert (
        "task-1",
        {"status": "failed", "error": "video_render_failed:no_renderable_segments"},
    ) in agent.redis.events


@pytest.mark.asyncio
async def test_step_video_render_raises_when_render_result_invalid() -> None:
    task = SimpleNamespace(input_video_key="source.mp4", detail={})
    agent = MainAgent.__new__(MainAgent)
    agent.db = DummyDB(task)
    agent.mcp = SimpleNamespace(call_tool=lambda *_args, **_kwargs: __import__("asyncio").sleep(0, {"error": "no_renderable_segments"}))

    with pytest.raises(RuntimeError, match="video_render_failed:no_renderable_segments"):
        await agent._step_video_render(
            task_id="task-1",
            analysis={"scenes": []},
            copies={"sentences": []},
            audios={"audio_segments": []},
        )


@pytest.mark.asyncio
async def test_step_voice_synthesis_raises_when_all_tts_failed() -> None:
    task = SimpleNamespace(input_video_key="source.mp4", detail={})
    agent = MainAgent.__new__(MainAgent)
    agent.db = DummyDB(task)
    agent.mcp = SimpleNamespace(
        call_tool=lambda *_args, **_kwargs: __import__("asyncio").sleep(
            0,
            {
                "error": "all_tts_failed",
                "audio_segments": [{"sentence_id": "t_0", "status": "failed", "error": "dashscope_tts_failed:400"}],
                "failed_reasons": ["dashscope_tts_failed:400"],
            },
        )
    )

    with pytest.raises(RuntimeError, match="voice_synthesis_failed:all_tts_failed:dashscope_tts_failed:400"):
        await agent._step_voice_synthesis(
            task_id="task-1",
            copies={"sentences": [{"sentence_id": "t_0", "scene_id": "s_0", "text": "x"}]},
        )


@pytest.mark.asyncio
async def test_heartbeat_disables_restart_when_supervisord_socket_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool) -> object:
        calls.append((cmd, check))
        return SimpleNamespace(returncode=4, stdout="", stderr="unix:///tmp/evoclip-supervisor.sock no such file")

    monkeypatch.setattr("agent.main_agent.subprocess.run", fake_run)

    agent = MainAgent.__new__(MainAgent)
    agent.skill_names = ["video-analysis", "copy-generation"]
    agent.mcp = DummyMCP(["video-analysis", "copy-generation"])
    agent.redis = DummyRedis()
    agent.supervisorctl = "/usr/bin/supervisorctl"
    agent.supervisord_conf = Path("supervisord.conf")
    agent.supervisor_restart_disabled_reason = None

    await agent._heartbeat("task-1")

    assert len(calls) == 1
    assert calls[0] == (["/usr/bin/supervisorctl", "-c", "supervisord.conf", "restart", "video-analysis"], False)
    assert agent.supervisor_restart_disabled_reason == "supervisord_socket_unavailable"
    assert (
        "task-1",
        {"status": "restart_skipped", "skill": "copy-generation", "reason": "supervisord_socket_unavailable"},
    ) in agent.redis.events
