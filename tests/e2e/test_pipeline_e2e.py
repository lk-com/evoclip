from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests


pytestmark = pytest.mark.e2e


@pytest.mark.skipif(not os.getenv("EVOCLIP_E2E"), reason="set EVOCLIP_E2E=1 to run e2e")
def test_full_pipeline_generates_output() -> None:
    base = os.getenv("EVOCLIP_BASE_URL", "http://127.0.0.1:8000")
    fixture_video = Path("tests/fixtures/sample_30s.mp4")
    product_desc = Path("tests/fixtures/product_description.txt").read_text(encoding="utf-8").strip()

    with fixture_video.open("rb") as fh:
        resp = requests.post(
            f"{base}/tasks",
            files={"video": (fixture_video.name, fh, "video/mp4")},
            data={"product_description": product_desc},
            timeout=30,
        )
    resp.raise_for_status()
    task_id = resp.json()["task_id"]

    for _ in range(180):
        status_resp = requests.get(f"{base}/tasks/{task_id}", timeout=10)
        status_resp.raise_for_status()
        payload = status_resp.json()
        if payload["status"] in {"completed", "failed"}:
            break
        time.sleep(2)
    else:
        raise AssertionError("task_timeout")

    assert payload["status"] == "completed"
    assert "video-render" in payload["detail"]
    assert "quality-evaluation" in payload["detail"]
    assert "skill-optimization" in payload["detail"]

    dl_resp = requests.get(f"{base}/tasks/{task_id}/download", timeout=60)
    dl_resp.raise_for_status()
    assert dl_resp.headers["content-type"].startswith("video/")
