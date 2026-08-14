"""Validate image paths and bounds before the ML pipeline decodes them."""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

from charset import PATCH_SIZE


TRACK_IMAGE_NAME_RE = re.compile(
    r"[A-Za-z0-9_-]{1,64}_[0-9]{1,20}(?:_[0-9a-f]{12})?\.jpg"
)
CHARACTER_IMAGE_NAME_RE = re.compile(r"[0-9a-f]{32}\.png")

TRACK_IMAGE_MAX_BYTES = 4 * 1024 * 1024
TRACK_IMAGE_MAX_PIXELS = 2_000_000
TRACK_IMAGE_MAX_DIMENSION = 4096
CHARACTER_IMAGE_MAX_BYTES = 64 * 1024
LABEL_FILE_MAX_BYTES = 256 * 1024 * 1024
LABEL_LINE_MAX_BYTES = 16 * 1024
LABEL_MAX_RECORDS = 200_000


def _resolve_image(images_dir: Path, image_name: object, pattern: re.Pattern[str]) -> Path:
    """Return a contained regular image with an expected flat filename."""
    if not isinstance(image_name, str) or pattern.fullmatch(image_name) is None:
        raise ValueError(f"unexpected dataset image filename: {image_name!r}")

    root = images_dir.resolve(strict=True)
    candidate = images_dir / image_name
    if candidate.is_symlink():
        raise ValueError(f"dataset image must not be a symlink: {image_name}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"dataset image does not exist: {image_name}") from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"dataset image escapes its directory: {image_name}")
    return resolved


def resolve_track_image(images_dir: Path, image_name: object) -> Path:
    """Return a validated whole-track JPEG path."""
    return _resolve_image(images_dir, image_name, TRACK_IMAGE_NAME_RE)


def resolve_character_image(images_dir: Path, image_name: object) -> Path:
    """Return a validated character PNG path."""
    return _resolve_image(images_dir, image_name, CHARACTER_IMAGE_NAME_RE)


def load_bounded_image(
    image_path: Path,
    *,
    max_bytes: int,
    max_pixels: int,
    max_dimension: int,
    expected_format: str,
    expected_size: tuple[int, int] | None = None,
) -> Image.Image:
    """Load an image after checking compressed and decoded size bounds."""
    file_size = image_path.stat().st_size
    if file_size > max_bytes:
        raise ValueError(f"image exceeds the {max_bytes} byte limit: {image_path.name}")

    with Image.open(image_path) as image:
        width, height = image.size
        if image.format != expected_format:
            raise ValueError(f"image is not {expected_format}: {image_path.name}")
        if expected_size is not None and image.size != expected_size:
            expected_width, expected_height = expected_size
            raise ValueError(
                f"image must be {expected_width}x{expected_height}: {image_path.name}"
            )
        if width > max_dimension or height > max_dimension:
            raise ValueError(f"image dimensions exceed the {max_dimension}px limit: {image_path.name}")
        if width * height > max_pixels:
            raise ValueError(f"image exceeds the {max_pixels} pixel limit: {image_path.name}")
        image.load()
        return image.copy()


def load_track_image(image_path: Path) -> Image.Image:
    """Load a bounded whole-track JPEG."""
    return load_bounded_image(
        image_path,
        max_bytes=TRACK_IMAGE_MAX_BYTES,
        max_pixels=TRACK_IMAGE_MAX_PIXELS,
        max_dimension=TRACK_IMAGE_MAX_DIMENSION,
        expected_format="JPEG",
    )


def load_character_image(image_path: Path) -> Image.Image:
    """Load a bounded character PNG with the model's exact dimensions."""
    image = load_bounded_image(
        image_path,
        max_bytes=CHARACTER_IMAGE_MAX_BYTES,
        max_pixels=PATCH_SIZE * PATCH_SIZE,
        max_dimension=PATCH_SIZE,
        expected_format="PNG",
        expected_size=(PATCH_SIZE, PATCH_SIZE),
    )
    if image.mode != "L":
        raise ValueError(f"character image must be grayscale: {image_path.name}")
    return image


def load_bounded_jsonl(
    path: Path,
    *,
    max_bytes: int = LABEL_FILE_MAX_BYTES,
    max_line_bytes: int = LABEL_LINE_MAX_BYTES,
    max_records: int = LABEL_MAX_RECORDS,
) -> list[dict]:
    """Load a JSONL manifest within file, line, and record limits."""
    if path.is_symlink():
        raise ValueError(f"label manifest must not be a symlink: {path}")
    if not path.exists():
        return []
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"label manifest does not exist: {path}") from error
    if not resolved.is_file():
        raise ValueError(f"label manifest is not a regular file: {path}")
    if resolved.stat().st_size > max_bytes:
        raise ValueError(f"label manifest exceeds the {max_bytes} byte limit: {path}")

    records = []
    with open(resolved, "rb") as handle:
        line_number = 0
        while True:
            line = handle.readline(max_line_bytes + 1)
            if not line:
                break
            line_number += 1
            if len(line) > max_line_bytes:
                raise ValueError(f"label line {line_number} exceeds the byte limit: {path}")
            if not line.strip():
                continue
            if len(records) >= max_records:
                raise ValueError(f"label manifest exceeds the {max_records} record limit: {path}")
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"invalid label JSON on line {line_number}: {path}") from error
            if not isinstance(record, dict):
                raise ValueError(f"label line {line_number} is not an object: {path}")
            records.append(record)
    return records
