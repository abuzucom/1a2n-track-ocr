"""Compares on-device and Tesseract OCR results for the same capture,
decides which one feeds sinks.py, and tracks on-device agreement.

Firmware always uploads a frame to /frame; it only ever adds a /result
call afterward, and only when a model is loaded and ready. So Tesseract
is the default-trusted source: /frame writes to sinks immediately on
every capture. A /result call, when it comes, is a delayed comparison
signal keyed on the same capture_id as the frame it was derived from.
It does not write to sinks unless the on-device model's recent agreement
rate with Tesseract has crossed TRUST_THRESHOLD, per the plan's "default
to Tesseract until on-device agreement is consistently high."
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import sinks

AGREEMENT_WINDOW_SIZE = 20
TRUST_THRESHOLD = 0.9
PENDING_CAPACITY = 200

_lock = threading.Lock()
_pending_tesseract: dict[tuple[str, str], str] = {}
_pending_order: deque[tuple[str, str]] = deque()
_agreement_history: dict[str, deque] = {}


def record_tesseract(player_id: str, capture_id: str, track: str, confidence: Optional[float]) -> bool:
    """Handle a /frame result. Feeds sinks immediately and caches the
    result briefly so a later /result call for the same capture_id can
    be compared against it."""
    key = (player_id, capture_id)
    with _lock:
        if key not in _pending_tesseract and len(_pending_order) >= PENDING_CAPACITY:
            oldest = _pending_order.popleft()
            _pending_tesseract.pop(oldest, None)
        if key not in _pending_tesseract:
            _pending_order.append(key)
        _pending_tesseract[key] = track

    return sinks.update(player_id, track, source="tesseract", confidence=confidence)


def _record_agreement(player_id: str, agree: bool) -> None:
    history = _agreement_history.setdefault(player_id, deque(maxlen=AGREEMENT_WINDOW_SIZE))
    history.append(agree)


def is_trusted(player_id: str) -> bool:
    """True once the on-device model's recent agreement rate for
    player_id has a full window and clears TRUST_THRESHOLD."""
    history = _agreement_history.get(player_id)
    if history is None or len(history) < AGREEMENT_WINDOW_SIZE:
        return False
    return sum(history) / len(history) >= TRUST_THRESHOLD


def record_ondevice(player_id: str, capture_id: str, track: str) -> Optional[bool]:
    """Handle a /result result. Compares against the cached Tesseract
    result for the same capture_id, if still pending. Returns whether
    they agreed, or None if there was nothing to compare against.
    Writes to sinks only once the on-device model is trusted for
    player_id."""
    key = (player_id, capture_id)
    with _lock:
        tesseract_track = _pending_tesseract.pop(key, None)

    if tesseract_track is None:
        print(f"arbiter: no pending Tesseract result for {player_id}/{capture_id}")
        return None

    agree = track == tesseract_track
    _record_agreement(player_id, agree)
    if not agree:
        print(
            f"arbiter: disagreement for {player_id}/{capture_id}: "
            f"on-device={track!r} tesseract={tesseract_track!r}"
        )

    if is_trusted(player_id):
        sinks.update(player_id, track, source="ondevice", confidence=None)

    return agree
