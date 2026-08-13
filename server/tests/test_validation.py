import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import validation

TOKEN = "test-token-abcdefghijklmnop"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKEND_TOKEN", TOKEN)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "dataset"))
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)

    import auth, sinks, dataset, app as app_module
    for module in (auth, sinks, dataset, app_module):
        importlib.reload(module)

    from fastapi.testclient import TestClient
    return TestClient(app_module.app), tmp_path


# --- validate_identifier ---------------------------------------------

@pytest.mark.parametrize("value", ["deck1", "a", "A_b-9", "x" * 64])
def test_valid_identifiers_accepted(value):
    assert validation.validate_identifier(value, "player_id") == value


@pytest.mark.parametrize("value", [
    "../../evil",            # relative traversal
    "..",
    "C:/Windows/Temp/evil",  # pathlib discards the left operand on absolute
    "/etc/passwd",
    "deck/1",
    "deck\\1",
    "deck.1",                # dots excluded so no traversal component forms
    "deck:1",                # NTFS alternate data stream
    "",
    "x" * 65,
    "deck 1",
])
def test_dangerous_identifiers_rejected(value):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        validation.validate_identifier(value, "player_id")
    assert excinfo.value.status_code == 422


# --- resolve_within, the defense-in-depth layer ----------------------

def test_resolve_within_allows_contained_path(tmp_path):
    base = tmp_path / "output"
    base.mkdir()
    assert validation.resolve_within(base, base / "now_playing_deck1.txt")


def test_resolve_within_rejects_traversal(tmp_path):
    base = tmp_path / "output"
    base.mkdir()
    with pytest.raises(ValueError):
        validation.resolve_within(base, base / ".." / ".." / "evil.txt")


def test_resolve_within_rejects_absolute_escape(tmp_path):
    base = tmp_path / "output"
    base.mkdir()
    # pathlib's "/" returns the right operand when it is absolute, which
    # is the subtle case the boundary regex also has to stop.
    escaped = base / Path(tmp_path / "elsewhere.txt").as_posix()
    with pytest.raises(ValueError):
        validation.resolve_within(base, escaped)


# --- endpoint level ---------------------------------------------------

def test_traversal_player_id_rejected_and_writes_nothing(sandbox):
    client, tmp_path = sandbox
    response = client.post(
        "/frame",
        data={"player_id": "../../evil", "capture_id": "100"},
        files={"file": ("roi.jpg", b"\xff\xd8\xff\x00", "image/jpeg")},
        headers=AUTH,
    )
    assert response.status_code == 422
    assert not list(tmp_path.glob("**/*evil*"))


def test_oversized_upload_rejected(sandbox):
    client, _ = sandbox
    import app as app_module
    payload = b"\xff\xd8\xff" + b"\x00" * (app_module.MAX_UPLOAD_BYTES + 10)
    response = client.post(
        "/frame",
        data={"player_id": "deck1", "capture_id": "100"},
        files={"file": ("roi.jpg", payload, "image/jpeg")},
        headers=AUTH,
    )
    assert response.status_code == 413


def test_non_jpeg_upload_rejected(sandbox):
    client, _ = sandbox
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    response = client.post(
        "/frame",
        data={"player_id": "deck1", "capture_id": "100"},
        files={"file": ("roi.jpg", png, "image/jpeg")},
        headers=AUTH,
    )
    assert response.status_code == 415


def test_oversized_track_rejected(sandbox):
    client, _ = sandbox
    response = client.post(
        "/result",
        json={
            "player_id": "deck1",
            "capture_id": "100",
            "track": "x" * (validation.MAX_TRACK_LENGTH + 1),
            "confidence": 0.9,
        },
        headers=AUTH,
    )
    assert response.status_code == 422
