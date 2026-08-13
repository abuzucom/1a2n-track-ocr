"""Train the on-device character classifier.

Loads every sample from ml/dataset/chars/ (real, from prepare_chars.py,
and synthetic, from synth.py), trains a small CNN, and saves a Keras
model to ml/model_output/. Run prepare_chars.py and synth.py first.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter

import numpy as np
import tensorflow as tf
from PIL import Image

import chars_dataset
from charset import CHARSET, CHAR_TO_INDEX, PATCH_SIZE

MODEL_OUTPUT_DIR = "model_output"
VALIDATION_SPLIT = 0.2
EPOCHS = 20
BATCH_SIZE = 32


def load_dataset() -> tuple[np.ndarray, np.ndarray, Counter]:
    labels = chars_dataset.load_labels()
    if not labels:
        raise RuntimeError(
            "no samples in ml/dataset/chars/labels.jsonl; run prepare_chars.py "
            "and/or synth.py first"
        )

    images = []
    class_indices = []
    source_counts: Counter = Counter()

    for entry in labels:
        char = entry["char"]
        if char not in CHAR_TO_INDEX:
            continue
        image_path = chars_dataset.IMAGES_DIR / entry["image"]
        if not image_path.is_file():
            continue
        patch = Image.open(image_path).convert("L")
        images.append(np.array(patch, dtype=np.float32) / 255.0)
        class_indices.append(CHAR_TO_INDEX[char])
        source_counts[(char, entry["source"])] += 1

    x = np.array(images).reshape((-1, PATCH_SIZE, PATCH_SIZE, 1))
    y = np.array(class_indices, dtype=np.int32)
    return x, y, source_counts


def log_class_balance(source_counts: Counter) -> None:
    per_char: dict[str, Counter] = {}
    for (char, source), count in source_counts.items():
        per_char.setdefault(char, Counter())[source] = count

    for char in CHARSET:
        counts = per_char.get(char)
        if counts is None:
            print(f"  class {char!r}: 0 samples")
            continue
        real = counts.get("real", 0)
        synthetic = counts.get("synthetic", 0)
        print(f"  class {char!r}: {real} real, {synthetic} synthetic")


def build_model(num_classes: int) -> tf.keras.Model:
    return tf.keras.Sequential([
        tf.keras.layers.Input(shape=(PATCH_SIZE, PATCH_SIZE, 1)),
        tf.keras.layers.Conv2D(8, 3, activation="relu", padding="same"),
        tf.keras.layers.MaxPooling2D(2),
        tf.keras.layers.Conv2D(16, 3, activation="relu", padding="same"),
        tf.keras.layers.MaxPooling2D(2),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dense(num_classes, activation="softmax"),
    ])


def run(epochs: int) -> None:
    print("loading dataset...")
    x, y, source_counts = load_dataset()
    print(f"loaded {len(x)} samples across {len(CHARSET)} classes")
    log_class_balance(source_counts)

    model = build_model(len(CHARSET))
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    model.summary()

    model.fit(
        x, y,
        validation_split=VALIDATION_SPLIT,
        epochs=epochs,
        batch_size=BATCH_SIZE,
    )

    os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
    model.save(f"{MODEL_OUTPUT_DIR}/ocr_model.keras")
    print(f"saved model to {MODEL_OUTPUT_DIR}/ocr_model.keras")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    args = parser.parse_args()
    run(args.epochs)
