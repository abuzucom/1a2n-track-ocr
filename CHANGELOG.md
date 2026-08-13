# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
`0.y.z` is unstable initial development; the public API is not defined
until 1.0.0.

## [Unreleased]

### Added

- `LICENSE`: MIT.
- `THIRD-PARTY-NOTICES.md`: attribution for the reference documents in
  `docs/` and the OFL typeface in `ml/fonts/`, plus the license of every
  build and runtime dependency. Records that the firmware statically
  links the LGPL-2.1-or-later Arduino ESP32 core, and what that does and
  does not require.

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
