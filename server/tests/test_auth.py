import importlib
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

DECK1_TOKEN = "deck1-token-abcdefghijklmnop"
DECK2_TOKEN = "deck2-token-qrstuvwxyz012345"
TOKENS = f"deck1:{DECK1_TOKEN},deck2:{DECK2_TOKEN}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKEND_TOKENS", TOKENS)
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "dataset"))
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)

    import auth, sinks, dataset, app as app_module
    for module in (auth, sinks, dataset, app_module):
        importlib.reload(module)

    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def post_result(client, token=None, player_id="deck1"):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(
        "/result",
        json={
            "player_id": player_id,
            "capture_id": "100",
            "track": "Artist - Title",
            "confidence": 0.9,
        },
        headers=headers,
    )


# --- credential presence -------------------------------------------

def test_missing_token_rejected(client):
    assert post_result(client).status_code == 401


def test_unknown_token_rejected(client):
    assert post_result(client, "not-a-configured-token").status_code == 401


def test_correct_prefix_wrong_suffix_rejected(client):
    assert post_result(client, DECK1_TOKEN[:-1] + "X").status_code == 401


def test_truncated_token_rejected(client):
    assert post_result(client, DECK1_TOKEN[:10]).status_code == 401


def test_correct_token_accepted(client):
    assert post_result(client, DECK1_TOKEN, player_id="deck1").status_code == 200


# --- per-device binding, audit finding 2 -----------------------------
#
# One shared token authorized every player, so compromising a single rig
# let it overwrite another player's output, poison that player's training
# data, and consume its slot. Each credential is now bound to one
# player_id.

def test_rig_cannot_post_as_another_player(client):
    response = post_result(client, DECK1_TOKEN, player_id="deck2")
    assert response.status_code == 403


def test_each_rig_can_post_as_itself(client):
    assert post_result(client, DECK1_TOKEN, player_id="deck1").status_code == 200
    assert post_result(client, DECK2_TOKEN, player_id="deck2").status_code == 200


def test_frame_endpoint_enforces_the_same_binding(client):
    response = client.post(
        "/frame",
        data={"player_id": "deck2", "capture_id": "100"},
        files={"file": ("roi.jpg", b"\xff\xd8\xff\x00", "image/jpeg")},
        headers={"Authorization": f"Bearer {DECK1_TOKEN}"},
    )
    assert response.status_code == 403


def test_frame_endpoint_requires_a_token(client):
    response = client.post(
        "/frame",
        data={"player_id": "deck1", "capture_id": "100"},
        files={"file": ("roi.jpg", b"\xff\xd8\xff\x00", "image/jpeg")},
    )
    assert response.status_code == 401


# --- configuration ---------------------------------------------------

def test_refuses_to_start_with_no_credentials(monkeypatch):
    monkeypatch.delenv("BACKEND_TOKENS", raising=False)
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    import auth
    importlib.reload(auth)
    with pytest.raises(RuntimeError, match="BACKEND_TOKENS"):
        auth.credentials()


def test_legacy_single_token_refuses_with_migration_hint(monkeypatch):
    """A shared token is the finding, so it must not silently keep working.

    Failing loudly with the replacement spelled out beats accepting the
    old variable and leaving every rig able to impersonate every other.
    """
    monkeypatch.delenv("BACKEND_TOKENS", raising=False)
    monkeypatch.setenv("BACKEND_TOKEN", "legacy-single-token")
    import auth
    importlib.reload(auth)
    with pytest.raises(RuntimeError, match="BACKEND_TOKENS"):
        auth.credentials()


@pytest.mark.parametrize("value", ["deck1", "deck1:", ":token", "deck1:tok,bad", "=x:y"])
def test_malformed_configuration_rejected(monkeypatch, value):
    monkeypatch.setenv("BACKEND_TOKENS", value)
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    import auth
    importlib.reload(auth)
    with pytest.raises(RuntimeError):
        auth.credentials()


def test_duplicate_player_rejected(monkeypatch):
    monkeypatch.setenv("BACKEND_TOKENS", "deck1:aaaaaaaaaaaaaaaaaa,deck1:bbbbbbbbbbbbbbbbbb")
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    import auth
    importlib.reload(auth)
    with pytest.raises(RuntimeError, match="duplicate"):
        auth.credentials()


def test_tokens_may_contain_colons(monkeypatch):
    """Split on the first colon only, since player_id cannot contain one."""
    monkeypatch.setenv("BACKEND_TOKENS", "deck1:tok:with:colons:and:more")
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    import auth
    importlib.reload(auth)
    assert auth.credentials()["deck1"] == "tok:with:colons:and:more"


# --- regression guards ------------------------------------------------

def test_comparison_is_constant_time():
    """Swapping compare_digest for == keeps every test above green while
    reintroducing a timing side channel that leaks the token."""
    import auth
    source = inspect.getsource(auth.authorized_player)
    assert "compare_digest" in source
    assert "==" not in source


def test_lookup_does_not_short_circuit_on_match(monkeypatch):
    """Returning on the first match leaks a credential's position.

    An implementation that stops early performs fewer comparisons for a
    token configured first than for one configured last, which is
    measurable. Counts calls rather than reading the source, so a
    refactor cannot quietly satisfy it.
    """
    import auth
    monkeypatch.setenv("BACKEND_TOKENS", TOKENS)
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    importlib.reload(auth)

    calls = []
    real_compare = auth.hmac.compare_digest

    def counting_compare(left, right):
        calls.append(1)
        return real_compare(left, right)

    monkeypatch.setattr(auth.hmac, "compare_digest", counting_compare)
    # deck1 is configured first; a short-circuiting lookup would stop
    # after one comparison instead of two.
    assert auth.authorized_player(f"Bearer {DECK1_TOKEN}") == "deck1"
    assert len(calls) == 2, "lookup stopped early, leaking position by timing"
