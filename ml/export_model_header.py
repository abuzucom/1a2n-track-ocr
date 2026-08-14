"""Generate firmware/src/ocr_model.h from a .tflite file.

ESP32 Arduino projects have no general filesystem for loading a model at
runtime, so TFLite-Micro models are embedded as a C byte array instead.
Run this after convert.py produces a real trained model. Until then,
firmware/src/ocr_model.h stays a placeholder (zero-length array), and
on-device inference is skipped at runtime; see main.cpp.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from model_validation import MAX_TFLITE_BYTES, validate_tflite_model

OUTPUT_PATH = "../firmware/src/ocr_model.h"


def generate(tflite_path: str) -> str:
    model_path = Path(tflite_path)
    if model_path.stat().st_size > MAX_TFLITE_BYTES:
        raise ValueError(f"TFLite model exceeds the {MAX_TFLITE_BYTES} byte limit")
    with open(model_path, "rb") as handle:
        model_bytes = handle.read()
    validate_tflite_model(model_bytes)

    hex_bytes = ", ".join(f"0x{byte:02x}" for byte in model_bytes)
    return (
        f"// Generated from {tflite_path} by ml/export_model_header.py.\n"
        "// Do not hand-edit.\n\n"
        "#pragma once\n\n"
        "alignas(16) const unsigned char g_model[] = {" + hex_bytes + "};\n"
        "const int g_model_len = sizeof(g_model);\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tflite_path", help="path to the trained .tflite model")
    args = parser.parse_args()

    content = generate(args.tflite_path)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"wrote {OUTPUT_PATH} ({len(content)} bytes of source)")
