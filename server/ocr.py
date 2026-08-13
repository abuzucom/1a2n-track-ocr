"""Tesseract OCR on a track-name ROI crop."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

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


def preprocess(image_bytes: bytes) -> np.ndarray:
    """Decode and prepare an ROI crop for OCR: grayscale, upscale, threshold."""
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
    data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)

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
