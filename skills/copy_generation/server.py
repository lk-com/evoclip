from __future__ import annotations

import re
from typing import Any

from openai import AsyncOpenAI

from skills.common import (
    RetryPolicy,
    get_credential,
    get_settings,
    parse_json_payload,
    retry_async,
)
from skills.copy_generation.prompt_builder import build_prompt, load_template

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None


class CopyGenerationService:
    def __init__(self) -> None:
        settings = get_settings()
        llm_cfg = settings.data["llm"]
        copy_cfg = settings.data.get("copy_generation", {})
        llm_api_key = get_credential(settings, "llm_api_key", fallback_name="openai_api_key")
        llm_base_url = get_credential(settings, "llm_base_url", fallback_name="openai_base_url")
        client_kwargs: dict[str, str] = {}
        if llm_api_key:
            client_kwargs["api_key"] = llm_api_key
        if llm_base_url:
            client_kwargs["base_url"] = llm_base_url
        self.client = AsyncOpenAI(**client_kwargs)
        self.model = llm_cfg["model"]
        self.timeout_seconds = int(llm_cfg.get("timeout_seconds", 30))
        self.speech_rate_chars_per_second = float(copy_cfg.get("speech_rate_chars_per_second", 3.8))
        self.max_sentence_seconds = float(copy_cfg.get("max_sentence_seconds", 6.0))
        self.target_segment_seconds = float(copy_cfg.get("target_segment_seconds", 2.5))
        self.min_sentence_chars = int(copy_cfg.get("min_sentence_chars", 4))
        self.duration_safety_factor = float(copy_cfg.get("duration_safety_factor", 0.88))
        self.max_sentences = int(copy_cfg.get("max_sentences", 12))
        self.limit_one_sentence_per_scene = bool(copy_cfg.get("limit_one_sentence_per_scene", True))
        self.reorder_by_scene_strategy = bool(copy_cfg.get("reorder_by_scene_strategy", False))
        configured_keywords = copy_cfg.get("highlight_keywords")
        if isinstance(configured_keywords, list) and configured_keywords:
            self.highlight_keywords = [str(item).lower() for item in configured_keywords if str(item).strip()]
        else:
            self.highlight_keywords = [
                "高光",
                "亮点",
                "特写",
                "爆点",
                "核心",
                "卖点",
                "重点",
                "对比",
                "效果",
                "before",
                "after",
                "highlight",
                "wow",
            ]
        self.template = load_template(settings.data["paths"]["copy_prompt"])

    async def generate_copy(self, product_description: str, scenes: list[dict[str, Any]]) -> dict[str, Any]:
        if not product_description or not product_description.strip():
            return {"error": "empty_product_description"}
        if len(scenes) < 1:
            return {"error": "empty_scenes"}

        scene_profiles = self._build_scene_profiles(scenes)
        scene_id_set = {scene["scene_id"] for scene in scene_profiles}
        total_duration_s = sum(float(scene["duration_s"]) for scene in scene_profiles)
        prompt = build_prompt(
            self.template,
            product_description.strip(),
            scene_profiles,
            total_duration_s=total_duration_s,
            speech_rate_chars_per_second=self.speech_rate_chars_per_second,
        )

        async def _call_llm() -> list[dict[str, Any]]:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                timeout=self.timeout_seconds,
            )
            text = response.choices[0].message.content or "[]"
            payload = parse_json_payload(text)
            if not isinstance(payload, list):
                raise ValueError("invalid_llm_response")
            return payload

        try:
            llm_output = await retry_async(_call_llm, RetryPolicy(retries=3, delays=(1.0, 2.0, 4.0)))
        except Exception:
            return {"error": "llm_api_unavailable"}

        items: list[dict[str, Any]] = []
        for index, sentence in enumerate(llm_output):
            scene_id = sentence.get("scene_id")
            if scene_id not in scene_id_set:
                return {"error": "invalid_scene_id_reference", "scene_id": scene_id}
            text = str(sentence.get("text", "")).strip()
            if not text:
                continue
            items.append({"scene_id": scene_id, "text": text, "index": index})

        if self.limit_one_sentence_per_scene:
            deduped: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in items:
                scene_id = str(item["scene_id"])
                if scene_id in seen:
                    continue
                seen.add(scene_id)
                deduped.append(item)
            items = deduped

        scene_rank = {scene["scene_id"]: int(scene["order_rank"]) for scene in scene_profiles}
        items.sort(key=lambda item: (scene_rank.get(str(item["scene_id"]), 10_000), int(item["index"])))

        items = self._limit_items_for_continuity(items, scene_profiles, total_duration_s)
        if self.reorder_by_scene_strategy:
            items.sort(key=lambda item: (scene_rank.get(str(item["scene_id"]), 10_000), int(item["index"])))

        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(items[: self.max_sentences]):
            scene_id = str(item["scene_id"])
            profile = next((scene for scene in scene_profiles if str(scene["scene_id"]) == scene_id), None)
            if not profile:
                continue
            max_seconds = min(float(profile["duration_s"]), self.max_sentence_seconds)
            safe_seconds = max(0.2, max_seconds * max(self.duration_safety_factor, 0.1))
            dynamic_min_chars = self.min_sentence_chars
            short_scene_cap = max(1, int(max_seconds * self.speech_rate_chars_per_second))
            if short_scene_cap < self.min_sentence_chars:
                dynamic_min_chars = short_scene_cap
            max_chars = max(dynamic_min_chars, int(safe_seconds * self.speech_rate_chars_per_second))
            trimmed_text = self._trim_text(str(item["text"]), max_chars)
            estimated_duration = round(len(trimmed_text) / self.speech_rate_chars_per_second, 1)
            normalized.append(
                {
                    "sentence_id": f"t_{idx}",
                    "scene_id": scene_id,
                    "text": trimmed_text,
                    "estimated_duration_s": estimated_duration,
                    "scene_duration_s": round(float(profile["duration_s"]), 2),
                    "suggested_position": profile["suggested_position"],
                    "audio_trim_risk": estimated_duration > max_seconds,
                }
            )

        return {"sentences": normalized}

    def _build_scene_profiles(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(scenes, key=lambda scene: int(scene.get("start_ms", 0)))
        profiles: list[dict[str, Any]] = []
        for index, scene in enumerate(ordered):
            start_ms = int(scene.get("start_ms", 0))
            end_ms = int(scene.get("end_ms", start_ms))
            duration_ms = max(300, end_ms - start_ms)
            duration_s = duration_ms / 1000
            highlight_score = self._score_highlight(scene)
            profiles.append(
                {
                    "scene_id": str(scene["scene_id"]),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "duration_s": duration_s,
                    "description": scene.get("description", ""),
                    "objects": scene.get("objects", []),
                    "transcription": scene.get("transcription"),
                    "source_video_key": scene.get("source_video_key"),
                    "highlight_score": highlight_score,
                    "suggested_position": "body",
                    "order_rank": 1000 + index,
                }
            )
        if not profiles:
            return profiles

        highlight_scene = max(profiles, key=lambda item: (int(item["highlight_score"]), float(item["duration_s"])))
        closing_scene = profiles[-1]
        total_span_ms = max(int(profiles[-1]["end_ms"]) - int(profiles[0]["start_ms"]), 1)
        highlight_offset_ms = int(highlight_scene["start_ms"]) - int(profiles[0]["start_ms"])
        ratio = highlight_offset_ms / total_span_ms
        if ratio <= 0.33:
            highlight_scene["suggested_position"] = "hook"
        elif ratio >= 0.66:
            highlight_scene["suggested_position"] = "climax"
        else:
            highlight_scene["suggested_position"] = "mid_hook"
        if closing_scene["scene_id"] != highlight_scene["scene_id"]:
            closing_scene["suggested_position"] = "closing"
        else:
            highlight_scene["suggested_position"] = "hook_closing"
        return profiles

    def _score_highlight(self, scene: dict[str, Any]) -> int:
        merged_text = " ".join(
            [
                str(scene.get("description", "")).lower(),
                " ".join(str(item).lower() for item in scene.get("objects", [])),
                str(scene.get("transcription") or "").lower(),
            ]
        )
        score = 0
        for keyword in self.highlight_keywords:
            if keyword in merged_text:
                score += 2
        if any(token in merged_text for token in ("!", "！", "wow", "amazing")):
            score += 1
        return score

    def _trim_text(self, text: str, max_chars: int) -> str:
        normalized = re.sub(r"\s+", " ", text.strip())
        if len(normalized) <= max_chars:
            return normalized
        punctuated = re.split(r"([，。！？；,.!?;])", normalized)
        chunks: list[str] = []
        for token in punctuated:
            if not token:
                continue
            candidate = "".join(chunks) + token
            if len(candidate) > max_chars:
                break
            chunks.append(token)
        compact = "".join(chunks).strip()
        if compact:
            return compact
        return normalized[:max_chars].rstrip()

    def _limit_items_for_continuity(
        self,
        items: list[dict[str, Any]],
        scene_profiles: list[dict[str, Any]],
        total_duration_s: float,
    ) -> list[dict[str, Any]]:
        if not items:
            return items
        dynamic_limit = max(1, int(round(total_duration_s / max(self.target_segment_seconds, 0.5))))
        limit = min(self.max_sentences, dynamic_limit, len(items))
        if len(items) <= limit:
            return items

        scene_profile_map = {str(scene["scene_id"]): scene for scene in scene_profiles}
        ordered = sorted(
            items,
            key=lambda item: int(scene_profile_map.get(str(item["scene_id"]), {}).get("start_ms", item["index"])),
        )
        total = len(ordered)
        selected: set[int] = set()
        selected.add(0)
        if limit > 1:
            selected.add(total - 1)

        highlight_idx = max(
            range(total),
            key=lambda idx: int(scene_profile_map.get(str(ordered[idx]["scene_id"]), {}).get("highlight_score", 0)),
        )
        if len(selected) < limit:
            selected.add(highlight_idx)

        while len(selected) < limit:
            best_idx = None
            best_distance = -1
            for idx in range(total):
                if idx in selected:
                    continue
                nearest = min(abs(idx - picked) for picked in selected)
                if nearest > best_distance:
                    best_distance = nearest
                    best_idx = idx
            if best_idx is None:
                break
            selected.add(best_idx)

        return [ordered[idx] for idx in sorted(selected)]


service = CopyGenerationService()
mcp = FastMCP("copy-generation") if FastMCP else None

if mcp:

    @mcp.tool(name="generate_copy")
    async def generate_copy_tool(product_description: str, scenes: list[dict[str, Any]]) -> dict[str, Any]:
        return await service.generate_copy(product_description=product_description, scenes=scenes)


if __name__ == "__main__":  # pragma: no cover
    if not mcp:
        raise SystemExit("mcp sdk unavailable")
    mcp.run(transport="stdio")
