# ml

On-device OCR model training. See the plan's Phase 4 for scope.

## dataset/

Auto-labeled by `server/dataset.py` (Phase 3): every frame the backend
OCRs gets recorded here, tagged by `player_id`. Tesseract's own errors
are present in these labels; spot-check a sample before training, do not
trust them blindly.

- `dataset/images/<player_id>_<timestamp_ms>.jpg`: the ROI crop as
  uploaded by the firmware.
- `dataset/labels.jsonl`: one JSON object per line, matching an image by
  filename: `{"image": ..., "player_id": ..., "track": ..., "confidence":
  ..., "timestamp_ms": ...}`.

Also worth capturing manually: tracks with and without a distinguishable
artist, parenthetical remix tags, "Feat" credits (see the real examples
in `docs/xdj_screen_reference.md`), since normal operation may
underrepresent them.
