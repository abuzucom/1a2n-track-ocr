"""Derive per-character crops from ml/dataset/ (Phase 3's whole-track
captures) using Tesseract's character-level bounding boxes.

Phase 3's labels.jsonl only has whole-track strings per image, not
character boxes, so this re-runs Tesseract at the character level on
each stored image rather than changing Phase 3's schema. Tesseract's box
interface has no per-character confidence, so images below
CONFIDENCE_THRESHOLD (by mean word confidence) are skipped entirely, and
the count of skipped/out-of-charset boxes is reported, not silently
dropped.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image

import chars_dataset
from charset import CHAR_TO_INDEX, PATCH_SIZE

DATASET_DIR = Path(os.environ.get("DATASET_DIR", "dataset"))
IMAGES_DIR = DATASET_DIR / "images"
LABELS_PATH = DATASET_DIR / "labels.jsonl"

_FALLBACK_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
]


def _resolve_tesseract_cmd() -> str:
    override = os.environ.get("TESSERACT_CMD")
    if override:
        return override
    if shutil.which("tesseract"):
        return "tesseract"
    for path in _FALLBACK_TESSERACT_PATHS:
        if os.path.isfile(path):
            return path
    return "tesseract"


pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract_cmd()

CONFIDENCE_THRESHOLD = 60.0


def load_track_labels() -> list[dict]:
    if not LABELS_PATH.exists():
        return []
    with open(LABELS_PATH, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _otsu_threshold(gray: np.ndarray) -> int:
    histogram, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = gray.size
    sum_all = np.dot(np.arange(256), histogram)
    sum_background = 0.0
    weight_background = 0.0
    max_variance = 0.0
    best_threshold = 0
    for level in range(256):
        weight_background += histogram[level]
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += level * histogram[level]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_all - sum_background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > max_variance:
            max_variance = variance
            best_threshold = level
    return best_threshold


def preprocess(image: Image.Image) -> Image.Image:
    """Grayscale, upscale, and Otsu-threshold, matching server/ocr.py's
    preprocessing so character boxes are detected as reliably here as in
    the live OCR path."""
    gray = image.convert("L")
    upscaled = gray.resize((gray.width * 3, gray.height * 3), Image.BICUBIC)
    array = np.array(upscaled)
    threshold = _otsu_threshold(array)
    binary = (array > threshold).astype(np.uint8) * 255
    return Image.fromarray(binary)


def _mean_word_confidence(image: Image.Image) -> float:
    """Tesseract's box interface (used for character segmentation below)
    carries no confidence field. Approximate a per-character confidence
    with the image's mean word-level confidence from image_to_data
    instead of leaving it unset; every character from the same image
    gets this one value, not a true per-character score."""
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    confidences = [float(c) for c in data["conf"] if float(c) >= 0]
    return sum(confidences) / len(confidences) if confidences else 0.0


def extract_chars(image_path: Path) -> tuple[list[tuple[str, Image.Image, float]], int]:
    """Return ((char, cropped_patch, confidence) list, dropped_count).

    Boxes are dropped for not being a single in-charset character, for a
    zero-size box, or for the image's mean confidence falling below
    CONFIDENCE_THRESHOLD."""
    image = preprocess(Image.open(image_path))
    confidence = _mean_word_confidence(image)
    boxes = pytesseract.image_to_boxes(image, output_type=pytesseract.Output.DICT)
    if confidence < CONFIDENCE_THRESHOLD:
        return [], len(boxes["char"])

    height = image.height

    results = []
    dropped = 0
    for i, char in enumerate(boxes["char"]):
        if char not in CHAR_TO_INDEX:
            dropped += 1
            continue
        left, right = boxes["left"][i], boxes["right"][i]
        # image_to_boxes returns Tesseract's raw box-file coordinates
        # (origin at bottom-left); flip to top-left-origin pixel rows.
        top = height - boxes["top"][i]
        bottom = height - boxes["bottom"][i]
        if right <= left or bottom <= top:
            dropped += 1
            continue
        crop = image.crop((left, top, right, bottom))
        crop = crop.resize((PATCH_SIZE, PATCH_SIZE))
        results.append((char, crop, confidence))
    return results, dropped


def run() -> None:
    track_labels = load_track_labels()
    kept = 0
    dropped = 0

    for entry in track_labels:
        image_path = IMAGES_DIR / entry["image"]
        if not image_path.is_file():
            continue
        chars, drop_count = extract_chars(image_path)
        dropped += drop_count
        for char, patch, confidence in chars:
            chars_dataset.save_char(
                patch,
                char,
                source="real",
                source_image=entry["image"],
                confidence=confidence,
            )
            kept += 1

    print(f"kept {kept} character crops (confidence >= {CONFIDENCE_THRESHOLD})")
    print(f"dropped {dropped} boxes below the confidence threshold or out of charset")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
