from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.quality_evaluation.server import QualityEvaluationService
from skills.quality_evaluation.sync_checker import check_sync


@pytest.mark.asyncio
async def test_evaluate_quality_returns_input_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    service = QualityEvaluationService()
    monkeypatch.setattr(service.minio, "download_bytes", lambda *_: (_ for _ in ()).throw(FileNotFoundError("x")))

    result = await service.evaluate_quality("task", "output/missing.json", "output/missing.mp4")
    assert result["error"] == "input_not_found"


@pytest.mark.asyncio
async def test_evaluate_quality_calculates_score(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = QualityEvaluationService()
    timeline = [
        {
            "scene_id": "s_0",
            "sentence_id": "t_0",
            "start_ms": 0,
            "end_ms": 1000,
            "audio_path": "audio/task/t_0.mp3",
            "subtitle_text": "安全描述",
            "skipped": False,
        }
    ]

    monkeypatch.setattr(service.minio, "download_bytes", lambda *_: json.dumps(timeline).encode("utf-8"))

    def fake_download(bucket: str, object_name: str, file_path: str) -> None:
        Path(file_path).write_bytes(b"data")

    monkeypatch.setattr(service.minio, "download_file", fake_download)
    monkeypatch.setattr(service.minio, "upload_bytes", lambda *args, **kwargs: "")
    monkeypatch.setattr("skills.quality_evaluation.server.check_sync", lambda *args, **kwargs: [{}])
    monkeypatch.setattr("skills.quality_evaluation.server.detect_visual_issues", lambda *args, **kwargs: [])
    monkeypatch.setattr("skills.quality_evaluation.server.scan_prohibited", lambda *args, **kwargs: [])
    monkeypatch.setattr("skills.quality_evaluation.server.probe_duration_ms", lambda *args, **kwargs: 1000)

    result = await service.evaluate_quality("task", "output/timeline.json", "output/final.mp4")
    assert result["overall_score"] == 90
    assert len(result["sync_errors"]) == 1


def test_check_sync_prefers_final_audio_duration_ms() -> None:
    timeline = [
        {
            "scene_id": "s_0",
            "start_ms": 0,
            "end_ms": 1000,
            "audio_path": "audio/task/t_0.mp3",
            "final_audio_duration_ms": 1160,
        }
    ]
    # 即使查找包含匹配的持续时间，final_audio_duration_ms 应该是权威值
    errors = check_sync(timeline, {"audio/task/t_0.mp3": 1000}, tolerance_ms=120)
    assert len(errors) == 1
    assert errors[0]["delta_ms"] == 160
