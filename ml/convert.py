"""Quantize the trained Keras model to int8 TFLite for TFLite-Micro.

Uses real (not synthetic) character crops as the representative dataset
for post-training quantization, then compares quantized vs. float
accuracy on the same held-out samples: a large drop means the
architecture or representative set needs revisiting before Phase 5,
not something to defer.
"""

from __future__ import annotations

import argparse
import os
import random

import numpy as np
import tensorflow as tf
from PIL import Image

import chars_dataset
from charset import CHAR_TO_INDEX, PATCH_SIZE

MODEL_INPUT_PATH = "model_output/ocr_model.keras"
TFLITE_OUTPUT_PATH = "../firmware/models/ocr_model.tflite"
REPRESENTATIVE_SAMPLE_SIZE = 200


def load_real_samples() -> list[tuple[np.ndarray, int]]:
    labels = [entry for entry in chars_dataset.load_labels() if entry["source"] == "real"]
    random.shuffle(labels)

    samples = []
    for entry in labels:
        char = entry["char"]
        if char not in CHAR_TO_INDEX:
            continue
        image_path = chars_dataset.IMAGES_DIR / entry["image"]
        if not image_path.is_file():
            continue
        patch = Image.open(image_path).convert("L")
        array = np.array(patch, dtype=np.float32) / 255.0
        samples.append((array.reshape((PATCH_SIZE, PATCH_SIZE, 1)), CHAR_TO_INDEX[char]))
    return samples


def representative_dataset_gen(samples: list[tuple[np.ndarray, int]]):
    for array, _label in samples[:REPRESENTATIVE_SAMPLE_SIZE]:
        yield [array.reshape(1, PATCH_SIZE, PATCH_SIZE, 1)]


def evaluate_float(model: tf.keras.Model, samples: list[tuple[np.ndarray, int]]) -> float:
    x = np.array([array for array, _label in samples])
    y = np.array([label for _array, label in samples])
    _loss, accuracy = model.evaluate(x, y, verbose=0)
    return accuracy


def evaluate_tflite(tflite_model: bytes, samples: list[tuple[np.ndarray, int]]) -> float:
    interpreter = tf.lite.Interpreter(model_content=tflite_model)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]

    scale, zero_point = input_detail["quantization"]
    correct = 0
    for array, label in samples:
        quantized = array / scale + zero_point if scale else array
        quantized = quantized.astype(input_detail["dtype"])
        interpreter.set_tensor(input_detail["index"], quantized.reshape(1, PATCH_SIZE, PATCH_SIZE, 1))
        interpreter.invoke()
        prediction = interpreter.get_tensor(output_detail["index"])
        if int(np.argmax(prediction)) == label:
            correct += 1
    return correct / len(samples) if samples else 0.0


def run() -> None:
    model = tf.keras.models.load_model(MODEL_INPUT_PATH)
    samples = load_real_samples()
    if not samples:
        raise RuntimeError(
            "no real character samples available for the representative "
            "dataset; run prepare_chars.py against real captures first"
        )

    float_accuracy = evaluate_float(model, samples)
    print(f"float model accuracy on real samples: {float_accuracy:.3f}")

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: representative_dataset_gen(samples)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite_model = converter.convert()

    quantized_accuracy = evaluate_tflite(tflite_model, samples)
    print(f"quantized model accuracy on real samples: {quantized_accuracy:.3f}")

    drop = float_accuracy - quantized_accuracy
    if drop > 0.05:
        print(
            f"WARNING: quantization dropped accuracy by {drop:.3f}, "
            "review the representative dataset or architecture before Phase 5"
        )

    os.makedirs(os.path.dirname(TFLITE_OUTPUT_PATH), exist_ok=True)
    with open(TFLITE_OUTPUT_PATH, "wb") as handle:
        handle.write(tflite_model)
    size_kb = len(tflite_model) / 1024
    print(f"wrote {TFLITE_OUTPUT_PATH} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
