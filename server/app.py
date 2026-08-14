"""HTTP server: receives ROI frames, runs OCR, serves now-playing output."""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import arbiter
import auth
import dataset
import ocr
import sinks
import validation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# The ROI crop is a small JPEG of one text field, tens of KB in practice.
# The cap exists so an unauthenticated body cannot be read into memory
# unbounded; it is not a tuning knob for image quality.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024

# JPEG SOI marker. The firmware sends JPEG and dataset.py stores the
# bytes with a .jpg extension, but cv2.imdecode would accept PNG, TIFF,
# WebP, or OpenEXR, leaving stored content and extension disagreeing.
JPEG_MAGIC = b"\xff\xd8\xff"


class OndeviceResult(BaseModel):
    player_id: str
    capture_id: str
    track: str = Field(max_length=validation.MAX_TRACK_LENGTH)
    # Optional preserves the request contract, but a missing value no
    # longer skips the gate; see arbiter.py. allow_inf_nan matters:
    # Pydantic accepts NaN for a bare float, and "NaN < threshold" is
    # False. Confidence is a dequantized softmax value, so 0.0 to 1.0.
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, allow_inf_nan=False
    )


# Fail at import rather than serving the capture endpoints open.
auth.credentials()

sinks.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory=str(sinks.OUTPUT_DIR)), name="output")


# Sync def, not async: extract_track_text shells out to Tesseract and
# blocks. As an async endpoint it stalled the event loop for the whole
# call, serializing concurrent requests. FastAPI runs a sync endpoint in
# a threadpool instead.
@app.post("/frame")
def receive_frame(
    player_id: Annotated[str, Form()],
    capture_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    authorized: Annotated[str, Depends(auth.authorized_player)] = "",
):
    validation.validate_identifier(player_id, "player_id")
    validation.validate_identifier(capture_id, "capture_id")
    # The credential decides which player_id it may write, so a rig
    # cannot claim another deck's identity.
    auth.require_player_match(authorized, player_id)

    # Read one byte past the cap so an oversized body is detected without
    # reading all of it into memory.
    image_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload exceeds size limit")
    if not image_bytes.startswith(JPEG_MAGIC):
        raise HTTPException(status_code=415, detail="upload is not a JPEG")

    try:
        result = ocr.extract_track_text(image_bytes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    dataset.record(player_id, image_bytes, result.track, result.confidence)
    changed = arbiter.record_tesseract(player_id, capture_id, result.track, result.confidence)
    return {"track": result.track, "confidence": result.confidence, "changed": changed}


@app.post("/result")
def receive_result(
    payload: OndeviceResult,
    authorized: Annotated[str, Depends(auth.authorized_player)] = "",
):
    validation.validate_identifier(payload.player_id, "player_id")
    validation.validate_identifier(payload.capture_id, "capture_id")
    auth.require_player_match(authorized, payload.player_id)
    agree = arbiter.record_ondevice(
        payload.player_id, payload.capture_id, payload.track, payload.confidence
    )
    return {"received": True, "agree": agree}
