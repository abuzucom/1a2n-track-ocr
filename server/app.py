"""HTTP server: receives ROI frames, runs OCR, serves now-playing output."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

import arbiter
import auth
import ble_bridge
import dataset
import ingest
import ocr
import sinks
import validation
# Re-exported: the model moved to ingest.py so the BLE bridge parses
# payloads through the same field constraints. Kept importable from here
# because it is part of the /result request contract.
from ingest import OndeviceResult  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# The ROI crop is a small JPEG of one text field, tens of KB in practice.
# The cap exists so an unauthenticated body cannot be read into memory
# unbounded; it is not a tuning knob for image quality.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024

# JPEG SOI marker. The firmware sends JPEG and dataset.py stores the
# bytes with a .jpg extension, but cv2.imdecode would accept PNG, TIFF,
# WebP, or OpenEXR, leaving stored content and extension disagreeing.
JPEG_MAGIC = b"\xff\xd8\xff"


# Fail at import rather than serving the capture endpoints open.
auth.credentials()

sinks.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run the BLE bridge alongside the HTTP server, if enabled.

    In-process rather than a separate service: arbiter and sinks hold
    process-local state, so a second process would keep its own copy and
    the two would race writing the now_playing files. See ble_bridge.py.
    """
    if not ble_bridge.enabled():
        yield
        return

    task = asyncio.create_task(ble_bridge.run_bridge())
    try:
        yield
    finally:
        task.cancel()
        # Awaited, not abandoned: a cancelled task that is never awaited
        # swallows whatever it raised on the way down.
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(lifespan=lifespan)
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
    # sole_source stays off here: a rig that can reach this endpoint over
    # HTTP also uploads frames, so Tesseract arbitration applies.
    return ingest.record_ondevice_result(payload, authorized)
