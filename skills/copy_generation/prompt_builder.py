from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_template(path: str) -> dict[str, str]:
    """加载提示词模板"""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def build_prompt(
    template: dict[str, str],
    product_description: str,
    scenes: list[dict[str, Any]],
    total_duration_s: float,
    speech_rate_chars_per_second: float,
) -> str:
    """构建提示词"""
    parts: list[str] = [template["system"], "", "产品描述:", product_description, "", "场景:"]
    for scene in scenes:
        parts.append(
            json.dumps(
                {
                    "scene_id": scene["scene_id"],
                    "duration_s": scene.get("duration_s"),
                    "suggested_position": scene.get("suggested_position"),
                    "highlight_score": scene.get("highlight_score"),
                    "description": scene.get("description", ""),
                    "objects": scene.get("objects", []),
                    "transcription": scene.get("transcription"),
                },
                ensure_ascii=False,
            )
        )

    parts.append(
        "约束条件:"
    )
    parts.append(
        f"- 保持旁白与视频时长预算对齐（总计约 {total_duration_s:.1f} 秒）。"
    )
    parts.append(
        f"- 每行保持简洁；目标语速约为每秒 {speech_rate_chars_per_second:.1f} 个字符。"
    )
    parts.append(
        "- 优先选择开头附近的钩子/高光场景和结尾处的收尾场景。"
    )
    parts.append(
        "输出 JSON 数组，包含键 sentence_id（临时允许）、scene_id、text。不要包含 Markdown 代码块。"
    )
    return "\n".join(parts)
