# ml

Trains the on-device OCR character classifier.

## dataset/

Auto-labeled by `server/dataset.py`: every frame the backend OCRs gets
recorded here, tagged by `player_id`. Preparation accepts only flat,
server-generated JPEG names, rejects symlinks, and checks compressed
bytes and decoded pixels before loading an image. Label manifests are
regular files bounded by bytes, line length, and record count.

- `dataset/images/<player_id>_<timestamp_ms>.jpg`: the ROI crop as
  uploaded by the firmware.
- `dataset/labels.jsonl`: one JSON object per line, matching an image by
  filename: `{"image": ..., "player_id": ..., "track": ..., "confidence":
  ..., "timestamp_ms": ...}`.

`prepare_chars.py` gives both Tesseract calls a 20 second deadline and
keeps crops only when the complete box sequence matches the expected
track after removing spaces. A mismatch rejects the whole capture rather
than shifting labels onto later boxes.

Character samples receive a deterministic split based on their source
capture. All characters from one real frame stay in exactly one of
`train`, `validation`, `calibration`, or `evaluation`; synthetic
font-size groups enter only training or validation. Training stops if
any charset class is absent. Conversion uses separate real calibration
and evaluation groups and stops before writing an artifact when absolute
accuracy or quantization-loss gates fail.

Capture these cases manually, since normal operation underrepresents
them: tracks with and without a distinguishable artist, parenthetical
remix tags, and "Feat" credits. See `docs/xdj_screen_reference.md` for
examples.
