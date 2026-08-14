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
import os
import shutil
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image

import chars_dataset
import dataset_io
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
TESSERACT_TIMEOUT_SECONDS = 20


class LabelAlignmentError(ValueError):
    """Raised when Tesseract boxes do not match the expected track."""


def load_track_labels() -> list[dict]:
    return dataset_io.load_bounded_jsonl(LABELS_PATH)


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
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        timeout=TESSERACT_TIMEOUT_SECONDS,
    )
    confidences = [float(c) for c in data["conf"] if float(c) >= 0]
    return sum(confidences) / len(confidences) if confidences else 0.0


def align_box_labels(expected_text: str, box_chars: list[str]) -> list[str]:
    """Return expected labels after an exact, space-aware alignment."""
    if not expected_text:
        raise LabelAlignmentError("expected track is empty")
    if any(char.isspace() and char != " " for char in expected_text):
        raise LabelAlignmentError("expected track contains unsupported whitespace")
    expected_chars = [char for char in expected_text if char != " "]
    unsupported = [char for char in expected_chars if char not in CHAR_TO_INDEX]
    if unsupported:
        raise LabelAlignmentError(f"expected track contains unsupported characters: {unsupported!r}")
    if box_chars != expected_chars:
        raise LabelAlignmentError(
            f"Tesseract box sequence {''.join(box_chars)!r} does not match expected "
            f"track {''.join(expected_chars)!r}"
        )
    return expected_chars


def extract_chars_from_image(
    source_image: Image.Image,
    expected_text: str | None,
    expected_len: int | None = None,
) -> tuple[list[tuple[str, Image.Image, float]], int]:
    """Extract aligned character patches from one loaded track image."""
    image = preprocess(source_image)
    if expected_len is None:
        expected_len = len(expected_text.replace(" ", "")) if expected_text is not None else 0
    confidence = _mean_word_confidence(image)
    if confidence < CONFIDENCE_THRESHOLD:
        return [], expected_len

    boxes = pytesseract.image_to_boxes(
        image,
        output_type=pytesseract.Output.DICT,
        timeout=TESSERACT_TIMEOUT_SECONDS,
    )
    labels = boxes["char"]
    if expected_text is not None:
        labels = align_box_labels(expected_text, labels)
    results = []
    dropped = 0
    for i, char in enumerate(labels):
        if char not in CHAR_TO_INDEX:
            dropped += 1
            continue
        left, right = boxes["left"][i], boxes["right"][i]
        top = image.height - boxes["top"][i]
        bottom = image.height - boxes["bottom"][i]
        if right <= left or bottom <= top:
            dropped += 1
            continue
        crop = image.crop((left, top, right, bottom)).resize((PATCH_SIZE, PATCH_SIZE))
        results.append((char, crop, confidence))
    return results, dropped


def extract_chars(
    image_path: Path,
    expected_len: int,
    *,
    expected_text: str | None = None,
) -> tuple[list[tuple[str, Image.Image, float]], int]:
    """Return ((char, cropped_patch, confidence) list, dropped_count).

    Boxes are dropped for not being a single in-charset character, for a
    zero-size box, or for the image's mean confidence falling below
    CONFIDENCE_THRESHOLD."""
    image = dataset_io.load_track_image(image_path)
    try:
        return extract_chars_from_image(image, expected_text, expected_len)
    except RuntimeError as error:
        if str(error) == "Tesseract process timeout":
            raise RuntimeError(f"Tesseract timed out for {image_path.name}") from error
        raise


def run() -> None:
    track_labels = load_track_labels()
    chars_dataset.init_dirs()
    kept = 0
    dropped = 0
    entries = []

    for entry in track_labels:
        image_path = dataset_io.resolve_track_image(IMAGES_DIR, entry.get("image"))
        expected_text = entry.get("track")
        if not isinstance(expected_text, str):
            raise RuntimeError(f"track label is not text for {image_path.name}")
        expected_len = len(expected_text.replace(" ", ""))
        try:
            chars, drop_count = extract_chars(
                image_path,
                expected_len,
                expected_text=expected_text,
            )
        except LabelAlignmentError as error:
            print(f"skipping {image_path.name}: {error}")
            dropped += expected_len
            continue
        dropped += drop_count
        for char, patch, confidence in chars:
            dataset_entry = chars_dataset.save_char(
                patch,
                char,
                source="real",
                source_image=entry["image"],
                confidence=confidence,
            )
            entries.append(dataset_entry)
            kept += 1

    chars_dataset.save_labels(entries)

    print(f"kept {kept} character crops (confidence >= {CONFIDENCE_THRESHOLD})")
    print(f"dropped {dropped} boxes because of confidence, geometry, or label alignment")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
