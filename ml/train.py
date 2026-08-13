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


def load_dataset() -> tuple[tf.data.Dataset, Counter, int]:
    labels = chars_dataset.load_labels()
    if not labels:
        raise RuntimeError(
            "no samples in ml/dataset/chars/labels.jsonl; run prepare_chars.py "
            "and/or synth.py first"
        )

    paths = []
    class_indices = []
    source_counts: Counter = Counter()

    for entry in labels:
        char = entry["char"]
        if char not in CHAR_TO_INDEX:
            continue
        image_path = chars_dataset.IMAGES_DIR / entry["image"]
        if not image_path.is_file():
            continue
        paths.append(str(image_path))
        class_indices.append(CHAR_TO_INDEX[char])
        source_counts[(char, entry["source"])] += 1

    paths = np.array(paths)
    class_indices = np.array(class_indices, dtype=np.int32)

    dataset = tf.data.Dataset.from_tensor_slices((paths, class_indices))

    def load_image(path, label):
        image = tf.io.read_file(path)
        image = tf.image.decode_png(image, channels=1)
        image = tf.cast(image, tf.float32) / 255.0
        return image, label

    dataset = dataset.map(load_image, num_parallel_calls=tf.data.AUTOTUNE)
    return dataset, source_counts, len(paths)


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
    dataset, source_counts, total_samples = load_dataset()
    print(f"loaded {total_samples} samples across {len(CHARSET)} classes")
    log_class_balance(source_counts)

    model = build_model(len(CHARSET))
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    model.summary()

    dataset = dataset.shuffle(buffer_size=total_samples, reshuffle_each_iteration=False)
    
    val_size = int(total_samples * VALIDATION_SPLIT)
    
    val_ds = dataset.take(val_size).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
    train_ds = dataset.skip(val_size).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)

    model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs,
    )

    os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
    model.save(f"{MODEL_OUTPUT_DIR}/ocr_model.keras")
    print(f"saved model to {MODEL_OUTPUT_DIR}/ocr_model.keras")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    args = parser.parse_args()
    run(args.epochs)
