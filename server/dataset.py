"""Auto-labeled training data.

Stores each frame's ROI crop alongside its Tesseract output, for later
use training the on-device character classifier (see ml/train.py,
Phase 4). Every OCR'd frame is recorded, not just ones that changed
output; Tesseract's own errors will be present in these labels, so a
spot-check pass is needed before training, not blind trust.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

DATASET_DIR = Path(os.environ.get("DATASET_DIR", "../ml/dataset"))
IMAGES_DIR = DATASET_DIR / "images"
LABELS_PATH = DATASET_DIR / "labels.jsonl"


def record(player_id: str, image_bytes: bytes, track: str, confidence: float) -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_ms = int(time.time() * 1000)
    image_name = f"{player_id}_{timestamp_ms}.jpg"
    (IMAGES_DIR / image_name).write_bytes(image_bytes)

    entry = {
        "image": image_name,
        "player_id": player_id,
        "track": track,
        "confidence": confidence,
        "timestamp_ms": timestamp_ms,
    }
    with open(LABELS_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
