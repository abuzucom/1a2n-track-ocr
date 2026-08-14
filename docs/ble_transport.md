# BLE transport

A rig can reach the backend over Bluetooth LE instead of WiFi. This is the
default build, because it needs no network at all: no guest WiFi, no captive
portal, no congested venue spectrum. The server runs on a laptop in the booth,
on Windows or macOS.

## What BLE does and does not carry

BLE carries on-device OCR results only. A ROI JPEG runs tens of KB and BLE
moves tens of KB per second, so frame upload stays a WiFi feature.

Two things follow, and both matter more than they look:

1. **A BLE rig needs a real model in `ocr_model.h`.** On-device OCR is the
   only thing producing a track, since nothing uploads a frame for Tesseract
   to read. A BLE build with the placeholder model halts at boot rather than
   running silently forever.
2. **A BLE rig collects no training data.** Only `/frame` produces labeled
   samples, and only Tesseract labels them. The model a BLE rig runs has to
   come from somewhere else.

So the two transports are phases, not just alternatives:

```
WiFi build  ->  collect and auto-label a dataset  ->  train, convert, export
            ->  flash ocr_model.h  ->  BLE build  ->  operate in the booth
```

Run the WiFi path on a trusted network first. See the training steps in
`README.md` and `ml/README.md`.

## Firmware setup

In `config.h`, define exactly one transport:

```c
#define TRANSPORT_BLE
// #define TRANSPORT_WIFI
```

Set `BLE_PASSKEY` to a random six digit number. It is the passkey the host
enters when pairing. `config.h` is gitignored, so it stays on your machine.

`PLAYER_ID` and `BACKEND_TOKEN` work exactly as they do on WiFi: the token
travels in the message body rather than an HTTP header, and the backend still
checks that the credential owns the `player_id` being claimed.

`BACKEND_URL` and `BACKEND_CA_CERT` are unused on a BLE build. There is no
Caddy in the path.

### Device names

Each rig advertises as `OCR-<last 6 hex digits of its BLE MAC>`, for example
`OCR-A4F2C9`. The suffix comes from the board, so two rigs are always distinct
rows in the host's Bluetooth menu even if they were flashed from the same
unedited `config.h`.

The name does not say which deck a rig is. Note the suffix when you flash it,
or label the enclosure, otherwise pairing a two-deck setup is guesswork.

Renaming a rig after pairing can leave the old name in the host's menu until
the bond is removed, since both Windows and macOS cache it.

## Server setup

Install the extra dependency and start the server with the bridge on:

```
cd server
pip install -r requirements-ble.lock
BACKEND_TOKENS=deck1:<token1>,deck2:<token2> BLE_ENABLED=1 \
  uvicorn app:app --host 127.0.0.1 --port 8000
```

The bridge runs inside the uvicorn process; there is no second service to
start. `BLE_MAX_DEVICES` caps concurrent rigs and defaults to 4.

Caddy is still worth running if OBS reads the overlay files over HTTP. It is
no longer in the rig's path.

`requirements-ble.lock` is compiled per OS, because bleak's dependencies
differ by platform. Regenerate it on yours; see the dependency pinning section
in `README.md`.

## Pairing

Both characteristics require an encrypted link, so the host pairs on first
access. Enter the `BLE_PASSKEY` when prompted. The bond persists, so later
reconnects are silent on both sides.

### macOS

Grant Bluetooth permission to the **terminal application** you launch the
server from, in System Settings, Privacy and Security, Bluetooth. The server
checks this at startup and says so if it is denied, because the failure mode
is otherwise invisible: scanning simply returns nothing, exactly as if no rig
were in range.

Running over ssh or from launchd is the case to watch. There is no responsible
GUI application for macOS to attribute the request to, so no prompt appears
and the permission stays denied. Start the server from a terminal you have
opened on the machine itself.

To open the pane directly:

```
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Bluetooth"
```

### Windows

Requires the WinRT Bluetooth stack, so Windows 10 version 1709 or later. The
bridge asks the stack to pair on connect; if that does not take, pair once
through Settings, Bluetooth and devices, entering the passkey there.

## Security

On WiFi, Caddy provides TLS with a CA the firmware pins. BLE has no equivalent
layer, so this path stands on two things instead:

- **The link.** LE Secure Connections pairing with a passkey, bonded, with
  both characteristics marked as requiring encryption. That gives
  confidentiality and integrity for everything crossing the air.
- **The token.** The same per-rig bearer token as the HTTP path, carried in
  the message body and checked against the claimed `player_id`. Link
  encryption authenticates the link; the token is what still binds a rig to
  one deck's output.

Known limits, stated rather than implied:

- The token crosses an encrypted link, but not a TLS one, and there is no
  per-message HMAC or nonce. Replay protection rests on the BLE link layer
  plus the fact that `sinks.update` ignores a repeat of the current track.
- The advertised name is not authenticated. Nothing is decided by it: the
  bridge filters on the service UUID and authorizes on the token.

## Behavior worth knowing

**Results survive a dropout.** Track changes are edge-triggered, so a result
lost while the laptop is out of range would leave the overlay on the previous
track until the next change, possibly for minutes. Instead a disconnected rig
keeps capturing and queues up to 8 undelivered results, flushing them oldest
first when the host returns. On overflow the oldest is dropped: the newest
track is the one actually on screen.

**Two rigs, one credential.** If two rigs present the same token, the second
one's results are rejected and logged once. Without that they would take turns
overwriting the same `now_playing_<player_id>.txt`. Give each rig its own
`player_id:token` pair.

**Messages are capped at 1024 bytes** on both ends, which replaces the 4MB
ingress cap Caddy applies to the HTTP path.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Rig halts at boot with a model message | BLE build with a placeholder `ocr_model.h`. Train and export a model first. |
| Server finds no devices on macOS | Bluetooth permission denied. See the macOS section above. |
| Rig visible but never publishes | Check the token matches this rig's `player_id` in `BACKEND_TOKENS`. |
| Two rigs, only one publishes | Both are flashed with the same credential. The log names the duplicate `player_id`. |
| Overlay stuck on an old track | The rig may be out of range and queueing. Results flush on reconnect. |
