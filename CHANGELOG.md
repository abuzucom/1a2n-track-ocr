# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
`0.y.z` is unstable initial development; the public API is not defined
until 1.0.0.

## [Unreleased]

### Added

- `app-tests.yml` workflow running the checks CI never ran: backend
  pytest, firmware `pio run`, manifest and lock agreement, and
  `caddy validate`. The existing workflows check policy and prose only,
  so authentication could have been deleted from both endpoints with
  every check still green.
- `scripts/check_lock_sync.py`, blocking: verifies each
  `requirements*.txt` pin matches its compiled `.lock`. An automated
  dependency bump can edit a manifest and leave the lock alone, which
  nothing caught by eye.

### Fixed

- Regenerated `server/requirements-dev.lock`, which still installed
  pytest 8.4.2 while the manifest pinned 9.0.3. The stale version is
  affected by GHSA-6w46-j5rx-g56g.

### Security

- Firmware now verifies the backend's TLS certificate against a pinned
  local CA (`BACKEND_CA_CERT` in `config.h`, the Caddy `tls internal`
  root) instead of calling `WiFiClientSecure::setInsecure()`. The
  previous "protect token transit" framing only held against a passive
  listener: `setInsecure()` accepts any certificate, so an active
  attacker on the same network could present their own certificate and
  receive the bearer token. Verification now rejects that.

### Added

- Added `Caddyfile` for a local reverse proxy enforcing HTTPS and OWASP Top 10 security headers.
- Updated ESP32 firmware in `uploader.cpp` to use `WiFiClientSecure` to protect token transit.
- Added `Caddyfile` to the architecture orientation map in `AGENTS.md` and repo layout in `README.md`.

### Fixed

- Added explicit division-by-zero guards in `firmware/src/ondevice_ocr.cpp` and `ml/convert.py` to prevent crashes from corrupt model parameters or empty datasets.
- Shuffled training arrays before `validation_split` in `ml/train.py`.
  Keras splits from the tail without shuffling, so the ordered labels
  file produced a validation set of only synthetic samples.
- Added output tensor `dims->size` precondition in
  `firmware/src/ondevice_ocr.cpp` before indexing `data[size - 1]`,
  matching the existing input tensor validation.
- Hoisted duplicate `image_to_boxes` call in `ml/prepare_chars.py` and
  replaced contradictory `.get()` vs direct `[]` access with consistent
  direct access.
- Removed impossible `not IMAGES_DIR.is_dir()` branch in
  `server/dataset.py`; the sole caller creates the directory first.
- Folded redundant `key not in _pending_tesseract` re-test and replaced
  `setdefault` on a proven-absent key with direct assignment in
  `server/arbiter.py`.
- Removed tautological `if (top < bottom)` guard, redundant
  `lastActiveX >= 0` check, and structurally unnecessary `std::max(1, ...)`
  clamping in `firmware/src/char_segment.cpp`.
- Removed unreachable empty-list guard in `ml/convert.py`; the caller
  raises before reaching the function if samples is empty.
### Security

- Capture endpoints now require a shared bearer token, configured as
  `BACKEND_TOKEN` on both the backend and the firmware. The server
  refuses to start without one rather than serving them open. Comparison
  uses `hmac.compare_digest`. `/static` and `/output` stay open because
  OBS reads them and cannot send a header.
- `player_id` and `capture_id` are validated against a strict identifier
  pattern. Both reached filesystem paths unvalidated, so a crafted value
  could write outside the intended directory, either through `../` or
  through an absolute path, which `pathlib` honors by discarding the
  left operand. Paths are now re-checked for containment where they are
  built, so the boundary check is not the only thing standing between a
  request and an arbitrary file write.
- A missing `confidence` on `/result` no longer bypasses the on-device
  confidence gate. It previously skipped the check entirely, so an
  unmeasured result was treated as trustworthy.
- Uploads are capped at 4 MB, must begin with the JPEG magic bytes, and
  decoded dimensions are checked before the 3x upscale, which multiplies
  pixel count ninefold and made small compressed images a memory bomb.
- Dataset collection and per-player state are bounded. Both previously
  grew without limit, keyed on a request-supplied value.
- `cropRoi` validates `fb->len` and `fb->format` before its `memcpy`,
  instead of trusting the frame descriptor to describe its own buffer.
- `.gitignore` excludes `.env`, `*.pem`, `*.key`, and `secrets.*`.

### Changed

- `/frame` is a synchronous endpoint so FastAPI runs its blocking
  Tesseract call in a threadpool. It previously stalled the event loop
  for the duration of every request.

### Added

- `scripts/sync.py` from the `abuzucom/agents` template, and the eight
  tool-specific copies of `AGENTS.md` it generates (`CLAUDE.md`,
  `GEMINI.md`, `CONVENTIONS.md`, `.cursorrules`, `.clinerules`,
  `.windsurfrules`, `.copilot-instructions`,
  `.github/copilot-instructions.md`). The template's sync step had never
  been run, so every agent tool other than those reading `AGENTS.md`
  natively saw no conventions at all.
- `.editorconfig`, `.gitattributes`, and `.claudeignore` from the same
  template, copied verbatim. `.editorconfig` disables trailing-whitespace
  trimming for Markdown, which is what stripped the hard line breaks out
  of this repo's `AGENTS.md`. `.gitattributes` caused no renormalization:
  all tracked files were already LF in the index.
- `LICENSE`: MIT.
- `THIRD-PARTY-NOTICES.md`: attribution for the reference documents in
  `docs/` and the OFL typeface in `ml/fonts/`, plus the license of every
  build and runtime dependency. Records that the firmware statically
  links the LGPL-2.1-or-later Arduino ESP32 core, and what that does and
  does not require.
- `server/requirements.lock`, `server/requirements-dev.lock`, and
  `ml/requirements.lock`: fully resolved dependency trees with hashes,
  generated by `pip-compile`. The `.txt` files pinned only direct
  dependencies, leaving 14 transitive packages floating for the backend
  and 30 for the training pipeline.

### Changed

- Pinned GitHub Actions by commit SHA instead of by major-version tag
  (`actions/checkout` v4.4.0, `actions/setup-python` v5.6.0). A tag can
  be repointed by whoever controls the action's repository, so a tag pin
  is not a pin. Versions are unchanged; this is a pinning fix, not an
  upgrade.
- Pinned `esp32-camera` by commit instead of by its `v2.1.7` tag, for
  the same reason. Same code, immutable reference.
- README installs from the lock files rather than the `.txt` files, and
  documents that Tesseract's version cannot be pinned from this repo
  while its output is the training set's ground truth.

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
