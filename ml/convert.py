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


def load_real_dataset() -> tuple[tf.data.Dataset, int]:
    labels = [entry for entry in chars_dataset.load_labels() if entry["source"] == "real"]
    random.shuffle(labels)

    paths = []
    class_indices = []
    for entry in labels:
        char = entry["char"]
        if char not in CHAR_TO_INDEX:
            continue
        image_path = chars_dataset.IMAGES_DIR / entry["image"]
        if not image_path.is_file():
            continue
        paths.append(str(image_path))
        class_indices.append(CHAR_TO_INDEX[char])
        
    paths = np.array(paths)
    class_indices = np.array(class_indices, dtype=np.int32)
    
    dataset = tf.data.Dataset.from_tensor_slices((paths, class_indices))

    def load_image(path, label):
        image = tf.io.read_file(path)
        image = tf.image.decode_png(image, channels=1)
        image = tf.cast(image, tf.float32) / 255.0
        return image, label

    dataset = dataset.map(load_image, num_parallel_calls=tf.data.AUTOTUNE)
    return dataset, len(paths)


def representative_dataset_gen(dataset: tf.data.Dataset):
    for array, _label in dataset.take(REPRESENTATIVE_SAMPLE_SIZE):
        yield [tf.reshape(array, [1, PATCH_SIZE, PATCH_SIZE, 1])]


def evaluate_float(model: tf.keras.Model, dataset: tf.data.Dataset) -> float:
    batched = dataset.batch(32)
    _loss, accuracy = model.evaluate(batched, verbose=0)
    return accuracy


def evaluate_tflite(tflite_model: bytes, dataset: tf.data.Dataset, count: int) -> float:
    if count == 0:
        return 0.0
        
    interpreter = tf.lite.Interpreter(model_content=tflite_model)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]

    scale, zero_point = input_detail["quantization"]
    correct = 0
    for array, label in dataset:
        array = array.numpy()
        label = label.numpy()
        quantized = array / scale + zero_point if scale else array
        quantized = quantized.astype(input_detail["dtype"])
        interpreter.set_tensor(input_detail["index"], quantized.reshape(1, PATCH_SIZE, PATCH_SIZE, 1))
        interpreter.invoke()
        prediction = interpreter.get_tensor(output_detail["index"])
        if int(np.argmax(prediction)) == label:
            correct += 1
    return correct / count


def run() -> None:
    model = tf.keras.models.load_model(MODEL_INPUT_PATH)
    dataset, count = load_real_dataset()
    if count == 0:
        raise RuntimeError(
            "no real character samples available for the representative "
            "dataset; run prepare_chars.py against real captures first"
        )

    float_accuracy = evaluate_float(model, dataset)
    print(f"float model accuracy on real samples: {float_accuracy:.3f}")

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: representative_dataset_gen(dataset)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite_model = converter.convert()

    quantized_accuracy = evaluate_tflite(tflite_model, dataset, count)
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
