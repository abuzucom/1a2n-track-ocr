# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
`0.y.z` is unstable initial development; the public API is not defined
until 1.0.0.

## [Unreleased]

### Added

- `Caddyfile`: local HTTPS reverse proxy with security headers. Firmware
  reaches the backend only through it.
- `.github/workflows/app-tests.yml`: backend tests, firmware build,
  manifest and lock agreement, and `caddy validate` in CI.
- `scripts/check_lock_sync.py`: blocks when a requirements manifest and
  its compiled lock disagree.
- `scripts/sync.py` and the eight tool-specific copies of `AGENTS.md` it
  generates.
- `.editorconfig`, `.gitattributes`, `.claudeignore`.
- `LICENSE` (MIT) and `THIRD-PARTY-NOTICES.md`.
- `requirements.lock` for `server/`, `server/` dev, and `ml/`, with
  hashes.

### Changed

- Pinned GitHub Actions by commit SHA, `esp32-camera` by commit, and the
  Caddy CI image by digest. Tags are mutable.
- `/frame` is a synchronous endpoint, so FastAPI runs its blocking
  Tesseract call in a threadpool rather than on the event loop.
- uvicorn binds to loopback. Caddy is the only entry point.
- Setup installs from the lock files.

### Fixed

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

First implementation of the full capture to overlay pipeline. Backfilled
from the seven build phases. Nothing in this release has been verified
against real hardware.

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
- Phase 4 was validated on synthetic data only.

[Unreleased]: https://github.com/abuzucom/1a2n-track-ocr/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/abuzucom/1a2n-track-ocr/releases/tag/v0.1.0
