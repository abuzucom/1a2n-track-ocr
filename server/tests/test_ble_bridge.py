"""Framing, parsing, and ingest tests for the BLE transport.

No bleak, and no BLE hardware: ble_bridge imports bleak lazily inside
the coroutines that talk to a radio, so everything below runs on a host
with no Bluetooth stack at all.
"""

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

DECK1_TOKEN = "deck1-token-abcdefghijklmnop"
DECK2_TOKEN = "deck2-token-qrstuvwxyz012345"
TOKENS = f"deck1:{DECK1_TOKEN},deck2:{DECK2_TOKEN}"


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    """Reload the modules under test with a scratch output directory."""
    monkeypatch.setenv("BACKEND_TOKENS", TOKENS)
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "dataset"))
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)

    import arbiter
    import auth
    import dataset
    import ingest
    import sinks
    import ble_bridge

    for module in (auth, sinks, dataset, arbiter, ingest, ble_bridge):
        importlib.reload(module)

    arbiter._pending_tesseract.clear()
    arbiter._pending_order.clear()
    arbiter._agreement_history.clear()
    sinks._state.clear()
    return ble_bridge


def frame(message: bytes, seq: int = 1, chunk_size: int = 244, total=None):
    """Split a message into packets the way the firmware does."""
    declared = len(message) if total is None else total
    packets = []
    for start in range(0, max(len(message), 1), chunk_size):
        chunk = message[start:start + chunk_size]
        packets.append(ble_header(seq, declared) + chunk)
    return packets


def ble_header(seq: int, total: int) -> bytes:
    import struct
    return struct.pack("<HH", seq, total)


def result_message(track="Artist - Title", token=DECK1_TOKEN, player_id="deck1",
                   capture_id="100", confidence=0.9):
    body = {
        "player_id": player_id,
        "capture_id": capture_id,
        "track": track,
        "confidence": confidence,
        "token": token,
    }
    return json.dumps(body).encode("utf-8")


def feed_all(reassembler, packets):
    """Feed every packet, returning the last non-None completion."""
    completed = None
    for packet in packets:
        result = reassembler.feed(packet)
        if result is not None:
            completed = result
    return completed


def test_single_packet_message_reassembles(bridge):
    message = result_message()
    reassembler = bridge.ResultReassembler()
    completed = feed_all(reassembler, frame(message))
    assert completed == (1, message)


def test_message_reassembles_across_chunk_boundaries(bridge):
    message = result_message(track="A" * 400)
    packets = frame(message, chunk_size=64)
    assert len(packets) > 1

    reassembler = bridge.ResultReassembler()
    for packet in packets[:-1]:
        assert reassembler.feed(packet) is None
    seq, rebuilt = reassembler.feed(packets[-1])
    assert (seq, rebuilt) == (1, message)


def test_new_sequence_abandons_a_partial_message(bridge):
    """A rig that resets mid-message must not wedge the buffer."""
    reassembler = bridge.ResultReassembler()
    abandoned = frame(result_message(track="A" * 400), seq=1, chunk_size=64)
    assert reassembler.feed(abandoned[0]) is None

    message = result_message(track="Second")
    completed = feed_all(reassembler, frame(message, seq=2))
    assert completed == (2, message)


def test_oversized_message_is_dropped_not_buffered(bridge):
    """The cap is this path's replacement for Caddy's request_body limit."""
    reassembler = bridge.ResultReassembler()
    header = ble_header(1, bridge.MAX_MESSAGE_BYTES + 1)
    assert reassembler.feed(header + b"x" * 100) is None
    assert len(reassembler._buffer) == 0


def test_message_longer_than_declared_is_dropped(bridge):
    reassembler = bridge.ResultReassembler()
    message = result_message()
    packets = frame(message, total=len(message) - 5)
    assert feed_all(reassembler, packets) is None


def test_runt_packet_is_dropped(bridge):
    reassembler = bridge.ResultReassembler()
    assert reassembler.feed(b"\x01") is None


def test_malformed_json_is_rejected(bridge):
    with pytest.raises(ValueError):
        bridge.parse_result_message(b"{not json")


def test_message_without_a_token_is_rejected(bridge):
    body = json.loads(result_message())
    del body["token"]
    with pytest.raises(ValueError):
        bridge.parse_result_message(json.dumps(body).encode("utf-8"))


def test_overlong_track_is_rejected_by_the_shared_model(bridge):
    import validation
    message = result_message(track="A" * (validation.MAX_TRACK_LENGTH + 1))
    with pytest.raises(ValueError):
        bridge.parse_result_message(message)


def test_token_is_not_carried_on_the_parsed_payload(bridge):
    payload, token = bridge.parse_result_message(result_message())
    assert token == DECK1_TOKEN
    assert not hasattr(payload, "token")


def test_accepted_message_publishes_without_a_tesseract_result(bridge, tmp_path):
    """The whole point of sole_source: BLE never sends a frame."""
    registry = bridge.DeviceRegistry()
    assert bridge.handle_message(result_message(), "AA:BB:CC", registry) is True

    published = tmp_path / "output" / "now_playing_deck1.txt"
    assert published.read_text(encoding="utf-8") == "Artist - Title"

    import sinks
    assert sinks._state["deck1"]["source"] == "ondevice"


def test_unknown_token_is_rejected(bridge):
    registry = bridge.DeviceRegistry()
    message = result_message(token="not-a-configured-token-at-all")
    assert bridge.handle_message(message, "AA:BB:CC", registry) is False


def test_token_may_not_claim_another_players_id(bridge):
    """The credential-to-player binding holds on BLE too."""
    registry = bridge.DeviceRegistry()
    message = result_message(player_id="deck2", token=DECK1_TOKEN)
    assert bridge.handle_message(message, "AA:BB:CC", registry) is False


def test_two_devices_publish_independently(bridge, tmp_path):
    registry = bridge.DeviceRegistry()
    assert bridge.handle_message(
        result_message(player_id="deck1", token=DECK1_TOKEN, track="One"),
        "AA:BB:CC", registry,
    ) is True
    assert bridge.handle_message(
        result_message(player_id="deck2", token=DECK2_TOKEN, track="Two"),
        "DD:EE:FF", registry,
    ) is True

    payload = json.loads(
        (tmp_path / "output" / "now_playing.json").read_text(encoding="utf-8")
    )
    assert payload["players"]["deck1"]["track"] == "One"
    assert payload["players"]["deck2"]["track"] == "Two"


def test_second_device_claiming_a_live_player_id_is_rejected(bridge):
    """Two rigs flashed from the same unedited config.h."""
    registry = bridge.DeviceRegistry()
    assert bridge.handle_message(result_message(track="One"), "AA:BB:CC", registry) is True
    assert bridge.handle_message(result_message(track="Two"), "DD:EE:FF", registry) is False

    import sinks
    assert sinks._state["deck1"]["track"] == "One"


def test_released_player_id_can_be_reclaimed_after_a_disconnect(bridge):
    registry = bridge.DeviceRegistry()
    assert bridge.handle_message(result_message(), "AA:BB:CC", registry) is True
    registry.release("AA:BB:CC")
    assert bridge.handle_message(result_message(track="Later"), "DD:EE:FF", registry) is True


def test_max_devices_defaults_and_rejects_nonsense(bridge, monkeypatch):
    monkeypatch.delenv(bridge.ENV_MAX_DEVICES, raising=False)
    assert bridge.max_devices() == bridge.DEFAULT_MAX_DEVICES

    monkeypatch.setenv(bridge.ENV_MAX_DEVICES, "2")
    assert bridge.max_devices() == 2

    monkeypatch.setenv(bridge.ENV_MAX_DEVICES, "not-a-number")
    assert bridge.max_devices() == bridge.DEFAULT_MAX_DEVICES

    monkeypatch.setenv(bridge.ENV_MAX_DEVICES, "0")
    assert bridge.max_devices() == bridge.DEFAULT_MAX_DEVICES


def test_bridge_is_off_unless_explicitly_enabled(bridge, monkeypatch):
    monkeypatch.delenv(bridge.ENV_ENABLED, raising=False)
    assert bridge.enabled() is False

    monkeypatch.setenv(bridge.ENV_ENABLED, "1")
    assert bridge.enabled() is True

    monkeypatch.setenv(bridge.ENV_ENABLED, "0")
    assert bridge.enabled() is False


def test_permission_preflight_is_skipped_off_darwin(bridge, monkeypatch):
    monkeypatch.setattr(bridge.sys, "platform", "linux")
    assert bridge._preflight_macos_permission() is True


def test_permission_preflight_blocks_when_denied(bridge, monkeypatch):
    """A denied permission scans empty and silent, so name it instead."""
    fake = _fake_corebluetooth(authorization=2)
    monkeypatch.setattr(bridge.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "CoreBluetooth", fake)
    assert bridge._preflight_macos_permission() is False


def test_permission_preflight_proceeds_when_allowed(bridge, monkeypatch):
    monkeypatch.setattr(bridge.sys, "platform", "darwin")
    for state in (0, 3):
        monkeypatch.setitem(sys.modules, "CoreBluetooth", _fake_corebluetooth(state))
        assert bridge._preflight_macos_permission() is True


def _fake_corebluetooth(authorization: int):
    """Stand in for pyobjc's CoreBluetooth on a non-macOS test host."""
    import types

    module = types.ModuleType("CoreBluetooth")
    module.CBManagerAuthorizationDenied = 2
    module.CBManagerAuthorizationRestricted = 1

    class FakeCentralManager:
        @staticmethod
        def authorization():
            return authorization

    module.CBCentralManager = FakeCentralManager
    return module
