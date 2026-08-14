"""Deterministic group-disjoint splits for character samples."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import chars_dataset
import dataset_io
from charset import CHARSET, CHAR_TO_INDEX


@dataclass(frozen=True)
class Sample:
    path: Path
    char: str
    class_index: int
    split: str
    source: str = ""


def _split_bucket(group: str) -> int:
    digest = hashlib.sha256(group.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100


def split_for_entry(entry: dict) -> str:
    """Return a stable split shared by every sample from one source group."""
    source = entry.get("source")
    if source == "real":
        source_image = entry.get("source_image")
        if not isinstance(source_image, str):
            raise ValueError("real sample is missing source_image")
        if dataset_io.TRACK_IMAGE_NAME_RE.fullmatch(source_image) is None:
            raise ValueError(f"unexpected real source image filename: {source_image!r}")
        bucket = _split_bucket(f"real:{source_image}")
        if bucket < 65:
            return "train"
        if bucket < 80:
            return "validation"
        if bucket < 90:
            return "calibration"
        return "evaluation"

    if source == "synthetic":
        font = entry.get("font")
        font_size = entry.get("font_size")
        if not isinstance(font, str) or not isinstance(font_size, int):
            raise ValueError("synthetic sample is missing font provenance")
        bucket = _split_bucket(f"synthetic:{font}:{font_size}")
        return "validation" if bucket < 20 else "train"

    raise ValueError(f"unknown sample source: {source!r}")


def load_samples() -> list[Sample]:
    """Load and validate every character label and image."""
    labels = chars_dataset.load_labels()
    if not labels:
        raise RuntimeError(
            "no samples in ml/dataset/chars/labels.jsonl; run prepare_chars.py "
            "and/or synth.py first"
        )

    samples = []
    seen_paths = set()
    content_splits = {}
    for line_number, entry in enumerate(labels, start=1):
        char = entry.get("char")
        if char not in CHAR_TO_INDEX:
            raise RuntimeError(f"invalid character label on line {line_number}: {char!r}")
        try:
            image_path = dataset_io.resolve_character_image(
                chars_dataset.IMAGES_DIR, entry.get("image")
            )
            loaded_image = dataset_io.load_character_image(image_path)
            split = split_for_entry(entry)
        except (OSError, ValueError) as error:
            raise RuntimeError(f"invalid character sample on line {line_number}: {error}") from error
        if image_path in seen_paths:
            raise RuntimeError(f"duplicate character image on line {line_number}: {image_path.name}")
        seen_paths.add(image_path)
        content_hash = hashlib.sha256()
        content_hash.update(loaded_image.mode.encode("ascii"))
        content_hash.update(bytes(loaded_image.size))
        content_hash.update(loaded_image.tobytes())
        content_digest = content_hash.digest()
        previous_split = content_splits.get(content_digest)
        if previous_split is not None and previous_split != split:
            raise RuntimeError(
                f"duplicate image content crosses {previous_split} and {split} splits"
            )
        content_splits[content_digest] = split
        samples.append(Sample(image_path, char, CHAR_TO_INDEX[char], split, entry["source"]))
    return samples


def require_class_coverage(samples: Iterable[Sample], split: str) -> None:
    """Raise when `split` lacks any model output class."""
    present = {sample.char for sample in samples if sample.split == split}
    missing = [char for char in CHARSET if char not in present]
    if missing:
        formatted = ", ".join(repr(char) for char in missing)
        raise RuntimeError(f"{split} split is missing character classes: {formatted}")
