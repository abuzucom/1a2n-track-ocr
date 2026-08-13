"""Shared I/O for the per-character dataset (chars/images + labels.jsonl).

Used by both prepare_chars.py (real captures) and synth.py (synthetic
renders) so the two producers write one consistent format. Images are
stored flat with generated filenames, not one folder per class: a
folder-per-class layout would collide on a case-insensitive filesystem
(e.g. "A" and "a" as the same directory on Windows).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from PIL import Image

CHARS_DIR = Path(os.environ.get("CHARS_DATASET_DIR", "dataset/chars"))
IMAGES_DIR = CHARS_DIR / "images"
LABELS_PATH = CHARS_DIR / "labels.jsonl"


def save_char(image: Image.Image, char: str, source: str, **extra) -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    image_name = f"{uuid.uuid4().hex}.png"
    image.save(IMAGES_DIR / image_name)

    entry = {"image": image_name, "char": char, "source": source, **extra}
    with open(LABELS_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def load_labels() -> list[dict]:
    if not LABELS_PATH.exists():
        return []
    with open(LABELS_PATH, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
