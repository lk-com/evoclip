from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def _laplacian_variance(gray: np.ndarray) -> float:
    """计算拉普拉斯方差（用于检测模糊）"""
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    padded = np.pad(gray, ((1, 1), (1, 1)), mode="edge")
    conv = np.zeros_like(gray, dtype=np.float32)
    for i in range(gray.shape[0]):
        for j in range(gray.shape[1]):
            conv[i, j] = np.sum(padded[i : i + 3, j : j + 3] * kernel)
    return float(np.var(conv))


def detect_visual_issues(video_path: Path) -> list[dict]:
    """检测视频的视觉问题（黑屏、模糊等）"""
    with tempfile.TemporaryDirectory(prefix="evoclip-visual-") as tmp:
        pattern = Path(tmp) / "frame_%06d.jpg"
        subprocess.check_call(
            ["ffmpeg", "-y", "-i", str(video_path), "-vf", "fps=1", str(pattern)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        frame_files = sorted(Path(tmp).glob("frame_*.jpg"))
        issues: list[dict] = []
        for index, frame in enumerate(frame_files):
            image = Image.open(frame).convert("L")
            gray = np.array(image, dtype=np.float32)
            brightness = float(np.mean(gray))
            blur_var = _laplacian_variance(gray)
            start_ms = index * 1000
            end_ms = start_ms + 1000

            if brightness < 10:
                issues.append({"type": "black_screen", "start_ms": start_ms, "end_ms": end_ms})
            if blur_var < 100:
                issues.append({"type": "blur", "start_ms": start_ms, "end_ms": end_ms})

        return issues
