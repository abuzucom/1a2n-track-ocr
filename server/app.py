"""HTTP server: receives ROI frames, runs OCR, serves now-playing output."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles

import ocr
import sinks

sinks.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory=str(sinks.OUTPUT_DIR)), name="output")


@app.post("/frame")
async def receive_frame(player_id: str = Form(...), file: UploadFile = File(...)):
    image_bytes = await file.read()
    result = ocr.extract_track_text(image_bytes)
    changed = sinks.update(
        player_id, result.track, source="tesseract", confidence=result.confidence
    )
    return {"track": result.track, "confidence": result.confidence, "changed": changed}
