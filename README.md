# 1a2n-track-ocr

Read the currently playing track off a Pioneer XDJ-1000 or XDJ-1000MK2
screen with a camera, and publish it to an OBS "now playing" overlay.

Neither unit exposes the playing track over an API. This system points a
W11 ESP32-S3 camera board at the player's screen, OCRs the track name
field, and writes the result to files OBS can read.

## Status

**Nothing here has been tested against real hardware.** It was built to
spec from the schematics and manuals in `docs/`. Calibration values (ROI
coordinates, poll interval, confidence thresholds) are configurable at
runtime, so a tester can adjust them without rebuilding.

The on-device OCR model is not trained. `firmware/src/ocr_model.h` is a
zero-length placeholder, and the firmware skips on-device inference when
no model is embedded. Training needs a dataset, which needs hardware.


## Hardware

| Part | Detail |
|---|---|
| Board | W11 ESP32-S3 (ESP32-S3R8, 16MB quad flash, 8MB octal PSRAM) |
| Camera | OV5640 on the W11 expansion board, DVP interface |
| Target | Pioneer XDJ-1000 or XDJ-1000MK2 |

Both player generations use the same screen layout, so one ROI and one
classifier serve both. See `docs/hardware_documentation.md` for the pin
map and `docs/xdj_screen_reference.md` for the screen layout.

One rig (one board plus camera) watches one player. A 2-deck setup runs
two rigs, each with its own `PLAYER_ID`.

## How it works

```
[XDJ screen] ...camera...> [W11 ESP32-S3 firmware]
                                     |
              on a timer (CAPTURE_INTERVAL_MS, default 20s):
              crop to the track name ROI, hash it, compare to
              the previous sample, act only when it changes
                                     |
                    +================+================+
                    |                                 |
          on-device OCR                       JPEG crop uploaded
          (TFLite-Micro char                  as HTTPS POST /frame
           classifier, when a                 (Bearer token,
           model is embedded)                  pinned CA cert)
                    |                                 |
        POST /result                          [Caddy, :443]
        (same HTTPS, token,                    TLS termination,
         pinned cert)                          OWASP headers,
                    |                          reverse_proxy for
                    |                          /frame and /result
                    |                                 |
                    |                          [uvicorn, :8000]
                    |                          Tesseract OCR runs on
                    |                          every frame. Records the
                    |                          crop plus its label into
                    |                          ml/dataset/ for training.
                    |                          Rejects unauthenticated
                    |                          or malformed requests.
                    |                                 |
                    +================+================+
                                     |
                              [server/arbiter.py]
                    Pairs the two results by capture_id.
                    Tesseract publishes by default. On-device
                    publishes only after its agreement rate
                    clears a trust threshold. Rejects empty
                    and low-confidence reads from both.
                                     |
                    +================+================+
                    |                                 |
        now_playing.txt                    now_playing.json plus
        (OBS Text source,                  static/overlay.html,
         read from file)                   served by Caddy's own
                                            file_server directly
                                            (not proxied to uvicorn)
                                            (OBS Browser Source)
```

Both OCR paths run on every changed frame; neither is a fallback for
the other. Tesseract's output auto-labels the on-device model's training
data, and the arbiter publishes the on-device result only once its
agreement rate clears the threshold.

Caddy and uvicorn are separate processes; both must run. Firmware never
talks to uvicorn directly. Caddy serves `/static` and `/output` off disk
without authentication, since OBS cannot send a bearer token. Only
`/frame` and `/result` are proxied and token-checked.

## Repo layout

| Path | Contents |
|---|---|
| `firmware/` | PlatformIO project, Arduino framework, ESP32-S3 |
| `server/` | FastAPI backend, Tesseract OCR, arbitration, output sinks |
| `ml/` | Character classifier training pipeline (see `ml/README.md`) |
| `docs/` | Board schematics, FCC filings, chip datasheets, player manuals |
| `scripts/` | AGENTS.md policy check scripts, run by CI |
| `Caddyfile` | Local HTTPS reverse proxy configuration |

## Setup

### Dependency pinning

Install from the `.lock` files. Each `requirements.txt` lists direct
dependencies; the matching `requirements.lock` pins every transitive
dependency with a hash.

Regenerate a lock after editing the matching `.txt`:

```bash
cd server && python -m piptools compile --generate-hashes --strip-extras --output-file requirements.lock requirements.txt
```

These locks were resolved on Windows and CPython 3.13 with no
environment markers. Regenerate on Linux or macOS; TensorFlow resolves
differently.

Actions, the PlatformIO platform, and `esp32-camera` are pinned by commit
SHA. `dependency-provenance.json` records the corresponding release
archives and runtime artifact digests. CI verifies the mutable PlatformIO
archive and binds verified Arduino archives into the pinned platform
manifest before compiling.

### Backend

Needs the Tesseract OCR engine binary installed separately (system
package manager, or the Windows installer). `server/ocr.py` finds it on
PATH, or set `TESSERACT_CMD` to an explicit path.

Tesseract is a system binary, so the package locks cannot install it.
`dependency-provenance.json` records the approved Windows binary and
English `traineddata` version and SHA-256 digests. Verify deployed files
against that record before collecting comparable labels; another
platform needs its own reviewed artifact entry.

```powershell
python scripts/verify_dependency_provenance.py `
  --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe" `
  --traineddata "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata"
```

Each rig needs its own credential. Set `BACKEND_TOKENS` to comma
separated `player_id:token` pairs, each token matching that rig's
`BACKEND_TOKEN` in `config.h`. A credential authorizes only its own
`player_id`, so one compromised rig cannot overwrite another deck's
output. The server refuses to start without it rather than running open.

Bind uvicorn to loopback. Caddy runs on the same host and is the only
thing that should reach it; binding to `0.0.0.0` would expose a
plaintext port alongside the HTTPS one.

```bash
cd server && pip install -r requirements.lock && BACKEND_TOKENS=deck1:<token1>,deck2:<token2> uvicorn app:app --host 127.0.0.1 --port 8000
```

#### Running behind Caddy (required)

The firmware always connects over HTTPS through Caddy; it never talks to
uvicorn directly. Both processes run together.

1. Install [Caddy](https://caddyserver.com/).
2. Run Caddy from the repository root, which generates a local CA the
   first time it runs:
   ```bash
   caddy run
   ```
3. Install that CA into your own machine's trust store, so your browser
   trusts the overlay page:
   ```bash
   caddy trust
   ```
4. Copy the CA's root certificate into the firmware's `config.h` as
   `BACKEND_CA_CERT`. `firmware/src/config.h.example` lists where Caddy
   stores it per platform. The firmware verifies the backend against
   this CA; without it, it would accept any certificate on the network.

With Caddy running, point your OBS Browser Source at
`https://localhost/static/overlay.html`.

Output lands in `server/output/`: `now_playing_<player_id>.txt`,
`now_playing.txt` (single rig only), and `now_playing.json`. Point an
OBS Text source at the `.txt` file, or an OBS Browser Source at
`https://localhost/static/overlay.html`. Caddy is the only HTTP entry
point; with uvicorn on loopback there is no plaintext port to reach from
another machine.

### Firmware

```bash
cd firmware && cp src/config.h.example src/config.h
```

Edit `src/config.h`: WiFi credentials, `BACKEND_URL`, `BACKEND_TOKEN`,
`PLAYER_ID`, and the ROI. `BACKEND_TOKEN` must appear in the backend's
`BACKEND_TOKENS` paired with this rig's `PLAYER_ID`, or uploads are
rejected with 401, and a mismatched pairing with 403. `config.h` is gitignored and must never be committed. The ROI values
shipped in the example are placeholders; calibrate them against the
physical camera mount.

```bash
cd firmware && pio run && pio run -t upload
```

Production rigs use the compile-only `w11-esp32s3-production`
environment, which enables Secure Boot V2 and AES-256 flash encryption
in release mode. Provisioning burns irreversible eFuses and is not part
of the normal PlatformIO upload path. Follow
`docs/firmware_production.md` for signing, inspection, and the controlled
provisioning boundary.

### Training the on-device model

Only useful once `ml/dataset/` holds real captures from a running rig.

```bash
cd ml && pip install -r requirements.lock
```

```bash
cd ml && python synth.py && python prepare_chars.py && python train.py && python convert.py
```

Preparation rejects unexpected paths, oversized images, OCR timeouts,
and box sequences that do not exactly match the expected track. Training
uses deterministic source-group splits and requires every character
class. Conversion keeps calibration separate from evaluation and will
not replace the TFLite artifact unless both absolute accuracy and
quantization-loss gates pass.

Then embed the result and rebuild the firmware:

```bash
cd ml && python export_charset.py && python export_model_header.py ../firmware/models/ocr_model.tflite
```

## Design decisions

**On-device OCR is scoped to one font, one field.** General purpose OCR
does not fit the ESP32-S3's compute and memory budget. Both players
render track text in a fixed font at a fixed screen position, so the
on-device path detects the region, segments characters, and classifies
each one against a fixed vocabulary with a quantized int8 CNN.

**No text detection.** The ROI is configured, not found. The screen
layout is fixed, so this works, but a bumped camera breaks OCR until the
ROI is recalibrated.

**Character segmentation is the highest risk step.** Training
(`ml/prepare_chars.py`) segments with Tesseract's character-level boxes.
The firmware (`firmware/src/char_segment.cpp`) uses its own Otsu
threshold plus column projection, since there is no Tesseract on-device.
The two do not place boxes identically, so training and inference see
different distributions. Touching characters also produce overlapping
boxes; a crop labeled `D` can contain `De`. Spot-check derived crops
before training.

**Synthetic data supplements real captures, it does not replace them.**
EuroSans Pro, the player's apparent UI font, is not licensed for use
here, so `ml/synth.py` renders training characters in the visually close
Coda (Google Fonts, SIL OFL, committed under `ml/fonts/`). Synthetic
renders cover characters that real captures underrepresent.
`ml/train.py` logs the real to synthetic ratio per class, so a class
trained almost entirely on synthetic data stays visible.

**Track text is the source of truth; artist is derived.** Both
generations show one track field and no separate artist field. Whether
an artist can be split out depends on how the track was tagged on the
source USB drive. `server/sinks.py` parses a leading artist only when
the text matches an `Artist - Title` shape, and keeps the verbatim text
regardless.

**Text not found is distinct from a misread.** The Performance screen
does not show the track name field. An empty OCR result holds the last
known good value instead of blanking the overlay.

## Component status

| Component | State |
|---|---|
| Firmware capture, ROI crop, change detection | Built, unverified on hardware |
| Backend, Tesseract OCR, output sinks | Built and tested |
| Auto-labeled dataset collection | Built, no real captures yet |
| Character classifier training and quantization | Built, exercised on synthetic data only |
| On-device TFLite-Micro inference | Built, no trained model embedded |
| Arbitration between the two OCR sources | Built and tested |
| WiFi reconnect, retry and backoff, confidence rejection | Built, unverified on hardware |

Also outstanding: recreate the W11 schematics as an editable KiCad
project in `docs/`, with a PDF plot and a BOM.

## Verification

Without hardware:

- Build the firmware with `pio run`. Copy `config.h.example` to
  `config.h` first.
- Run `pytest server/tests/` for the arbiter's agreement tracking, trust
  threshold, input bounds, and concurrency behavior.
- Run `pytest ml/tests/` for dataset containment, split isolation, label
  alignment, quality gates, and model-contract validation.
- Run the policy checks in `scripts/`. CI runs these plus the backend
  tests, firmware build, and Caddyfile validation on every pull request.

With a physical rig:

- Confirm the ROI frames the track name text on a real unit.
- Change tracks and confirm the result reaches the overlay.
- Spot-check the auto-labeled dataset against the captures before
  training on it.
- Drop WiFi and confirm recovery without a manual reset.
- Restart the backend mid-upload and confirm the retry path runs.

## Conventions

`AGENTS.md` defines the policy this repo is developed under: branch
naming, commit format, style rules, and security constraints. The checks
in `scripts/` enforce the mechanically checkable subset, and CI runs them
on every pull request.

## License

MIT, see `LICENSE`.

That covers the source code only. `docs/` retains manufacturer and
regulatory documents, and `ml/fonts/` ships an OFL-licensed typeface;
both remain the property of their owners. See `THIRD-PARTY-NOTICES.md`
for attribution and for the license of every build and runtime
dependency.

One dependency is not permissive: the firmware statically links the
Arduino ESP32 core, which is LGPL-2.1-or-later. That imposes nothing on
distributing this source. Shipping a compiled firmware binary invokes
LGPL section 6, satisfied here by the source being public.
