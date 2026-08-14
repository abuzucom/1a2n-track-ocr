# Quickstart

A step by step guide to flashing the W11 rig, confirming it works, and
collecting training data. Written for someone who has never used a terminal
or flashed hardware before. Every step says what to type and what you should
see before moving to the next one.

This is the beginner path. `README.md` is the full technical reference; come
back to it once this guide gets you a working rig.

Nothing here has been tested against real hardware yet. Getting this guide
right the first time you follow it is part of that test. If a step does not
match what you see on your screen, stop and see "If you get stuck" at the
end rather than guessing.

## 1. What you need

- The W11 ESP32-S3 board with its camera attached.
- A USB **data** cable, not a charge-only cable. The two look identical.
  A charge-only cable lets the board power on but never lets your computer
  talk to it, which looks like a broken board when it is really just the
  wrong cable. If step 8 below cannot find the board, try a different cable
  before anything else.
- A computer you personally have full install rights on. Installing
  software and reaching a USB serial port both need normal admin
  permissions; a locked-down work or school laptop will likely block one of
  the steps below with no clear reason why.
- A Pioneer XDJ-1000 or XDJ-1000MK2 to point the camera at.
- Something to hold the camera fixed in place over the unit's screen: a
  small tripod, an articulating arm, or another mount that will not shift.
  This is not optional. The system is calibrated to one fixed crop of the
  image, and a camera that drifts after calibration will silently produce
  bad captures with no error telling you why.
- Your WiFi network's name and password (a 2.4GHz network; see step 7).

By the end of this guide you will have a rig that watches the XDJ's screen
and records what it sees, ready to send off so a trained model can be built
from it.

## 2. Install the tools on your computer

Four tools, once, before anything else.

**Git**, to download the project:
- Windows and macOS: [git-scm.com/downloads](https://git-scm.com/downloads),
  run the installer.
- Linux (Debian or Ubuntu): `sudo apt install git`

**Python** (3.10 or newer), needed by the flashing tool and the backend
server:
- Windows and macOS: [python.org/downloads](https://python.org/downloads),
  run the installer. On Windows, check the box that says "Add python.exe to
  PATH" during install, or later commands will not find it.
- Linux (Debian or Ubuntu): `sudo apt install python3 python3-pip`

**PlatformIO**, which builds and flashes the firmware:
```
pip install platformio
```

**Tesseract**, the OCR engine the backend uses to read captures:
- Linux (Debian or Ubuntu): `sudo apt install tesseract-ocr`
- macOS: `brew install tesseract` (needs Homebrew, from
  [brew.sh](https://brew.sh), installed first)
- Windows: download and run the installer from Tesseract's official
  Windows build maintainer, UB Mannheim, linked from the project's own
  install notes. Install to the default location.

**Caddy**, the local HTTPS server the rig talks to:
- Linux (Debian or Ubuntu):
  ```
  sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
  sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
  sudo apt update
  sudo apt install caddy
  ```
- macOS: `brew install caddy`
- Windows: if you have Chocolatey, `choco install caddy`. If you have
  Scoop, `scoop install caddy` instead. If you have neither, download the
  static binary from caddyserver.com's Download page and place it
  somewhere on your PATH; installing a whole package manager just for this
  one tool is not worth it.

## 3. Get the code

Open a terminal (Command Prompt or PowerShell on Windows, Terminal on
macOS, your terminal of choice on Linux) and run:

```
git clone https://github.com/abuzucom/1a2n-track-ocr.git
cd 1a2n-track-ocr
```

Everything from here assumes you are inside this `1a2n-track-ocr` folder.

## 4. Mount the camera

Secure the camera to the tripod or arm from step 1 first, so it cannot
shift once you aim it. Do not prop it against something loose; if it moves
later, you will need to redo this step and step 10's check below, not just
one of them.

Aim it at the XDJ's screen, at the "Track names" field: the top info bar,
to the right of a small music-note icon, to the left of the row of touch
keys. Use that music-note icon as a landmark when you position the camera,
and the "Key" field immediately to its right (a small text field like
"Em") as a second landmark to confirm you are framing the right area.

Two things that will otherwise cause confusing failures later:

- The unit must stay on the **Normal playback screen**. If it switches to
  the Performance screen, the track name field disappears entirely and the
  camera has nothing to read until it switches back.
- Aim the camera as close to straight-on as you can, rather than at a sharp
  angle, and avoid a spot where booth or stage lighting reflects directly
  off the screen. Either one makes the text harder to read regardless of
  the camera. The camera's lens is fixed focus; there is no ring to adjust,
  so if the image looks bad the cause is distance, angle, or lighting, not
  focus.

## 5. Start Caddy, and allow it through your firewall

From the `1a2n-track-ocr` folder:

```
caddy run
```

The first time you run this, your operating system will likely ask whether
to allow Caddy to accept connections from your network. **Allow it.** This
is the single most common reason a rig never reaches the server while
everything else looks correctly set up. On Windows, a firewall window
appears with checkboxes for network type; check the one for your home or
private network and click the button that allows access. On macOS, this
only appears if the built-in firewall is turned on at all; if you see a
prompt about incoming connections, allow it. Exact wording varies by
operating system version; look for a button that means allow, not block.

Leave this window running and open a second terminal window for the next
step. In that second terminal, from the same folder, run:

```
caddy trust
```

Caddy just generated a security certificate on your computer. Find its
file, since you need its contents in the next step:
- Linux: `~/.local/share/caddy/pki/authorities/local/root.crt`
- macOS: `~/Library/Application Support/Caddy/pki/authorities/local/root.crt`
- Windows: `%AppData%\Caddy\pki\authorities\local\root.crt`

## 6. Find your computer's network address

You will need this in the next step. Find the address of the computer
running Caddy, on your local network:

- Windows: open Command Prompt and run `ipconfig`. Look for "IPv4 Address"
  under the WiFi or Ethernet section that is currently connected.
- macOS: System Settings, WiFi, click the details button next to your
  connected network, read "IP Address."
- Linux: run `hostname -I` and read the address shown.

Write this down; it looks like `192.168.1.50`. It can change later if your
router reassigns it, which is worth remembering if things stop working
after a few days; see the troubleshooting table.

**Your WiFi network must be 2.4GHz.** The board's WiFi radio does not
support 5GHz at all. Many home routers today broadcast two networks, one
often named with "5G" in it; if yours does, use the other one. Connecting
to a 5GHz-only network produces a "WiFi connect timed out" failure with
nothing telling you the band was the problem. Also, a hotel, cafe, or venue
guest network with a browser login page will not work: the rig cannot click
through a login screen. Use a network you control.

## 7. Configure the firmware

Copy the template. Type this command rather than copying the file in
Finder or Explorer and renaming it; both hide file extensions by default,
and a renamed copy can silently end up named `config.h.txt` instead of
`config.h`.

```
cd firmware
cp src/config.h.example src/config.h
```

Open `firmware/src/config.h` in a plain text editor. On Windows, Notepad is
fine. On macOS, if you use TextEdit, switch it to plain text first (Format
menu, "Make Plain Text"); TextEdit's default rich text mode can silently
insert characters that break the build, with an error far removed from the
actual cause.

Edit these values, in this order:

1. Near the top, comment out `TRANSPORT_BLE` and uncomment
   `TRANSPORT_WIFI`, so it reads:
   ```
   // #define TRANSPORT_BLE
   #define TRANSPORT_WIFI
   ```
2. `WIFI_SSID` and `WIFI_PASSWORD`: your network's name and password.
3. `BACKEND_URL`: `"https://"` followed by the address you found in step
   6, for example `"https://192.168.1.50"`.
4. `BACKEND_CA_CERT`: open the certificate file from step 5 in a text
   editor, copy its entire contents (including the `BEGIN CERTIFICATE` and
   `END CERTIFICATE` lines), and paste it in place of the placeholder
   text, keeping the surrounding quotes and parentheses exactly as they
   are.
5. `BACKEND_TOKEN`: make up a long, random value, for example a string of
   20 or more random letters and numbers. Write it down somewhere durable,
   the same place you would keep a WiFi password, not a sticky note that
   gets thrown out. You will need this exact value again in step 9. Never
   post this value anywhere public, including in a screenshot when asking
   for help; it is a credential, not a label.
6. `PLAYER_ID`: a short name with only letters, numbers, underscores, and
   hyphens, for example `player1`. No spaces, no apostrophes, nothing else;
   the server rejects anything else with a confusing error. Write this
   value on a piece of tape on the physical board now, before there is
   ever a second rig to mix it up with.

Leave the four `ROI_` values alone for now. You will come back to them in
step 10 only if the crop turns out to be wrong.

## 8. Build and flash

Plug the board into your computer with the data cable from step 1. From
the `firmware` folder:

```
pio run
```

The first time you run this, it downloads the compiler and supporting
tools, which can take 10 to 20 minutes on a home connection with no visible
progress. This is normal; do not close the window.

When that finishes without errors, flash the board:

```
pio run -t upload
```

If this cannot find the board, list the available ports:

```
pio device list
```

and look for one that appeared when you plugged the board in. If nothing
appears at all, double check you are using a data cable, not a
charge-only one.

Confirm the flash worked:

```
pio device monitor
```

You should see text scroll by, ending with the line `camera ready`. Leave
this running for now; press `Ctrl+C` (or `Ctrl+]` if that does not work)
when you want to stop watching it later.

Do not unplug the cable while `pio run -t upload` is running. Interrupting
a flash partway through can leave the board unable to start.

## 9. Start the backend

Open a new terminal window. From the `1a2n-track-ocr` folder:

```
cd server
pip install -r requirements.lock
```

Then, using the exact `BACKEND_TOKEN` and `PLAYER_ID` you chose in step 7:

Linux or macOS:
```
export BACKEND_TOKENS=player1:<your-token>
uvicorn app:app --host 127.0.0.1 --port 8000
```

Windows (PowerShell):
```
$env:BACKEND_TOKENS = "player1:<your-token>"
uvicorn app:app --host 127.0.0.1 --port 8000
```

Replace `player1` with your `PLAYER_ID` and `<your-token>` with your
`BACKEND_TOKEN`, keeping the colon between them. Leave this window running.
Both this and the `caddy run` window from step 5 need to stay open at the
same time.

## 10. Test it

With Caddy, the backend, and the flashed rig all running, and the camera
aimed at the XDJ's Normal playback screen, change the track on the unit.

Wait. The rig only samples the screen every 20 seconds by default, so
check back after at least that long, not immediately.

Look in the `server/output/` folder for a file named
`now_playing_player1.txt` (using your own `PLAYER_ID`). It should contain
the track name you just switched to.

If it does not update: change to a genuinely different track, not the same
one paused and resumed. The rig only acts when the cropped image actually
changes, so replaying the same track produces nothing, which looks
identical to a broken system but is not one.

If the file exists but the text is garbled or empty, the ROI crop is
likely misaligned. Adjust `ROI_X`, `ROI_Y`, `ROI_WIDTH`, and `ROI_HEIGHT`
in `config.h` (see the comment above them for what they mean), then repeat
step 8 to reflash, and test again.

## 11. Generate training data

With everything running and working, leave it running while music plays.
Every screen change gets captured, read, and saved automatically.

Specifically make these happen at least a few times each, since normal
play does not produce enough of them on its own:

- A track with a recognizable "Artist - Title" style name.
- A track with no separate artist in the name at all.
- A track with a parenthetical remix or version tag, like
  "Song (Someone's Remix)".
- A track with a "Feat" credit in the name.

## 12. How much is enough

There is no strict tested minimum. As a rough rule of thumb, not a
validated number, aim for at least a few hundred entries in
`ml/dataset/labels.jsonl`, covering many different tracks and all four
cases from step 11. More is better, up to a large built-in ceiling that
you are very unlikely to reach in a normal session.

## 13. Package the dataset and send it in

Stop the backend (`Ctrl+C` in its terminal window). Find the `ml/dataset`
folder at the root of the project; it contains an `images` folder and a
`labels.jsonl` file. Zip that `ml/dataset` folder into a single file, and
send it to the maintainer through whatever channel you have arranged
together. This project does not define a specific upload method; use
whatever you have agreed on.

Training happens on the maintainer's side after that, not on your
computer, unless you choose the optional section at the end of this guide.

## 14. Keep the rig running

There is nothing else to do until the maintainer asks for more data or
sends a trained model back. If asked for more, repeat steps 10 through 13.

## 15. When a trained model comes back: switch to BLE

The maintainer will send you a file named `ocr_model.h`. This step has
several parts; skipping one will cause a confusing failure later, so follow
them in order.

**a.** Replace `firmware/src/ocr_model.h` with the file you were sent.

**b.** In `config.h`, set `BLE_PASSKEY` to a random six-digit number (you
did not need this during the WiFi phase). Then comment out
`TRANSPORT_WIFI` and uncomment `TRANSPORT_BLE`, the reverse of step 7.

**c.** Rebuild and reflash, same commands as step 8:
```
pio run
pio run -t upload
```

**d. macOS only, before the next step:** open System Settings, Privacy and
Security, Bluetooth, and grant Bluetooth permission to the terminal
application you are about to run the server from. Skipping this is the
single most confusing BLE failure there is: no error appears, the rig
simply never shows up, as if nothing were listening.

**e.** Start the server again, with a different command from step 9:
```
cd server
pip install -r requirements-ble.lock
```
Linux or macOS:
```
export BACKEND_TOKENS=player1:<your-token>
export BLE_ENABLED=1
uvicorn app:app --host 127.0.0.1 --port 8000
```
Windows (PowerShell):
```
$env:BACKEND_TOKENS = "player1:<your-token>"
$env:BLE_ENABLED = "1"
uvicorn app:app --host 127.0.0.1 --port 8000
```

**f.** Pair the rig with the computer. The rig advertises itself as
`OCR-` followed by six characters, for example `OCR-A4F2C9`; if you have
more than one rig, note which one is which now.

Windows: Settings, Bluetooth and devices, turn Bluetooth on, Add device,
Bluetooth, select the `OCR-` entry, confirm the passkey matches the
`BLE_PASSKEY` you set in part (b), finish.

macOS: System Settings, Bluetooth, turn it on, find the `OCR-` entry under
nearby devices, click Connect, confirm the same passkey when prompted.

Exact button names and screens can vary slightly between operating system
versions; look for the option that means pair or connect.

**g.** Confirm it worked: the server's terminal should log the connection,
and `now_playing_player1.txt` should keep updating as before, now with no
WiFi and no Caddy involved at all.

For anything not covered here, `docs/ble_transport.md` is the deeper
reference, including its own troubleshooting table.

## Optional: train it yourself

Most readers should skip this and use step 13 instead. This is for someone
who wants to attempt training locally rather than sending the dataset off.

```
cd ml
pip install -r requirements.lock
python synth.py
```
Generates extra synthetic training images for characters real captures
underrepresent.
```
python prepare_chars.py
```
Cuts each captured track image into individual character images, using
Tesseract to find the letters.
```
python train.py
```
Trains the character-recognition model on the prepared images.
```
python convert.py
```
Shrinks the trained model to run on the small chip on the rig, and checks
it is still accurate enough before accepting it.
```
python export_charset.py
python export_model_header.py ../firmware/models/ocr_model.tflite
```
Writes the finished model into a file the firmware can be built with. If
this succeeds, `firmware/src/ocr_model.h` is now a real model rather than
the placeholder, and you can continue directly to step 15, parts (b)
onward, skipping part (a) since you already have the file in place.

## If you get stuck

Send the maintainer: which numbered step you were on, the exact error
message or a screenshot, and your operating system. That is usually enough
to diagnose remotely without a lot of back and forth.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Board not found in step 8 | Most likely a charge-only USB cable. Try a known-good data cable first. |
| `pio run` fails on the first try | The first run downloads several hundred MB of tools; a slow or interrupted connection can fail partway. Run it again. |
| Rig connects to WiFi but the overlay never updates | Either the firewall prompt in step 5 was blocked or dismissed, or `BACKEND_URL` in `config.h` has a now-stale address because your router reassigned it since step 6. |
| `WiFi connect timed out, halting` | Your network may be 5GHz only. See the warning in step 6. |
| Server refuses to start, mentions `BACKEND_TOKENS` | The token or player ID typed when starting the server does not match `config.h`. Check both match exactly. |
| Uploads return 401 | `BACKEND_TOKEN` in `config.h` does not match the token given to `BACKEND_TOKENS` when starting the server. |
| Rig never appears in the Bluetooth list (step 15) | On macOS, Bluetooth permission was not granted to the terminal app (part d). Otherwise, confirm `BLE_ENABLED=1` was set and `requirements-ble.lock` was installed. |
| Two rigs, only one publishes | Both were flashed with the same `BACKEND_TOKEN`. Give each rig its own token and `PLAYER_ID`. |
| Track name is stuck on an old value | If the unit was switched to the Performance screen, this is expected; it holds the last known value until the unit returns to Normal playback. |
| Rig reboots or drops out randomly | Try a different USB port, ideally directly on the computer rather than through a hub, or a different power source. |
