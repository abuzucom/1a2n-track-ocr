"""Quantize the trained Keras model to int8 TFLite for TFLite-Micro.

Uses real (not synthetic) character crops as the representative dataset
for post-training quantization, then compares quantized vs. float
accuracy on a separate held-out real evaluation split: a large drop
means the architecture or representative set needs revisiting before
Phase 5, not something to defer.
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import tensorflow as tf

import dataset_splits
from charset import PATCH_SIZE
from model_validation import enforce_quality_gates, validate_tflite_model

MODEL_INPUT_PATH = "model_output/ocr_model.keras"
TFLITE_OUTPUT_PATH = "../firmware/models/ocr_model.tflite"
REPRESENTATIVE_SAMPLE_SIZE = 200


def build_dataset(samples: list[dataset_splits.Sample]) -> tf.data.Dataset:
    """Build a TensorFlow dataset from validated samples."""
    paths = np.array([str(sample.path) for sample in samples])
    class_indices = np.array([sample.class_index for sample in samples], dtype=np.int32)
    dataset = tf.data.Dataset.from_tensor_slices((paths, class_indices))

    def load_image(path, label):
        image = tf.io.read_file(path)
        image = tf.image.decode_png(image, channels=1)
        image = tf.cast(image, tf.float32) / 255.0
        return image, label

    dataset = dataset.map(load_image, num_parallel_calls=tf.data.AUTOTUNE)
    return dataset


def load_real_dataset(
    split: str | None = None,
    samples: list[dataset_splits.Sample] | None = None,
) -> tuple[tf.data.Dataset, int]:
    """Return real samples, optionally limited to one deterministic split."""
    if samples is None:
        samples = dataset_splits.load_samples()
    selected = [
        sample
        for sample in samples
        if sample.source == "real" and (split is None or sample.split == split)
    ]
    if split == "evaluation":
        dataset_splits.require_class_coverage(selected, split)
    return build_dataset(selected), len(selected)


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
    samples = dataset_splits.load_samples()
    calibration_dataset, calibration_count = load_real_dataset("calibration", samples)
    evaluation_dataset, evaluation_count = load_real_dataset("evaluation", samples)
    if calibration_count == 0 or evaluation_count == 0:
        raise RuntimeError(
            "real calibration and evaluation splits must both contain samples; "
            "collect more reviewed captures"
        )

    float_accuracy = evaluate_float(model, evaluation_dataset)
    print(f"float model accuracy on real samples: {float_accuracy:.3f}")

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    # Wrap the generator in a no-arg callable as expected by TFLiteConverter
    converter.representative_dataset = lambda: representative_dataset_gen(calibration_dataset)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite_model = converter.convert()
    validate_tflite_model(tflite_model)

    quantized_accuracy = evaluate_tflite(
        tflite_model,
        evaluation_dataset,
        evaluation_count,
    )
    print(f"quantized model accuracy on real samples: {quantized_accuracy:.3f}")
    enforce_quality_gates(float_accuracy, quantized_accuracy)

    os.makedirs(os.path.dirname(TFLITE_OUTPUT_PATH), exist_ok=True)
    with open(TFLITE_OUTPUT_PATH, "wb") as handle:
        handle.write(tflite_model)
    size_kb = len(tflite_model) / 1024
    print(f"wrote {TFLITE_OUTPUT_PATH} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
