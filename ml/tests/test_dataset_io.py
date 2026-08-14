from pathlib import Path
import json

import pytest
from PIL import Image

import dataset_io


def save_image(path: Path, size: tuple[int, int] = (24, 24), image_format: str = "PNG") -> None:
    Image.new("L", size, color=0).save(path, format=image_format)


@pytest.mark.parametrize(
    "name",
    [
        "deck1_123.jpg",
        "deck_1_123_012345abcdef.jpg",
    ],
)
def test_resolve_track_image_accepts_expected_names(tmp_path, name):
    path = tmp_path / name
    save_image(path, image_format="JPEG")

    assert dataset_io.resolve_track_image(tmp_path, name) == path.resolve()


@pytest.mark.parametrize(
    "name",
    [
        "../deck1_123.jpg",
        "sub/deck1_123.jpg",
        "sub\\deck1_123.jpg",
        "/tmp/deck1_123.jpg",
        "C:\\Temp\\deck1_123.jpg",
        "deck1_123.png",
        "deck1_123_ABCDEF012345.jpg",
    ],
)
def test_resolve_track_image_rejects_unexpected_names(tmp_path, name):
    with pytest.raises(ValueError, match="filename"):
        dataset_io.resolve_track_image(tmp_path, name)


def test_resolve_track_image_rejects_symlink(tmp_path):
    outside = tmp_path.parent / "deck1_123.jpg"
    save_image(outside, image_format="JPEG")
    link = tmp_path / "deck1_123.jpg"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="symlink"):
        dataset_io.resolve_track_image(tmp_path, link.name)


def test_load_bounded_image_checks_bytes_before_open(tmp_path, monkeypatch):
    path = tmp_path / "deck1_123.jpg"
    path.write_bytes(b"x" * 11)

    def fail_open(*args, **kwargs):
        raise AssertionError("oversized image was opened")

    monkeypatch.setattr(dataset_io.Image, "open", fail_open)
    with pytest.raises(ValueError, match="byte limit"):
        dataset_io.load_bounded_image(
            path,
            max_bytes=10,
            max_pixels=100,
            max_dimension=10,
            expected_format="JPEG",
        )


def test_load_bounded_image_checks_pixels_before_decode(tmp_path):
    path = tmp_path / "deck1_123.jpg"
    save_image(path, size=(20, 20), image_format="JPEG")

    with pytest.raises(ValueError, match="pixel limit"):
        dataset_io.load_bounded_image(
            path,
            max_bytes=10_000,
            max_pixels=100,
            max_dimension=100,
            expected_format="JPEG",
        )


def test_resolve_character_image_requires_uuid_png(tmp_path):
    name = "0123456789abcdef0123456789abcdef.png"
    path = tmp_path / name
    save_image(path)

    assert dataset_io.resolve_character_image(tmp_path, name) == path.resolve()
    with pytest.raises(ValueError, match="filename"):
        dataset_io.resolve_character_image(tmp_path, "sample.png")


def test_load_character_image_requires_patch_dimensions(tmp_path):
    path = tmp_path / "0123456789abcdef0123456789abcdef.png"
    save_image(path, size=(25, 24))

    with pytest.raises(ValueError, match="24x24"):
        dataset_io.load_character_image(path)


def test_load_character_image_requires_grayscale(tmp_path):
    path = tmp_path / "0123456789abcdef0123456789abcdef.png"
    Image.new("RGB", (24, 24), color=(0, 0, 0)).save(path)

    with pytest.raises(ValueError, match="grayscale"):
        dataset_io.load_character_image(path)


def test_load_bounded_jsonl_rejects_record_limit(tmp_path):
    path = tmp_path / "labels.jsonl"
    path.write_text("\n".join(json.dumps({"value": i}) for i in range(3)), encoding="utf-8")

    with pytest.raises(ValueError, match="record limit"):
        dataset_io.load_bounded_jsonl(
            path,
            max_bytes=1000,
            max_line_bytes=100,
            max_records=2,
        )


def test_blank_lines_do_not_hide_records_after_limit(tmp_path):
    path = tmp_path / "labels.jsonl"
    records = "\n".join(json.dumps({"value": i}) for i in range(3))
    path.write_text("\n\n\n" + records, encoding="utf-8")

    with pytest.raises(ValueError, match="record limit"):
        dataset_io.load_bounded_jsonl(
            path,
            max_bytes=1000,
            max_line_bytes=100,
            max_records=2,
        )


def test_load_bounded_jsonl_rejects_symlink(tmp_path):
    target = tmp_path / "target.jsonl"
    target.write_text(json.dumps({"value": 1}), encoding="utf-8")
    link = tmp_path / "labels.jsonl"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="symlink"):
        dataset_io.load_bounded_jsonl(link)


def test_load_bounded_jsonl_rejects_broken_symlink(tmp_path):
    link = tmp_path / "labels.jsonl"
    try:
        link.symlink_to(tmp_path / "missing.jsonl")
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="symlink"):
        dataset_io.load_bounded_jsonl(link)
