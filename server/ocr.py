"""Tesseract OCR on a track-name ROI crop."""

from __future__ import annotations

import io
import os
import shutil
import threading
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from PIL import Image

# The ROI crop is one line of text, on the order of 480x40, so this
# leaves ample headroom. The pipeline upscales 3x, multiplying pixel
# count ninefold, so 2 Mpx caps the worst case at an 18 Mpx array.
MAX_IMAGE_PIXELS = 2_000_000
MAX_IMAGE_DIMENSION = 4096

# Tesseract is a subprocess with no natural bound on runtime. Without a
# deadline a pathological image blocks a worker indefinitely.
TESSERACT_TIMEOUT_SECONDS = 20

# Each call spawns a subprocess, and FastAPI runs sync endpoints in a
# threadpool, so without a bound concurrent requests contend for CPU.
MAX_CONCURRENT_OCR = 2
_ocr_slots = threading.Semaphore(MAX_CONCURRENT_OCR)

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


@dataclass
class OcrResult:
    track: str
    confidence: float


def inspect_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) from the image header without decoding it.

    Pillow parses the header lazily, so this reads the declared size
    without allocating the pixel buffer. Compressed size is no guide to
    decoded size: a solid 12000x12000 PNG is tens of KB on the wire and
    roughly 430 MB decoded, so the check has to happen here rather than
    after cv2.imdecode.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            return probe.size
    except Exception as error:
        raise ValueError(f"could not read image header: {error}") from error


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Decode and prepare an ROI crop for OCR: grayscale, upscale, threshold."""
    width, height = inspect_dimensions(image_bytes)
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(
            f"image {width}x{height} exceeds the {MAX_IMAGE_DIMENSION}px side limit"
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError(
            f"image {width}x{height} exceeds the {MAX_IMAGE_PIXELS} pixel limit"
        )

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("could not decode image bytes")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    upscaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, thresholded = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresholded


def extract_track_text(image_bytes: bytes) -> OcrResult:
    """Run Tesseract on an ROI crop and return the recognized track text."""
    processed = preprocess(image_bytes)

    # Bounded slots, and a deadline inside each one. The semaphore caps
    # how many Tesseract subprocesses exist at once; the timeout stops
    # any single one holding its slot forever.
    with _ocr_slots:
        try:
            data = pytesseract.image_to_data(
                processed,
                output_type=pytesseract.Output.DICT,
                timeout=TESSERACT_TIMEOUT_SECONDS,
            )
        except RuntimeError as error:
            # pytesseract raises RuntimeError on timeout. Surface it as
            # ValueError so app.py's existing handler returns 400 rather
            # than an unhandled 500.
            raise ValueError(f"OCR timed out after {TESSERACT_TIMEOUT_SECONDS}s") from error

    words = []
    confidences = []
    for text, conf in zip(data["text"], data["conf"]):
        stripped = text.strip()
        if not stripped:
            continue
        confidence = float(conf)
        if confidence < 0:
            continue
        words.append(stripped)
        confidences.append(confidence)

    track = " ".join(words)
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrResult(track=track, confidence=mean_confidence)
