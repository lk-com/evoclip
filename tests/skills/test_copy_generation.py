from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from skills.copy_generation.server import CopyGenerationService


def _fake_chat_response(payload: list[dict[str, str]]) -> object:
    content = json.dumps(payload, ensure_ascii=False)
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


@pytest.mark.asyncio
async def test_generate_copy_rejects_empty_description() -> None:
    service = CopyGenerationService()
    result = await service.generate_copy("   ", [{"scene_id": "s_0", "description": "x", "objects": []}])
    assert result["error"] == "empty_product_description"


@pytest.mark.asyncio
async def test_generate_copy_detects_invalid_scene_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = CopyGenerationService()

    async def fake_create(**_: object) -> object:
        return _fake_chat_response([{"scene_id": "s_missing", "text": "bad"}])

    monkeypatch.setattr(service.client.chat.completions, "create", fake_create)
    result = await service.generate_copy(
        "desc",
        [{"scene_id": "s_0", "description": "demo", "objects": [], "transcription": None}],
    )
    assert result["error"] == "invalid_scene_id_reference"


@pytest.mark.asyncio
async def test_generate_copy_estimates_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    service = CopyGenerationService()

    async def fake_create(**_: object) -> object:
        return _fake_chat_response([{"scene_id": "s_0", "text": "abcde"}])

    monkeypatch.setattr(service.client.chat.completions, "create", fake_create)
    result = await service.generate_copy(
        "desc",
        [{"scene_id": "s_0", "start_ms": 0, "end_ms": 5000, "description": "demo", "objects": ["cup"], "transcription": "hi"}],
    )

    assert result["sentences"][0]["scene_id"] == "s_0"
    assert result["sentences"][0]["estimated_duration_s"] == 1.3


@pytest.mark.asyncio
async def test_generate_copy_marks_highlight_and_keeps_chronological_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    service = CopyGenerationService()

    async def fake_create(**_: object) -> object:
        return _fake_chat_response(
            [
                {"scene_id": "s_1", "text": "高光特写，展示核心效果"},
                {"scene_id": "s_0", "text": "普通开场"},
            ]
        )

    monkeypatch.setattr(service.client.chat.completions, "create", fake_create)
    result = await service.generate_copy(
        "desc",
        [
            {"scene_id": "s_0", "start_ms": 0, "end_ms": 4000, "description": "平稳展示", "objects": []},
            {"scene_id": "s_1", "start_ms": 4000, "end_ms": 8000, "description": "高光特写镜头", "objects": []},
        ],
    )
    assert result["sentences"][0]["scene_id"] == "s_0"
    by_scene = {item["scene_id"]: item for item in result["sentences"]}
    assert by_scene["s_1"]["suggested_position"] in {"mid_hook", "climax", "hook", "hook_closing"}


@pytest.mark.asyncio
async def test_generate_copy_limits_cut_count_for_short_video(monkeypatch: pytest.MonkeyPatch) -> None:
    service = CopyGenerationService()
    service.target_segment_seconds = 2.5
    service.max_sentences = 12

    async def fake_create(**_: object) -> object:
        payload = [{"scene_id": f"s_{idx}", "text": f"文案{idx}"} for idx in range(8)]
        return _fake_chat_response(payload)

    monkeypatch.setattr(service.client.chat.completions, "create", fake_create)
    scenes = [
        {"scene_id": f"s_{idx}", "start_ms": idx * 1000, "end_ms": (idx + 1) * 1000, "description": "普通镜头", "objects": []}
        for idx in range(8)
    ]

    result = await service.generate_copy("desc", scenes)
    selected_ids = [item["scene_id"] for item in result["sentences"]]
    assert len(selected_ids) == 3
    assert "s_0" in selected_ids
    assert "s_7" in selected_ids


@pytest.mark.asyncio
async def test_generate_copy_trims_text_to_scene_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    service = CopyGenerationService()
    service.speech_rate_chars_per_second = 3.5
    service.min_sentence_chars = 4

    async def fake_create(**_: object) -> object:
        return _fake_chat_response(
            [
                {
                    "scene_id": "s_0",
                    "text": "这是一段非常长非常长非常长的文案，会超过场景时长预算，需要被自动裁短",
                }
            ]
        )

    monkeypatch.setattr(service.client.chat.completions, "create", fake_create)
    result = await service.generate_copy(
        "desc",
        [{"scene_id": "s_0", "start_ms": 0, "end_ms": 1000, "description": "demo", "objects": []}],
    )
    assert len(result["sentences"]) == 1
    assert len(result["sentences"][0]["text"]) <= 4
    assert result["sentences"][0]["estimated_duration_s"] <= 1.2
