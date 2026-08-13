"""Ordering, atomicity, and quota bounds under concurrent callers.

These assert invariants rather than racing and hoping, because a timing
dependent test that passes by luck is worse than none: it reports green
on the broken code often enough to be believed.
"""

import importlib
import inspect
import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture
def sinks_module(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    import sinks
    importlib.reload(sinks)
    sinks._state.clear()
    return sinks


@pytest.fixture
def dataset_module(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "dataset"))
    monkeypatch.setenv("MAX_DATASET_SAMPLES", "1000")
    monkeypatch.setenv("MAX_DATASET_BYTES", "1000")
    import dataset
    importlib.reload(dataset)
    return dataset


# --- publication ordering and atomicity, audit finding 6 -------------

def test_publish_happens_while_the_state_lock_is_held(sinks_module):
    """The snapshot and its publication must not be separable.

    Previously the lock was released after snapshotting and before
    writing, so two updates could publish out of order and the older
    snapshot could land last, permanently restoring stale output.
    """
    observed = {}
    original = sinks_module._write_json

    def observing_write(snapshot):
        observed["locked_during_write"] = sinks_module._lock.locked()
        return original(snapshot)

    sinks_module._write_json = observing_write
    try:
        sinks_module.update("deck1", "Artist - Title", source="tesseract", confidence=90.0)
    finally:
        sinks_module._write_json = original

    assert observed.get("locked_during_write") is True, (
        "published after releasing the lock; a concurrent update can overtake it"
    )


def test_json_is_replaced_atomically(sinks_module, monkeypatch):
    """A reader must never observe a half written now_playing.json.

    Writing in place truncates first, so a poll landing mid-write reads
    an empty or partial document. Building a temp file and renaming it
    makes the swap atomic.
    """
    calls = []
    real_replace = os.replace

    def spying_replace(src, dst):
        calls.append(str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(sinks_module.os, "replace", spying_replace)
    sinks_module.update("deck1", "Artist - Title", source="tesseract", confidence=90.0)

    assert any("now_playing.json" in dst for dst in calls), (
        "now_playing.json written in place rather than atomically replaced"
    )


def test_concurrent_updates_leave_file_matching_final_state(sinks_module):
    """Whatever order threads finish in, the file must match memory."""
    def write(index):
        sinks_module.update("deck1", f"Track {index}", source="tesseract", confidence=90.0)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(24)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    payload = json.loads((sinks_module.OUTPUT_DIR / "now_playing.json").read_text())
    assert payload["players"]["deck1"]["track"] == sinks_module._state["deck1"]["track"]


def test_no_temp_files_left_behind(sinks_module):
    sinks_module.update("deck1", "Artist - Title", source="tesseract", confidence=90.0)
    leftovers = [p.name for p in sinks_module.OUTPUT_DIR.iterdir() if p.suffix not in (".txt", ".json")]
    assert leftovers == []


# --- arbiter history, audit finding 6 --------------------------------

def test_is_trusted_reads_history_under_the_lock():
    """Reading a deque another thread appends to can raise.

    _record_agreement mutates _agreement_history under the lock while
    is_trusted summed it without one. Asserted on the source because a
    race that only sometimes raises is not a reliable test.
    """
    import arbiter
    source = inspect.getsource(arbiter.is_trusted)
    assert "_lock" in source, "is_trusted reads shared history without the lock"


def test_agreement_tracking_survives_concurrent_readers():
    import arbiter
    arbiter._agreement_history.clear()
    errors = []

    def record():
        try:
            for _ in range(200):
                arbiter._record_agreement("deck1", True)
        except Exception as error:
            errors.append(error)

    def read():
        try:
            for _ in range(200):
                arbiter.is_trusted("deck1")
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=record), threading.Thread(target=read)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


# --- dataset quota, audit finding 7 ----------------------------------

def test_byte_quota_stops_collection(dataset_module):
    """A count-only quota is not a storage bound.

    20000 samples times the 4MB upload cap is roughly 78 GiB, which is
    not a limit anyone intended.
    """
    payload = b"\xff\xd8\xff" + b"\x00" * 400
    for i in range(10):
        dataset_module.record("deck1", payload, f"Track {i}", 90.0)

    written = sum(p.stat().st_size for p in dataset_module.IMAGES_DIR.glob("*.jpg"))
    assert written <= dataset_module.MAX_DATASET_BYTES * 1.5, (
        f"wrote {written} bytes against a {dataset_module.MAX_DATASET_BYTES} byte quota"
    )


def test_same_millisecond_writes_do_not_collide(dataset_module, monkeypatch):
    """Filenames were player_id plus epoch milliseconds.

    Two frames for one rig inside the same millisecond produced the same
    filename, so one image silently overwrote the other while both got
    label rows, leaving a label pointing at the wrong image.
    """
    monkeypatch.setattr(dataset_module.time, "time", lambda: 1_700_000_000.0)
    payload = b"\xff\xd8\xff" + b"\x00" * 16

    dataset_module.record("deck1", payload, "Track A", 90.0)
    dataset_module.record("deck1", payload, "Track B", 90.0)

    images = list(dataset_module.IMAGES_DIR.glob("*.jpg"))
    assert len(images) == 2, f"expected 2 distinct images, found {len(images)}"


def test_concurrent_records_respect_the_quota(dataset_module):
    payload = b"\xff\xd8\xff" + b"\x00" * 200

    def write():
        for i in range(10):
            dataset_module.record("deck1", payload, f"Track {i}", 90.0)

    threads = [threading.Thread(target=write) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    written = sum(p.stat().st_size for p in dataset_module.IMAGES_DIR.glob("*.jpg"))
    assert written <= dataset_module.MAX_DATASET_BYTES * 1.5, (
        f"concurrent writers exceeded the quota: {written} bytes"
    )
