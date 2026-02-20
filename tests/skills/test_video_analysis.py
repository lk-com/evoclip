from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from skills.video_analysis.frame_extractor import (
    MAX_VIDEO_SIZE_BYTES,
    FrameInfo,
    VideoValidationError,
    validate_video_file,
)
from skills.video_analysis.server import Scene, VideoAnalysisService


@pytest.mark.parametrize(
    ("name", "size", "error"),
    [
        ("clip.avi", 1024, "unsupported_format"),
        ("clip.mp4", MAX_VIDEO_SIZE_BYTES + 1, "video_too_large"),
    ],
)
def test_validate_video_file_rejects_invalid_input(name: str, size: int, error: str) -> None:
    with pytest.raises(VideoValidationError, match=error):
        validate_video_file(name, size)


def test_merge_frames_creates_stable_scene_ids() -> None:
    service = VideoAnalysisService()
    service.min_scene_duration_ms = 0
    service.scene_split_min_duration_ms = 0
    scenes = service._merge_frames_into_scenes(
        [
            {"timestamp_ms": 0, "description": "kitchen", "objects": ["pan"]},
            {"timestamp_ms": 1000, "description": "kitchen", "objects": ["pan"]},
            {"timestamp_ms": 2000, "description": "table", "objects": ["plate"]},
        ],
        duration_ms=3000,
    )

    assert [scene.scene_id for scene in scenes] == ["s_0", "s_1"]
    assert scenes[0].start_ms == 0
    assert scenes[0].end_ms == 2000
    assert scenes[1].start_ms == 2000
    assert scenes[1].end_ms == 3000


def test_merge_frames_merges_too_short_scenes_for_continuity() -> None:
    service = VideoAnalysisService()
    service.min_scene_duration_ms = 1800
    service.scene_split_min_duration_ms = 0
    scenes = service._merge_frames_into_scenes(
        [
            {"timestamp_ms": 0, "description": "intro", "objects": ["phone"]},
            {"timestamp_ms": 1000, "description": "detail", "objects": ["screen"]},
            {"timestamp_ms": 2000, "description": "detail", "objects": ["screen"]},
            {"timestamp_ms": 3000, "description": "ending", "objects": ["logo"]},
        ],
        duration_ms=4000,
    )

    assert len(scenes) == 2
    assert scenes[0].start_ms == 0
    assert scenes[0].end_ms == 3000
    assert scenes[1].start_ms == 3000
    assert scenes[1].end_ms == 4000


def test_merge_frames_keeps_short_video_as_single_scene() -> None:
    service = VideoAnalysisService()
    service.scene_split_min_duration_ms = 10_000
    scenes = service._merge_frames_into_scenes(
        [
            {"timestamp_ms": 0, "description": "intro", "objects": ["phone"]},
            {"timestamp_ms": 1000, "description": "detail", "objects": ["screen"]},
            {"timestamp_ms": 2000, "description": "ending", "objects": ["logo"]},
        ],
        duration_ms=5000,
    )
    assert len(scenes) == 1
    assert scenes[0].start_ms == 0
    assert scenes[0].end_ms == 5000
    assert "phone" in scenes[0].objects
    assert "screen" in scenes[0].objects
    assert "logo" in scenes[0].objects


def test_align_transcription_sets_null_when_no_overlap() -> None:
    service = VideoAnalysisService()
    scenes = [
        Scene("s_0", 0, 1000, "scene", [], None),
        Scene("s_1", 1000, 2000, "scene", [], None),
    ]
    service._align_transcription(scenes, [{"begin_time": 0, "end_time": 800, "text": "hello"}])

    assert scenes[0].transcription == "hello"
    assert scenes[1].transcription is None


def test_limit_frames_downsamples_evenly() -> None:
    service = VideoAnalysisService()
    service.max_frames = 4
    frames = [FrameInfo(path=Path(f"frame_{i}.jpg"), timestamp_ms=i * 1000) for i in range(10)]

    selected, limited = service._limit_frames(frames)

    assert limited is True
    assert len(selected) == 4
    assert [item.timestamp_ms for item in selected] == [0, 3000, 6000, 9000]


@pytest.mark.asyncio
async def test_analyze_frames_respects_concurrency_and_emits_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VideoAnalysisService()
    service.frame_analysis_concurrency = 2
    frames = [FrameInfo(path=Path(f"frame_{i}.jpg"), timestamp_ms=i * 1000) for i in range(6)]

    active = 0
    max_active = 0

    async def fake_analyze_frame(frame_path: Path) -> dict[str, object]:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.01)
            return {"description": frame_path.stem, "objects": [frame_path.name]}
        finally:
            active -= 1

    monkeypatch.setattr(service.vision, "analyze_frame", fake_analyze_frame)

    events: list[dict[str, object]] = []

    async def progress_callback(payload: dict[str, object]) -> None:
        events.append(payload)

    analyzed = await service._analyze_frames(
        frames,
        source_video_key="video-1.mp4",
        progress_callback=progress_callback,
    )

    assert len(analyzed) == len(frames)
    assert max_active == 2
    frame_events = [event for event in events if event.get("stage") == "frame_processed"]
    assert len(frame_events) == len(frames)
    assert all(event.get("video_object_key") == "video-1.mp4" for event in frame_events)
    assert frame_events[-1]["processed_frames"] == len(frames)


@pytest.mark.asyncio
async def test_analyze_video_returns_frame_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VideoAnalysisService()
    service.max_frames = 3
    service.frame_sample_fps = 1

    class _Stat:
        size = 1024

    monkeypatch.setattr(service.minio.client, "stat_object", lambda *_args, **_kwargs: _Stat())
    monkeypatch.setattr(service.minio, "download_file", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service.minio, "upload_bytes", lambda *_args, **_kwargs: None)

    extracted_frames = [FrameInfo(path=Path(f"f_{idx}.jpg"), timestamp_ms=idx * 1000) for idx in range(6)]
    monkeypatch.setattr("skills.video_analysis.server.extract_frames", lambda *_args, **_kwargs: extracted_frames)
    monkeypatch.setattr("skills.video_analysis.server.get_video_duration_ms", lambda *_args, **_kwargs: 6000)

    async def fake_analyze_frames(
        frames: list[FrameInfo],
        *,
        source_video_key: str | None = None,
        progress_callback=None,
    ) -> list[dict[str, object]]:
        _ = source_video_key, progress_callback
        return [{"timestamp_ms": frame.timestamp_ms, "description": "scene", "objects": []} for frame in frames]

    async def fake_transcribe(_video_path: str) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(service, "_analyze_frames", fake_analyze_frames)
    monkeypatch.setattr(service.speech, "transcribe", fake_transcribe)

    progress_events: list[dict[str, object]] = []

    async def progress_callback(payload: dict[str, object]) -> None:
        progress_events.append(payload)

    result = await service.analyze_video(
        task_id="task-1",
        video_object_keys=["source_0.mp4"],
        progress_callback=progress_callback,
    )

    metrics = result["analysis_metrics"]
    assert metrics["total_videos"] == 1
    assert metrics["total_extracted_frames"] == 6
    assert metrics["total_analyzed_frames"] == 3
    assert metrics["frame_limit_applied_videos"] == 1
    assert metrics["videos"][0]["skipped_frames"] == 3
    assert metrics["videos"][0]["frame_limit_applied"] is True
    assert any(event.get("stage") == "frames_selected" for event in progress_events)
    assert any(event.get("stage") == "analysis_completed" for event in progress_events)
