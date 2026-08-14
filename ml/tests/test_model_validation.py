from pathlib import Path

import numpy as np
import pytest

import export_model_header
import model_validation


VALID_PREFIX = b"\x1c\x00\x00\x00TFL3"


class FakeInterpreter:
    def allocate_tensors(self):
        return None

    def get_input_details(self):
        return [{
            "shape": np.array([1, 24, 24, 1]),
            "dtype": np.int8,
            "quantization": (1 / 255, -128),
        }]

    def get_output_details(self):
        from charset import CHARSET

        return [{
            "shape": np.array([1, len(CHARSET)]),
            "dtype": np.int8,
            "quantization": (1 / 256, -128),
        }]


def test_validate_tflite_model_accepts_firmware_contract():
    model_validation.validate_tflite_model(
        VALID_PREFIX,
        interpreter_factory=lambda **kwargs: FakeInterpreter(),
    )


@pytest.mark.parametrize("model_bytes", [b"", b"12345678", b"\x00\x00\x00\x00NOPE"])
def test_validate_tflite_model_rejects_invalid_identifier(model_bytes):
    with pytest.raises(ValueError, match="TFLite|identifier|empty"):
        model_validation.validate_tflite_model(
            model_bytes,
            interpreter_factory=lambda **kwargs: FakeInterpreter(),
        )


@pytest.mark.parametrize(
    ("float_accuracy", "quantized_accuracy"),
    [(0.89, 0.95), (0.95, 0.89), (0.96, 0.90), (float("nan"), 0.95)],
)
def test_quality_gate_rejects_unacceptable_models(float_accuracy, quantized_accuracy):
    with pytest.raises(RuntimeError, match="accuracy|finite|drop"):
        model_validation.enforce_quality_gates(float_accuracy, quantized_accuracy)


def test_quality_gate_accepts_thresholds():
    model_validation.enforce_quality_gates(0.95, 0.90)


def test_header_export_validates_before_expanding(tmp_path, monkeypatch):
    model_path = tmp_path / "model.tflite"
    model_path.write_bytes(VALID_PREFIX)
    called = []

    def validate(model_bytes):
        called.append(model_bytes)

    monkeypatch.setattr(export_model_header, "validate_tflite_model", validate)
    content = export_model_header.generate(str(model_path))

    assert called == [VALID_PREFIX]
    assert "g_model" in content
