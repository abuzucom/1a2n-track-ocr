"""Auto-labeled training data.

Stores each frame's ROI crop alongside its Tesseract output, for later
use training the on-device character classifier (see ml/train.py,
Phase 4). Every OCR'd frame is recorded, not just ones that changed
output; Tesseract's own errors will be present in these labels, so a
spot-check pass is needed before training, not blind trust.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import validation

DATASET_DIR = Path(os.environ.get("DATASET_DIR", "../ml/dataset"))
IMAGES_DIR = (DATASET_DIR / "images").resolve()
LABELS_PATH = DATASET_DIR / "labels.jsonl"

# One image per received frame, forever, is an unbounded disk write
# reachable by anyone who can call /frame. Collection stops at the cap
# rather than filling the volume; raise it deliberately when actually
# collecting a training set.
MAX_SAMPLES = int(os.environ.get("MAX_DATASET_SAMPLES", "20000"))

logger = logging.getLogger(__name__)

_capacity_warned = False
_sample_count = None


def _at_capacity() -> bool:
    """Check whether the dataset image directory is at capacity."""
    global _capacity_warned, _sample_count
    if _sample_count is None:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        _sample_count = sum(1 for _ in IMAGES_DIR.glob("*.jpg"))

    if _sample_count < MAX_SAMPLES:
        return False
    if not _capacity_warned:
        logger.warning(
            "dataset at capacity (%d samples), stopping collection; "
            "raise MAX_DATASET_SAMPLES to continue", MAX_SAMPLES,
        )
        _capacity_warned = True
    return True


def record(player_id: str, image_bytes: bytes, track: str, confidence: float) -> None:
    if _at_capacity():
        return

    timestamp_ms = int(time.time() * 1000)
    image_name = f"{player_id}_{timestamp_ms}.jpg"
    # player_id is validated at the HTTP boundary, but it lands in a
    # filename here and the bytes are caller-controlled, so the resolved
    # path is checked against IMAGES_DIR as well.
    target = validation.resolve_within(IMAGES_DIR, IMAGES_DIR / image_name)
    target.write_bytes(image_bytes)

    entry = {
        "image": image_name,
        "player_id": player_id,
        "track": track,
        "confidence": confidence,
        "timestamp_ms": timestamp_ms,
    }
    with open(LABELS_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")

    global _sample_count
    if _sample_count is not None:
        _sample_count += 1
