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

import dataset_splits
from charset import CHARSET, PATCH_SIZE

MODEL_OUTPUT_DIR = "model_output"
VALIDATION_SPLIT = 0.2
EPOCHS = 20
BATCH_SIZE = 32


def build_dataset(samples: list[dataset_splits.Sample]) -> tf.data.Dataset:
    """Build a TensorFlow dataset from validated sample metadata."""
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


def load_dataset() -> tuple[tf.data.Dataset, Counter, int]:
    """Return all validated samples for existing callers."""
    samples = dataset_splits.load_samples()
    source_counts = Counter((sample.char, sample.source) for sample in samples)
    return build_dataset(samples), source_counts, len(samples)


def load_datasets() -> tuple[tf.data.Dataset, tf.data.Dataset, Counter, int]:
    """Return disjoint training and validation datasets."""
    samples = dataset_splits.load_samples()
    dataset_splits.require_class_coverage(samples, "train")
    train_samples = [sample for sample in samples if sample.split == "train"]
    validation_samples = [sample for sample in samples if sample.split == "validation"]
    if not validation_samples:
        raise RuntimeError("validation split has no samples")

    source_counts = Counter((sample.char, sample.source) for sample in samples)
    train_dataset = build_dataset(train_samples)
    validation_dataset = build_dataset(validation_samples)
    return train_dataset, validation_dataset, source_counts, len(train_samples)


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
    train_dataset, validation_dataset, source_counts, training_samples = load_datasets()
    print(f"loaded {training_samples} training samples across {len(CHARSET)} classes")
    log_class_balance(source_counts)

    model = build_model(len(CHARSET))
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    model.summary()

    train_ds = train_dataset.shuffle(
        buffer_size=training_samples,
        reshuffle_each_iteration=True,
    ).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
    val_ds = validation_dataset.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)

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
