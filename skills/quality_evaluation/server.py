from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skills.common import get_settings
from skills.quality_evaluation.prohibited_checker import load_words, scan_prohibited
from skills.quality_evaluation.sync_checker import check_sync, probe_duration_ms
from skills.quality_evaluation.visual_checker import detect_visual_issues
from store.minio_client import MinioStore

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None


def split_bucket_object(path: str) -> tuple[str, str]:
    """分割存储桶和对象路径"""
    bucket, object_key = path.split("/", 1)
    return bucket, object_key


class QualityEvaluationService:
    def __init__(self) -> None:
        settings = get_settings()
        minio_cfg = settings.storage["minio"]
        self.buckets = minio_cfg["buckets"]
        quality_cfg = settings.data.get("quality_evaluation", {})
        self.sync_tolerance_ms = int(quality_cfg.get("sync_tolerance_ms", 120))
        self.words = load_words(settings.data["paths"]["prohibited_words"])
        self.minio = MinioStore(
            endpoint=minio_cfg["endpoint"],
            access_key=minio_cfg["access_key"],
            secret_key=minio_cfg["secret_key"],
            secure=minio_cfg.get("secure", False),
        )

    async def evaluate_quality(self, task_id: str, timeline_path: str, video_path: str) -> dict[str, Any]:
        try:
            timeline_bucket, timeline_object = split_bucket_object(timeline_path)
            video_bucket, video_object = split_bucket_object(video_path)
            timeline_raw = self.minio.download_bytes(timeline_bucket, timeline_object)
        except Exception:
            return {"error": "input_not_found", "missing": timeline_path}

        timeline = json.loads(timeline_raw.decode("utf-8"))

        with tempfile.TemporaryDirectory(prefix="evoclip-eval-") as tmp:
            tmp_path = Path(tmp)
            local_video = tmp_path / "output.mp4"
            try:
                self.minio.download_file(video_bucket, video_object, str(local_video))
            except Exception:
                return {"error": "input_not_found", "missing": video_path}

            audio_durations: dict[str, int] = {}
            for item in timeline:
                if item.get("final_audio_duration_ms") is not None:
                    continue
                audio_path = item.get("audio_path")
                if not audio_path:
                    continue
                try:
                    audio_bucket, audio_object = split_bucket_object(audio_path)
                    local_audio = tmp_path / Path(audio_object).name
                    self.minio.download_file(audio_bucket, audio_object, str(local_audio))
                    audio_durations[audio_path] = probe_duration_ms(local_audio)
                except Exception:
                    continue

            sync_errors = check_sync(timeline, audio_durations, tolerance_ms=self.sync_tolerance_ms)
            visual_issues = detect_visual_issues(local_video)
            prohibited_words = scan_prohibited(timeline, self.words)

        score = 100 - len(sync_errors) * 10 - len(visual_issues) * 15 - len(prohibited_words) * 20
        diagnosis = {
            "overall_score": max(score, 0),
            "sync_errors": sync_errors,
            "visual_issues": visual_issues,
            "prohibited_words": prohibited_words,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        diagnosis_key = f"{task_id}/diagnosis.json"
        self.minio.upload_bytes(
            self.buckets["output"],
            diagnosis_key,
            json.dumps(diagnosis, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        diagnosis["diagnosis_path"] = f"{self.buckets['output']}/{diagnosis_key}"
        return diagnosis


service = QualityEvaluationService()
mcp = FastMCP("quality-evaluation") if FastMCP else None

if mcp:

    @mcp.tool(name="evaluate_quality")
    async def evaluate_quality_tool(task_id: str, timeline_path: str, video_path: str) -> dict[str, Any]:
        return await service.evaluate_quality(task_id=task_id, timeline_path=timeline_path, video_path=video_path)


if __name__ == "__main__":  # pragma: no cover
    if not mcp:
        raise SystemExit("mcp sdk unavailable")
    mcp.run(transport="stdio")
