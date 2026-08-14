# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
`0.y.z` is unstable initial development; the public API is not defined
until 1.0.0.

## [Unreleased]

### Added

- `docs/quickstart.md`: a non-technical, step by step guide to flashing a
  rig on WiFi, testing it, collecting training data, packaging it for the
  maintainer, and switching to BLE once a trained model comes back. Linked
  from the top of `README.md`.
- Bluetooth LE transport, now the default firmware build. A rig sends
  on-device OCR results to a server on Windows or macOS with no network
  in the path. Results only: BLE does not carry ROI frames, so a BLE rig
  runs no Tesseract comparison and contributes no training data. Build
  with `TRANSPORT_WIFI` in `config.h` for the HTTPS path, which is what
  collects the dataset the on-device model is trained from. See
  `docs/ble_transport.md`.
- `server/ble_bridge.py`: BLE central, running inside the uvicorn
  process under `BLE_ENABLED`. Serves several rigs at once, capped by
  `BLE_MAX_DEVICES`, and rejects a second device claiming a
  `player_id` that is already connected.
- `firmware/src/ble_transport.cpp`: GATT peripheral, LE Secure
  Connections pairing with `BLE_PASSKEY`, and an acknowledged framing
  protocol over a notify characteristic.
- Undelivered results are queued on the rig and flushed oldest first on
  reconnect, so a track change during a dropout is not lost.
- `sole_source` on `arbiter.record_ondevice`, letting the on-device
  model publish when it is the only source. The confidence gates still
  apply; the agreement scoring does not, having nothing to compare
  against. Existing callers are unaffected.
- `server/ingest.py`: the result path `/result` and the BLE bridge
  share, so neither can drift from the other's validation.
- `bleak` as an optional server dependency, pinned in
  `server/requirements-ble.txt`. An HTTP-only deployment installs
  nothing new.
- `w11-esp32s3-production`, a compile-only Secure Boot V2 and AES-256
  release-mode flash-encryption profile, plus a controlled signing and
  provisioning guide.
- `dependency-provenance.json`, recording immutable firmware source and
  reviewed Caddy, Tesseract, and trained-data artifacts, plus a verifier
  for firmware archives and deployed OCR files.
- ML assurance tests for dataset containment, image limits, OCR
  alignment, split isolation, class coverage, quality gates, and TFLite
  model contracts.
- `Caddyfile`: local HTTPS reverse proxy with security headers. Firmware
  reaches the backend only through it.
- `.github/workflows/app-tests.yml`: backend tests, firmware build,
  manifest and lock agreement, and `caddy validate` in CI. Application
  checks run only for relevant paths. Firmware waits until review-ready
  and restores an incremental build cache on later runs.
- `scripts/detect_app_changes.py`: classifies changed paths for the
  application CI gate.
- `scripts/check_lock_sync.py`: blocks when a requirements manifest and
  its compiled lock disagree.
- `scripts/sync.py` and the eight tool-specific copies of `AGENTS.md` it
  generates.
- `.editorconfig`, `.gitattributes`, `.claudeignore`.
- `LICENSE` (MIT) and `THIRD-PARTY-NOTICES.md`.
- `requirements.lock` for `server/`, `server/` dev, and `ml/`, with
  hashes.

### Changed

- `docs/hardware_documentation.md`: the camera lens is confirmed fixed
  focus, no adjustment ring, by direct inspection.
- The firmware job builds every transport. It compiled only the one
  `config.h.example` defaults to, so `TRANSPORT_WIFI` was never built in
  CI and could break unnoticed.
- The default firmware transport is BLE. Flashed WiFi rigs are
  unaffected until reflashed, and `TRANSPORT_WIFI` keeps the previous
  behavior.
- `docs/hardware_documentation.md`: Bluetooth moves out of "Open
  questions" into a "Radios" subsection under "Confirmed facts". The
  vendor specification's silence on Bluetooth was a gap in that
  document, not evidence the module lacks the radio.
- The PlatformIO platform is pinned to the release's Git commit instead
  of its replaceable release archive URL. CI binds its framework packages
  to downloaded archives that pass the reviewed SHA-256 digests.
- ML training uses deterministic source-group splits. Real calibration
  and evaluation samples are disjoint from training, and synthetic
  samples never enter either production evaluation split.
- Pinned GitHub Actions by commit SHA, `esp32-camera` by commit, and the
  Caddy CI image by digest. Tags are mutable.
- CI cancels superseded pull request runs and fails jobs after 30 minutes.
  Workflows no longer duplicate successful pull request checks after
  merge.
- `/frame` is a synchronous endpoint, so FastAPI runs its blocking
  Tesseract call in a threadpool rather than on the event loop.
- uvicorn binds to loopback. Caddy is the only entry point.
- Setup installs from the lock files.

### Fixed

- ML dataset ingestion rejects unexpected names, traversal, symlinks,
  oversized compressed or decoded images, unbounded label manifests,
  duplicate samples crossing splits, and stalled Tesseract calls.
- Character crops are saved only when Tesseract's complete box sequence
  matches the expected track. Training fails on missing classes.
- Conversion blocks low-accuracy or excessively degraded models and
  validates the TFLite tensor contract before writing or embedding it.
- Firmware verifies the TFLite FlatBuffer and exact tensor storage before
  dereferencing model data.
- Firmware bounds TLS, connection, read, retry, and backoff phases. A
  supervisor restarts requests that exceed the complete upload deadline.
  A failed `/frame` upload no longer commits the ROI hash, so the same
  track retries on the next capture cycle.
- Output is published under the state lock and written atomically.
  Concurrent updates could publish out of order, and a reader could
  observe a partially written file.
- `arbiter.is_trusted` reads agreement history under the lock.
- Dataset quota bounds bytes and free disk space, reserved atomically.
  Filenames carry a random suffix; label appends are serialized.
- Regenerated `server/requirements-dev.lock`, which installed pytest
  8.4.2 while the manifest pinned 9.0.3 (GHSA-6w46-j5rx-g56g).
- Division-by-zero guards in `firmware/src/ondevice_ocr.cpp` and
  `ml/convert.py`.
- `ml/train.py` shuffles before `validation_split`. Keras splits from
  the tail, so the ordered labels file yielded an all-synthetic
  validation set.
- `firmware/src/ondevice_ocr.cpp` checks output tensor `dims->size`
  before indexing.
- Removed dead branches and duplicated calls in `ml/prepare_chars.py`,
  `ml/convert.py`, `server/dataset.py`, `server/arbiter.py`, and
  `firmware/src/char_segment.cpp`.

### Security

- Each rig now needs its own credential. `BACKEND_TOKENS` maps
  `player_id` to token, and a credential authorizes only its own
  `player_id`, so a compromised rig cannot overwrite another deck's
  output or poison its training data. The single `BACKEND_TOKEN` is
  refused at startup with migration instructions rather than silently
  kept working.
- Capture endpoints require a bearer token (`BACKEND_TOKEN`), compared
  with `hmac.compare_digest`. The server refuses to start without one.
  `/static` and `/output` stay open; OBS cannot send a header.
- Firmware verifies the backend certificate against a pinned CA
  (`BACKEND_CA_CERT`) instead of `WiFiClientSecure::setInsecure()`,
  which accepted any certificate.
- `player_id` and `capture_id` are validated, and write paths are
  re-checked for containment. Both previously reached the filesystem
  unvalidated.
- `confidence` must be finite and within 0.0 through 1.0. A missing or
  NaN value no longer bypasses the low-confidence gate.
- Caddy caps request bodies at 4MB and sets connection timeouts.
- Image dimensions are read from the header before decoding, with a
  2 Mpx budget.
- Tesseract calls have a 20 second deadline and a concurrency bound.
- Uploads are size-capped and must begin with the JPEG magic bytes.
- Dataset collection and per-player state are bounded.
- `cropRoi` validates `fb->len` and `fb->format` before its `memcpy`.
- Overlay CSS and JavaScript moved out of line, so the proxy's
  `default-src 'self'` no longer blocks them.
- `.gitignore` excludes `.env`, `*.pem`, `*.key`, and `secrets.*`.

## [0.1.0] - 2026-08-13

First implementation of the capture to overlay pipeline. Nothing in this
release has been verified against real hardware.

### Added

- Repository policy (`AGENTS.md`) and the enforcement scripts in
  `scripts/` that back its mechanically checkable rules, wired into
  GitHub Actions on every pull request.
- Hardware reference material in `docs/`: W11 board schematics and FCC
  filings, ESP32-S3 datasheets, XDJ-1000 and XDJ-1000MK2 manuals,
  digested into `docs/hardware_documentation.md` and
  `docs/xdj_screen_reference.md`.
- Firmware camera bring-up: OV5640 init over the DVP pin map from the
  schematics, VGA RGB565 capture, configurable ROI crop, and FNV-1a
  change detection so unchanged screens do no further work.
- Firmware networking: WiFi connect from `config.h`, JPEG encode of the
  ROI crop, and multipart upload to the backend.
- Backend (`server/`): FastAPI service with `/frame` (JPEG upload, runs
  Tesseract) and `/result` (on-device OCR result), plus output sinks
  writing `now_playing_<player_id>.txt`, `now_playing.txt`,
  `now_playing.json`, and an OBS Browser Source page.
- Artist parsing: `server/sinks.py` splits a leading artist out of an
  `Artist - Title` shaped track string, keeping the verbatim text as the
  source of truth.
- Auto-labeled dataset collection: every OCR'd frame records its ROI
  crop and Tesseract label into `ml/dataset/`, tagged by `player_id`.
- Character classifier training pipeline (`ml/`): fixed charset,
  per-character crops derived from Tesseract's character-level boxes,
  synthetic renders in Coda for underrepresented classes, a small CNN,
  and int8 post-training quantization to TFLite.
- Code generators keeping firmware and training in sync:
  `ml/export_charset.py` writes `firmware/src/charset.h`, and
  `ml/export_model_header.py` embeds a `.tflite` model as a C array.
- On-device inference: TFLite-Micro interpreter, Otsu threshold plus
  column projection character segmentation, and per-character
  classification against the embedded model. Skipped at runtime when no
  model is embedded, leaving the Tesseract path unaffected.
- Arbitration (`server/arbiter.py`): pairs the on-device and Tesseract
  results for one capture by a shared `capture_id`, logs disagreements,
  and publishes Tesseract by default until the on-device model's recent
  agreement rate clears a trust threshold.
- Robustness: WiFi reconnect inside the capture loop without halting,
  retry with doubling backoff on both upload endpoints, per-track
  confidence from the on-device model, and rejection of empty and
  low-confidence reads on both OCR paths so a bad read holds the last
  known good value.
- `scripts/check_docs_updated.py`, warning only: flags changes to
  `firmware/`, `server/`, or `ml/` that do not touch this file or the
  README.

### Known limitations

- No trained on-device model ships. `firmware/src/ocr_model.h` is a
  zero-length placeholder and on-device inference stays disabled until a
  real model is embedded.
- ROI coordinates in `firmware/src/config.h.example` are placeholders,
  not measured against a physical camera mount.
- Character segmentation differs between training (Tesseract boxes) and
  inference (projection profile), an unmeasured accuracy risk.
- The character classifier was exercised on synthetic data only.

[Unreleased]: https://github.com/abuzucom/1a2n-track-ocr/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/abuzucom/1a2n-track-ocr/releases/tag/v0.1.0
