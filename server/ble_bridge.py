"""BLE central: receives on-device OCR results from rigs over Bluetooth LE.

The BLE transport exists so a rig can reach the server with no network
at all. It carries results only, never frames, so there is no Tesseract
read to arbitrate against and results are ingested with sole_source set;
see arbiter.py.

This runs inside the uvicorn process, started from app.py's lifespan
handler, rather than as its own service. That is deliberate: arbiter and
sinks keep their state in process-local globals, so a second process
would hold its own copies of both and the two would race writing
now_playing.json, losing the write ordering sinks.update maintains under
its lock.

BLE bypasses Caddy, so the limits Caddy applies to the HTTP path do not
apply here. MAX_MESSAGE_BYTES is this path's equivalent of the
Caddyfile's request_body cap.

bleak is imported lazily, inside the coroutines that need it, so the
framing and ingest logic below stay importable and testable on a host
that has no BLE stack installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import sys
from typing import Optional

from fastapi import HTTPException
from pydantic import ValidationError

import auth
import ingest

logger = logging.getLogger(__name__)

# Wire contract with deployed firmware. Changing any of these three, or
# the frame header below, breaks every already-flashed rig; see the
# public API surface note in AGENTS.md.
SERVICE_UUID = "5b9d1a70-3f4c-4a21-9c86-0e7b1d2f8a41"
RESULT_CHAR_UUID = "5b9d1a71-3f4c-4a21-9c86-0e7b1d2f8a41"
ACK_CHAR_UUID = "5b9d1a72-3f4c-4a21-9c86-0e7b1d2f8a41"

# Frame header: sequence number then total message length, both
# unsigned 16-bit little endian, followed by this packet's chunk.
FRAME_HEADER = struct.Struct("<HH")

# A result JSON is a few hundred bytes; a maximum-length track plus the
# other fields stays well under this. The cap bounds what a peer can
# make the bridge buffer before the message is parsed or authenticated.
MAX_MESSAGE_BYTES = 1024

ENV_ENABLED = "BLE_ENABLED"
ENV_MAX_DEVICES = "BLE_MAX_DEVICES"
DEFAULT_MAX_DEVICES = 4

SCAN_INTERVAL_SECONDS = 5.0
RECONNECT_BACKOFF_START_SECONDS = 1.0
RECONNECT_BACKOFF_MAX_SECONDS = 30.0


def enabled() -> bool:
    """True if the operator asked for the BLE bridge."""
    return os.environ.get(ENV_ENABLED, "").strip().lower() in ("1", "true", "yes", "on")


def max_devices() -> int:
    """Ceiling on simultaneous rig connections.

    Mirrors sinks.MAX_PLAYERS and arbiter.MAX_TRACKED_PLAYERS: without a
    cap, anything advertising the service UUID can grow the task set.
    """
    raw = os.environ.get(ENV_MAX_DEVICES, "").strip()
    if not raw:
        return DEFAULT_MAX_DEVICES
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer, using %d", ENV_MAX_DEVICES, raw, DEFAULT_MAX_DEVICES
        )
        return DEFAULT_MAX_DEVICES
    if value < 1:
        logger.warning(
            "%s=%d is below 1, using %d", ENV_MAX_DEVICES, value, DEFAULT_MAX_DEVICES
        )
        return DEFAULT_MAX_DEVICES
    return value


class ResultReassembler:
    """Rebuilds one framed message from a device's notification packets.

    One instance per connected device, never shared: sequence numbers
    are per device and interleaving two rigs into one buffer would
    splice their messages together.
    """

    def __init__(self) -> None:
        self._seq: Optional[int] = None
        self._total: int = 0
        self._buffer = bytearray()

    def reset(self) -> None:
        self._seq = None
        self._total = 0
        self._buffer.clear()

    def feed(self, packet: bytes) -> Optional[tuple[int, bytes]]:
        """Add one packet. Returns (seq, message) when one completes.

        Returns None while a message is still incomplete, and also when a
        packet is malformed: a bad peer should cost a dropped message,
        not a torn-down link.
        """
        if len(packet) < FRAME_HEADER.size:
            logger.warning("ble: dropping runt packet of %d bytes", len(packet))
            self.reset()
            return None

        seq, total = FRAME_HEADER.unpack_from(packet, 0)
        chunk = packet[FRAME_HEADER.size:]

        if total > MAX_MESSAGE_BYTES:
            logger.warning(
                "ble: dropping message of %d bytes, over the %d byte cap",
                total, MAX_MESSAGE_BYTES,
            )
            self.reset()
            return None

        if seq != self._seq:
            # A new sequence number abandons whatever was in flight. A
            # rig that reset mid-message must not leave a stuck buffer.
            self._seq = seq
            self._total = total
            self._buffer.clear()

        self._buffer.extend(chunk)
        if len(self._buffer) < self._total:
            return None

        if len(self._buffer) > self._total:
            logger.warning(
                "ble: dropping seq %d, %d bytes exceeds the declared %d",
                seq, len(self._buffer), self._total,
            )
            self.reset()
            return None

        message = bytes(self._buffer)
        self.reset()
        return seq, message


def parse_result_message(message: bytes) -> tuple[ingest.OndeviceResult, str]:
    """Parse a framed message into a result payload and its token.

    Parsing goes through ingest.OndeviceResult, so BLE payloads meet the
    same field constraints as an HTTP /result body. Raises ValueError on
    anything malformed; the token is returned separately so it never
    lands in a model that might be logged or echoed.
    """
    try:
        decoded = json.loads(message.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"message is not valid UTF-8 JSON: {error}") from error

    if not isinstance(decoded, dict):
        raise ValueError("message is not a JSON object")

    token = decoded.pop("token", None)
    if not isinstance(token, str) or not token:
        raise ValueError("message has no token")

    try:
        payload = ingest.OndeviceResult(**decoded)
    except (ValidationError, TypeError) as error:
        raise ValueError(f"message does not match the result schema: {error}") from error

    return payload, token


class DeviceRegistry:
    """Tracks which device handle currently owns each player_id.

    Two rigs flashed from the same unedited config.h present the same
    credential. Without this, both would write the same
    now_playing_<player_id>.txt and the overlay would flip between two
    decks' tracks with nothing in the log to explain it.
    """

    def __init__(self) -> None:
        self._owner_by_player: dict[str, str] = {}
        self._warned: set[str] = set()

    def claim(self, player_id: str, device_key: str) -> bool:
        """True if device_key may write player_id."""
        owner = self._owner_by_player.get(player_id)
        if owner is None:
            self._owner_by_player[player_id] = device_key
            return True
        if owner == device_key:
            return True
        if device_key not in self._warned:
            self._warned.add(device_key)
            logger.warning(
                "ble: refusing results for player_id %r from a second device; "
                "two rigs appear to share one credential",
                player_id,
            )
        return False

    def release(self, device_key: str) -> None:
        """Drop this device's claim, so a reconnect can take it again."""
        for player_id, owner in list(self._owner_by_player.items()):
            if owner == device_key:
                del self._owner_by_player[player_id]
        self._warned.discard(device_key)


def handle_message(
    message: bytes, device_key: str, registry: DeviceRegistry
) -> bool:
    """Authenticate and record one reassembled message.

    Returns True if it was recorded, so the caller knows whether to
    acknowledge. Never raises for bad input: a malformed or unauthorized
    message is logged and dropped, leaving the link up.
    """
    try:
        payload, token = parse_result_message(message)
    except ValueError as error:
        logger.warning("ble: dropping message from %s: %s", device_key, error)
        return False

    try:
        authorized = auth.authorized_player(f"Bearer {token}")
    except HTTPException:
        # Deliberately says nothing about the token itself.
        logger.warning("ble: rejecting message from %s: unrecognized credential", device_key)
        return False

    if not registry.claim(authorized, device_key):
        return False

    try:
        ingest.record_ondevice_result(payload, authorized, sole_source=True)
    except HTTPException as error:
        logger.warning(
            "ble: rejecting message from %s: %s", device_key, error.detail
        )
        return False
    return True


def _preflight_macos_permission() -> bool:
    """True if BLE may proceed on this host.

    macOS gates Bluetooth behind a TCC permission granted to the
    responsible application, which for a script is the terminal, not the
    interpreter. Where there is no responsible GUI app (ssh, launchd)
    the request is denied with no prompt and scanning silently returns
    nothing, so check the state rather than let it look like no rigs are
    in range.
    """
    if sys.platform != "darwin":
        return True

    try:
        from CoreBluetooth import (  # noqa: PLC0415
            CBCentralManager,
            CBManagerAuthorizationDenied,
            CBManagerAuthorizationRestricted,
        )
    except ImportError:
        # pyobjc ships with bleak on macOS. If it is missing, let the
        # scan itself produce the real error rather than guessing here.
        logger.info("ble: CoreBluetooth bindings unavailable, skipping permission check")
        return True

    authorization = CBCentralManager.authorization()
    if authorization in (CBManagerAuthorizationDenied, CBManagerAuthorizationRestricted):
        logger.error(
            "ble: Bluetooth permission is denied for this application. Grant it in "
            "System Settings, Privacy and Security, Bluetooth, then restart the "
            "server. To open that pane: open "
            '"x-apple.systempreferences:com.apple.preference.security?Privacy_Bluetooth"'
        )
        return False
    return True


async def _pump_device(client, device_key: str, registry: DeviceRegistry) -> None:
    """Subscribe to one device's results until it disconnects."""
    reassembler = ResultReassembler()
    queue: asyncio.Queue = asyncio.Queue()

    def on_notify(_characteristic, data: bytearray) -> None:
        queue.put_nowait(bytes(data))

    await client.start_notify(RESULT_CHAR_UUID, on_notify)
    logger.info("ble: subscribed to %s", device_key)
    try:
        while client.is_connected:
            packet = await queue.get()
            completed = reassembler.feed(packet)
            if completed is None:
                continue
            seq, message = completed
            # Ingest is synchronous: it writes two small files under a
            # lock and returns. Captures arrive every 20 seconds, so
            # holding the loop for that is cheaper than a thread hop.
            if handle_message(message, device_key, registry):
                await client.write_gatt_char(ACK_CHAR_UUID, FRAME_HEADER.pack(seq, 0))
    finally:
        await _stop_notify_quietly(client, device_key)


async def _stop_notify_quietly(client, device_key: str) -> None:
    """Unsubscribe, tolerating a link that is already gone."""
    try:
        await client.stop_notify(RESULT_CHAR_UUID)
    except Exception as error:  # noqa: BLE001
        # The usual case is the device having already dropped, where
        # there is nothing left to unsubscribe from and nothing to fix.
        logger.debug("ble: stop_notify on %s failed: %s", device_key, error)


async def _run_device(device, registry: DeviceRegistry) -> None:
    """Keep one rig connected, reconnecting with bounded backoff."""
    from bleak import BleakClient  # noqa: PLC0415

    device_key = str(device.address)
    backoff = RECONNECT_BACKOFF_START_SECONDS
    while True:
        try:
            # pair=True because both characteristics require encryption.
            # It is a no-op on macOS, which pairs automatically on first
            # access to such a characteristic, and does the work on
            # Windows and Linux.
            async with BleakClient(device, pair=True) as client:
                logger.info("ble: connected to %s", device_key)
                backoff = RECONNECT_BACKOFF_START_SECONDS
                await _pump_device(client, device_key, registry)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            # bleak raises stack-specific errors that differ per OS, and
            # every one of them means the same thing here: retry later.
            logger.warning("ble: %s disconnected: %s", device_key, error)
        finally:
            registry.release(device_key)

        logger.info("ble: retrying %s in %.0fs", device_key, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX_SECONDS)


async def run_bridge() -> None:
    """Scan for rigs and service each one until cancelled."""
    if not _preflight_macos_permission():
        return

    from bleak import BleakScanner  # noqa: PLC0415

    registry = DeviceRegistry()
    limit = max_devices()
    connected: dict[str, asyncio.Task] = {}

    logger.info("ble: bridge starting, up to %d devices", limit)
    async with asyncio.TaskGroup() as group:
        while True:
            found = await BleakScanner.discover(
                timeout=SCAN_INTERVAL_SECONDS, service_uuids=[SERVICE_UUID]
            )
            for device in found:
                key = str(device.address)
                if key in connected and not connected[key].done():
                    continue
                if len(connected) >= limit and key not in connected:
                    logger.warning(
                        "ble: ignoring %s, already at the %s limit of %d",
                        key, ENV_MAX_DEVICES, limit,
                    )
                    continue
                logger.info("ble: discovered %s", key)
                connected[key] = group.create_task(_run_device(device, registry))
