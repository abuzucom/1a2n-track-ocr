"""HTTP server: receives ROI frames, runs OCR, serves now-playing output."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import dataset
import ocr
import sinks


class OndeviceResult(BaseModel):
    player_id: str
    track: str

sinks.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory=str(sinks.OUTPUT_DIR)), name="output")


@app.post("/frame")
async def receive_frame(player_id: str = Form(...), file: UploadFile = File(...)):
    image_bytes = await file.read()
    result = ocr.extract_track_text(image_bytes)
    dataset.record(player_id, image_bytes, result.track, result.confidence)
    changed = sinks.update(
        player_id, result.track, source="tesseract", confidence=result.confidence
    )
    return {"track": result.track, "confidence": result.confidence, "changed": changed}


@app.post("/result")
async def receive_result(payload: OndeviceResult):
    # Logged only, not yet fed into sinks: deciding which of the
    # on-device and Tesseract results to trust is arbiter.py's job, not
    # built yet. Calling sinks.update() from both this and /frame right
    # now would make each one's "did it change" comparison fight the
    # other's, since both would share the same per-player_id last-known
    # state.
    print(f"on-device result for {payload.player_id}: {payload.track!r}")
    return {"received": True}
