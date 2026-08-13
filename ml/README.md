# ml

Trains the on-device OCR character classifier.

## dataset/

Auto-labeled by `server/dataset.py`: every frame the backend
OCRs gets recorded here, tagged by `player_id`. Tesseract's own errors
are present in these labels; spot-check a sample before training, do not
trust them blindly.

- `dataset/images/<player_id>_<timestamp_ms>.jpg`: the ROI crop as
  uploaded by the firmware.
- `dataset/labels.jsonl`: one JSON object per line, matching an image by
  filename: `{"image": ..., "player_id": ..., "track": ..., "confidence":
  ..., "timestamp_ms": ...}`.

Capture these cases manually, since normal operation underrepresents
them: tracks with and without a distinguishable artist, parenthetical
remix tags, and "Feat" credits. See `docs/xdj_screen_reference.md` for
examples.
