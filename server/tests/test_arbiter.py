import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import arbiter


@pytest.fixture(autouse=True)
def reset_arbiter_state(monkeypatch):
    arbiter._pending_tesseract.clear()
    arbiter._pending_order.clear()
    arbiter._agreement_history.clear()

    sink_calls = []
    monkeypatch.setattr(
        arbiter.sinks,
        "update",
        lambda player_id, track, source, confidence=None: sink_calls.append(
            (player_id, track, source, confidence)
        )
        or True,
    )
    return sink_calls


def test_tesseract_result_feeds_sinks_immediately(reset_arbiter_state):
    arbiter.record_tesseract("deck1", "100", "Artist - Title", 92.0)
    assert reset_arbiter_state == [("deck1", "Artist - Title", "tesseract", 92.0)]


def test_ondevice_result_without_matching_capture_is_ignored(reset_arbiter_state):
    result = arbiter.record_ondevice("deck1", "no-such-capture", "Artist - Title")
    assert result is None
    assert reset_arbiter_state == []


def test_ondevice_agreement_is_tracked_but_untrusted_result_skips_sinks(reset_arbiter_state):
    for i in range(arbiter.AGREEMENT_WINDOW_SIZE - 1):
        capture_id = str(i)
        arbiter.record_tesseract("deck1", capture_id, "Artist - Title", 90.0)
        agree = arbiter.record_ondevice("deck1", capture_id, "Artist - Title")
        assert agree is True

    assert arbiter.is_trusted("deck1") is False
    ondevice_calls = [call for call in reset_arbiter_state if call[2] == "ondevice"]
    assert ondevice_calls == []


def test_ondevice_result_feeds_sinks_once_trusted(reset_arbiter_state):
    for i in range(arbiter.AGREEMENT_WINDOW_SIZE):
        capture_id = str(i)
        arbiter.record_tesseract("deck1", capture_id, "Artist - Title", 90.0)
        arbiter.record_ondevice("deck1", capture_id, "Artist - Title")

    assert arbiter.is_trusted("deck1") is True

    reset_arbiter_state.clear()
    arbiter.record_tesseract("deck1", "later", "New Artist - New Title", 90.0)
    agree = arbiter.record_ondevice("deck1", "later", "New Artist - New Title")
    assert agree is True

    ondevice_calls = [call for call in reset_arbiter_state if call[2] == "ondevice"]
    assert ondevice_calls == [("deck1", "New Artist - New Title", "ondevice", None)]


def test_disagreement_is_recorded_and_lowers_trust(reset_arbiter_state):
    for i in range(arbiter.AGREEMENT_WINDOW_SIZE):
        capture_id = str(i)
        arbiter.record_tesseract("deck1", capture_id, "Artist - Title", 90.0)
        track = "Wrong Guess" if i % 2 == 0 else "Artist - Title"
        agree = arbiter.record_ondevice("deck1", capture_id, track)
        assert agree == (i % 2 == 1)

    assert arbiter.is_trusted("deck1") is False


def test_pending_tesseract_cache_is_bounded(reset_arbiter_state):
    for i in range(arbiter.PENDING_CAPACITY + 10):
        arbiter.record_tesseract("deck1", str(i), "Some Track", 90.0)

    assert len(arbiter._pending_tesseract) == arbiter.PENDING_CAPACITY
    assert ("deck1", "0") not in arbiter._pending_tesseract
    assert ("deck1", str(arbiter.PENDING_CAPACITY + 9)) in arbiter._pending_tesseract


def test_empty_tesseract_track_is_not_found_not_published(reset_arbiter_state):
    changed = arbiter.record_tesseract("deck1", "100", "   ", 95.0)
    assert changed is False
    assert reset_arbiter_state == []
    assert ("deck1", "100") not in arbiter._pending_tesseract


def test_low_confidence_tesseract_track_holds_last_known_good(reset_arbiter_state):
    changed = arbiter.record_tesseract(
        "deck1", "100", "Garbled Read", arbiter.TESSERACT_CONFIDENCE_THRESHOLD - 1
    )
    assert changed is False
    assert reset_arbiter_state == []
    assert ("deck1", "100") not in arbiter._pending_tesseract


def test_empty_ondevice_track_is_ignored(reset_arbiter_state):
    arbiter.record_tesseract("deck1", "100", "Artist - Title", 90.0)
    reset_arbiter_state.clear()
    result = arbiter.record_ondevice("deck1", "100", "  ")
    assert result is None
    assert reset_arbiter_state == []


def test_low_confidence_ondevice_track_is_ignored_and_not_scored(reset_arbiter_state):
    arbiter.record_tesseract("deck1", "100", "Artist - Title", 90.0)
    result = arbiter.record_ondevice(
        "deck1", "100", "Artist - Title", arbiter.ONDEVICE_CONFIDENCE_THRESHOLD - 0.1
    )
    assert result is None
    assert "deck1" not in arbiter._agreement_history
    # Still pending: a low-confidence on-device read should not consume
    # the cached Tesseract result, since no real comparison happened.
    assert ("deck1", "100") in arbiter._pending_tesseract
