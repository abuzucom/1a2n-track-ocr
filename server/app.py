"""HTTP server: receives ROI frames, runs OCR, serves now-playing output."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import arbiter
import dataset
import ocr
import sinks


class OndeviceResult(BaseModel):
    player_id: str
    capture_id: str
    track: str

sinks.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory=str(sinks.OUTPUT_DIR)), name="output")


@app.post("/frame")
async def receive_frame(
    player_id: str = Form(...), capture_id: str = Form(...), file: UploadFile = File(...)
):
    image_bytes = await file.read()
    result = ocr.extract_track_text(image_bytes)
    dataset.record(player_id, image_bytes, result.track, result.confidence)
    changed = arbiter.record_tesseract(player_id, capture_id, result.track, result.confidence)
    return {"track": result.track, "confidence": result.confidence, "changed": changed}


@app.post("/result")
async def receive_result(payload: OndeviceResult):
    agree = arbiter.record_ondevice(payload.player_id, payload.capture_id, payload.track)
    return {"received": True, "agree": agree}
