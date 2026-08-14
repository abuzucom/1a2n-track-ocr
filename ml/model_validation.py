"""Quality and structure gates for firmware TFLite artifacts."""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from charset import CHARSET, PATCH_SIZE


MAX_TFLITE_BYTES = 1024 * 1024
MIN_FLOAT_ACCURACY = 0.90
MIN_QUANTIZED_ACCURACY = 0.90
MAX_QUANTIZATION_ACCURACY_DROP = 0.05


def _validate_tensor(detail: dict, expected_shape: list[int], role: str) -> None:
    shape = list(detail.get("shape", []))
    if shape != expected_shape:
        raise ValueError(f"TFLite {role} shape {shape} does not match {expected_shape}")
    if np.dtype(detail.get("dtype")) != np.dtype(np.int8):
        raise ValueError(f"TFLite {role} tensor must use int8")
    scale, zero_point = detail.get("quantization", (0.0, 0))
    if not math.isfinite(float(scale)) or scale <= 0:
        raise ValueError(f"TFLite {role} tensor has invalid quantization scale")
    if not -128 <= int(zero_point) <= 127:
        raise ValueError(f"TFLite {role} tensor has invalid zero point")


def validate_tflite_model(
    model_bytes: bytes,
    *,
    interpreter_factory: Callable[..., object] | None = None,
) -> None:
    """Validate a TFLite buffer and the firmware-facing tensor contract."""
    if not model_bytes:
        raise ValueError("TFLite model is empty")
    if len(model_bytes) > MAX_TFLITE_BYTES:
        raise ValueError(f"TFLite model exceeds the {MAX_TFLITE_BYTES} byte limit")
    if len(model_bytes) < 8 or model_bytes[4:8] != b"TFL3":
        raise ValueError("TFLite model has an invalid FlatBuffer identifier")

    if interpreter_factory is None:
        import tensorflow as tf

        interpreter_factory = tf.lite.Interpreter
    try:
        interpreter = interpreter_factory(model_content=model_bytes)
        interpreter.allocate_tensors()
    except Exception as error:
        raise ValueError(f"TFLite model cannot allocate tensors: {error}") from error

    inputs = interpreter.get_input_details()
    outputs = interpreter.get_output_details()
    if len(inputs) != 1 or len(outputs) != 1:
        raise ValueError("TFLite model must have exactly one input and one output")
    _validate_tensor(inputs[0], [1, PATCH_SIZE, PATCH_SIZE, 1], "input")
    _validate_tensor(outputs[0], [1, len(CHARSET)], "output")


def enforce_quality_gates(float_accuracy: float, quantized_accuracy: float) -> None:
    """Reject a model that fails absolute or quantization accuracy gates."""
    if not math.isfinite(float_accuracy) or not math.isfinite(quantized_accuracy):
        raise RuntimeError("model accuracy must be finite")
    if float_accuracy < MIN_FLOAT_ACCURACY:
        raise RuntimeError(
            f"float accuracy {float_accuracy:.3f} is below {MIN_FLOAT_ACCURACY:.3f}"
        )
    if quantized_accuracy < MIN_QUANTIZED_ACCURACY:
        raise RuntimeError(
            f"quantized accuracy {quantized_accuracy:.3f} is below "
            f"{MIN_QUANTIZED_ACCURACY:.3f}"
        )
    drop = float_accuracy - quantized_accuracy
    if drop > MAX_QUANTIZATION_ACCURACY_DROP:
        raise RuntimeError(
            f"quantization accuracy drop {drop:.3f} exceeds "
            f"{MAX_QUANTIZATION_ACCURACY_DROP:.3f}"
        )
