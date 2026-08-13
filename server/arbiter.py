"""Compares on-device and Tesseract OCR results for the same capture,
decides which one feeds sinks.py, and tracks on-device agreement.

Firmware always uploads a frame to /frame; it only ever adds a /result
call afterward, and only when a model is loaded and ready. So Tesseract
is the default-trusted source: /frame writes to sinks on every capture
that clears the confidence bar. A /result call, when it comes, is a
delayed comparison signal keyed on the same capture_id as the frame it
was derived from. It does not write to sinks unless the on-device
model's recent agreement rate with Tesseract has crossed
TRUST_THRESHOLD, per the plan's "default to Tesseract until on-device
agreement is consistently high."

An empty track from either OCR path means the ROI's text was not
found (e.g. the unit is on the Performance screen, which does not show
a track field), not a misread. Track holds the last known good value:
neither case overwrites sinks with a low-confidence or empty result.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Optional

import sinks

AGREEMENT_WINDOW_SIZE = 20
TRUST_THRESHOLD = 0.9
PENDING_CAPACITY = 200

# Ceiling on distinct player_id values whose agreement history is kept.
MAX_TRACKED_PLAYERS = 16

# Tesseract's image_to_data confidence is 0-100. Below this, a non-empty
# result is treated as too unreliable to publish or to use as ground
# truth for on-device agreement tracking.
TESSERACT_CONFIDENCE_THRESHOLD = 40.0

# The on-device model's per-character confidence is dequantized from an
# int8 softmax output, so it is a 0-1 float, not the 0-100 scale above.
ONDEVICE_CONFIDENCE_THRESHOLD = 0.6

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pending_tesseract: dict[tuple[str, str], str] = {}
_pending_order: deque[tuple[str, str]] = deque()
_agreement_history: dict[str, deque] = {}


def record_tesseract(player_id: str, capture_id: str, track: str, confidence: float) -> bool:
    """Handle a /frame result. Feeds sinks only if the read clears the
    confidence bar; caches it briefly either way so long as it is
    non-empty, so a later /result call for the same capture_id can be
    compared against it. Returns True if it changed published output."""
    stripped = track.strip()
    if not stripped:
        logger.info("tesseract: no track text found for %s/%s", player_id, capture_id)
        return False

    if confidence < TESSERACT_CONFIDENCE_THRESHOLD:
        logger.info(
            "tesseract: rejecting low-confidence read for %s/%s (%.1f < %.1f): %r",
            player_id, capture_id, confidence, TESSERACT_CONFIDENCE_THRESHOLD, track,
        )
        return False

    key = (player_id, capture_id)
    with _lock:
        if key not in _pending_tesseract:
            if len(_pending_order) >= PENDING_CAPACITY:
                oldest = _pending_order.popleft()
                _pending_tesseract.pop(oldest, None)
            _pending_order.append(key)
        _pending_tesseract[key] = track

    return sinks.update(player_id, track, source="tesseract", confidence=confidence)


def _record_agreement(player_id: str, agree: bool) -> None:
    # Each deque is bounded, but the dict holding them was not, and it is
    # keyed by a request-supplied player_id. Cap the cardinality too.
    with _lock:
        history = _agreement_history.get(player_id)
        if history is None:
            if len(_agreement_history) >= MAX_TRACKED_PLAYERS:
                logger.warning(
                    "not tracking agreement for new player_id %r: at the %d limit",
                    player_id, MAX_TRACKED_PLAYERS,
                )
                return
            history = deque(maxlen=AGREEMENT_WINDOW_SIZE)
            _agreement_history[player_id] = history
        history.append(agree)


def is_trusted(player_id: str) -> bool:
    """True once the on-device model's recent agreement rate for
    player_id has a full window and clears TRUST_THRESHOLD.

    Reads under the lock. _record_agreement appends to these deques from
    other request threads, and summing one while it is being appended to
    can raise, or can average over a window that changed underneath the
    read. Callers must not already hold the lock; the only caller,
    record_ondevice, releases it before calling.
    """
    with _lock:
        history = _agreement_history.get(player_id)
        if history is None or len(history) < AGREEMENT_WINDOW_SIZE:
            return False
        return sum(history) / len(history) >= TRUST_THRESHOLD


def record_ondevice(
    player_id: str, capture_id: str, track: str, confidence: Optional[float] = None
) -> Optional[bool]:
    """Handle a /result result. Compares against the cached Tesseract
    result for the same capture_id, if still pending. Returns whether
    they agreed, or None if there was nothing to compare against (no
    matching Tesseract result cached, an empty on-device track, or a
    confidence below ONDEVICE_CONFIDENCE_THRESHOLD). Writes to sinks
    only once the on-device model is trusted for player_id."""
    stripped = track.strip()
    if not stripped:
        logger.info("on-device: no track text found for %s/%s", player_id, capture_id)
        return None

    # Fail closed. This previously read "confidence is not None and
    # confidence < THRESHOLD", so omitting the field from the request
    # skipped the gate entirely and an unmeasured result was treated as
    # trustworthy. An absent confidence is now untrusted.
    if confidence is None:
        logger.info(
            "on-device: rejecting result with no confidence for %s/%s", player_id, capture_id
        )
        return None

    if confidence < ONDEVICE_CONFIDENCE_THRESHOLD:
        logger.info(
            "on-device: rejecting low-confidence read for %s/%s (%.2f < %.2f): %r",
            player_id, capture_id, confidence, ONDEVICE_CONFIDENCE_THRESHOLD, track,
        )
        return None

    key = (player_id, capture_id)
    with _lock:
        tesseract_track = _pending_tesseract.pop(key, None)

    if tesseract_track is None:
        logger.info("on-device: no pending Tesseract result for %s/%s", player_id, capture_id)
        return None

    agree = track == tesseract_track
    _record_agreement(player_id, agree)
    if not agree:
        logger.warning(
            "arbiter: disagreement for %s/%s: on-device=%r tesseract=%r",
            player_id, capture_id, track, tesseract_track,
        )

    if is_trusted(player_id):
        sinks.update(player_id, track, source="ondevice", confidence=None)

    return agree
