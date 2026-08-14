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
import shutil
import threading
import time
import uuid
from pathlib import Path

import validation

DATASET_DIR = Path(os.environ.get("DATASET_DIR", "../ml/dataset"))
IMAGES_DIR = (DATASET_DIR / "images").resolve()
LABELS_PATH = DATASET_DIR / "labels.jsonl"

# One image per frame, forever, is an unbounded disk write reachable by
# anyone who can call /frame. Raise these deliberately when collecting a
# training set.
MAX_SAMPLES = int(os.environ.get("MAX_DATASET_SAMPLES", "20000"))

# A count is not a storage bound: 20000 samples at the 4MB upload cap is
# roughly 78 GiB. Whichever limit is reached first stops collection.
MAX_DATASET_BYTES = int(os.environ.get("MAX_DATASET_BYTES", str(2 * 1024 * 1024 * 1024)))

# Stop before the volume itself is full, so filling the dataset cannot
# take the rest of the machine down with it.
MIN_FREE_BYTES = int(os.environ.get("MIN_FREE_DISK_BYTES", str(512 * 1024 * 1024)))

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_capacity_warned = False
_sample_count = None
_sample_bytes = 0


def _warn_once(reason: str) -> None:
    global _capacity_warned
    if not _capacity_warned:
        logger.warning("dataset collection stopped: %s", reason)
        _capacity_warned = True


def _reserve(size: int) -> bool:
    """Claim quota for one sample of `size` bytes, or return False.

    Reserving under the lock before writing, rather than checking and
    then writing, is what stops concurrent callers from each observing
    spare capacity and collectively blowing past the limit.
    """
    global _sample_count, _sample_bytes
    with _lock:
        if _sample_count is None:
            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            existing = [p for p in IMAGES_DIR.glob("*.jpg")]
            _sample_count = len(existing)
            _sample_bytes = sum(p.stat().st_size for p in existing)

        if _sample_count >= MAX_SAMPLES:
            _warn_once(f"at the {MAX_SAMPLES} sample limit")
            return False
        if _sample_bytes + size > MAX_DATASET_BYTES:
            _warn_once(f"at the {MAX_DATASET_BYTES} byte limit")
            return False
        if shutil.disk_usage(IMAGES_DIR).free - size < MIN_FREE_BYTES:
            _warn_once(f"free space would drop below {MIN_FREE_BYTES} bytes")
            return False

        _sample_count += 1
        _sample_bytes += size
        return True


def _release(size: int) -> None:
    """Give back a reservation whose write did not happen."""
    global _sample_count, _sample_bytes
    with _lock:
        if _sample_count is not None:
            _sample_count -= 1
            _sample_bytes -= size


def record(player_id: str, image_bytes: bytes, track: str, confidence: float) -> None:
    if not _reserve(len(image_bytes)):
        return

    timestamp_ms = int(time.time() * 1000)
    # The uuid suffix is what makes this collision resistant. Keying on
    # player_id and epoch milliseconds alone meant two frames for one rig
    # inside the same millisecond produced the same filename, so one
    # image silently replaced the other while both wrote label rows,
    # leaving a label pointing at an image it does not describe.
    image_name = f"{player_id}_{timestamp_ms}_{uuid.uuid4().hex[:12]}.jpg"
    # player_id is validated at the HTTP boundary, but it lands in a
    # filename here and the bytes are caller-controlled, so the resolved
    # path is checked against IMAGES_DIR as well.
    target = validation.resolve_within(IMAGES_DIR, IMAGES_DIR / image_name)

    try:
        target.write_bytes(image_bytes)
    except OSError as error:
        _release(len(image_bytes))
        logger.warning("dataset image write failed for %s: %s", player_id, error)
        return

    entry = {
        "image": image_name,
        "player_id": player_id,
        "track": track,
        "confidence": confidence,
        "timestamp_ms": timestamp_ms,
    }
    # Serialized: concurrent appends can interleave inside a single line
    # and corrupt the JSONL, which is the training set's index.
    with _lock:
        with open(LABELS_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
