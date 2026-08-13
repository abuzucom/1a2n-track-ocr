import importlib
import inspect
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

TOKEN = "test-token-abcdefghijklmnop"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKEND_TOKEN", TOKEN)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "dataset"))
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)

    import auth, sinks, dataset, app as app_module
    for module in (auth, sinks, dataset, app_module):
        importlib.reload(module)

    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def post_result(client, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(
        "/result",
        json={"player_id": "deck1", "capture_id": "100", "track": "A", "confidence": 0.9},
        headers=headers,
    )


def test_missing_token_rejected(client):
    assert post_result(client).status_code == 401


def test_wrong_token_rejected(client):
    assert post_result(client, "totally-wrong").status_code == 401


def test_correct_prefix_wrong_suffix_rejected(client):
    # A prefix match must not pass. This is the case a length-only or
    # startswith comparison would let through.
    assert post_result(client, TOKEN[:-1] + "X").status_code == 401


def test_truncated_token_rejected(client):
    assert post_result(client, TOKEN[:10]).status_code == 401


def test_correct_token_accepted(client):
    assert post_result(client, TOKEN).status_code == 200


def test_frame_endpoint_also_requires_token(client):
    response = client.post(
        "/frame",
        data={"player_id": "deck1", "capture_id": "100"},
        files={"file": ("roi.jpg", b"\xff\xd8\xff\x00", "image/jpeg")},
    )
    assert response.status_code == 401


def test_app_refuses_to_start_without_token(monkeypatch):
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    import auth
    importlib.reload(auth)
    with pytest.raises(RuntimeError, match="BACKEND_TOKEN"):
        auth.expected_token()


def test_comparison_is_constant_time():
    """Guard against an == regression.

    Swapping compare_digest for == keeps every functional test above
    green while reintroducing a timing side channel that leaks the token
    byte by byte, so assert on the implementation itself.
    """
    import auth
    source = inspect.getsource(auth.require_token)
    assert "compare_digest" in source
    assert "presented == " not in source
