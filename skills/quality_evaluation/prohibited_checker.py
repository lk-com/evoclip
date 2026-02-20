from __future__ import annotations

from pathlib import Path


def load_words(path: str) -> list[str]:
    """加载违禁词列表"""
    content = Path(path).read_text(encoding="utf-8")
    return [line.strip() for line in content.splitlines() if line.strip()]


def scan_prohibited(timeline: list[dict], words: list[str]) -> list[dict]:
    """扫描时间线中的违禁内容"""
    findings: list[dict] = []
    for item in timeline:
        text = str(item.get("subtitle_text", ""))
        matched = [word for word in words if word in text]
        if matched:
            findings.append({"sentence_id": item.get("sentence_id"), "matched_words": matched, "text": text})
    return findings
