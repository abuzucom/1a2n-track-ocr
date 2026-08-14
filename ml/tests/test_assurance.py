from pathlib import Path

import pytest
from PIL import Image

import dataset_splits
import prepare_chars
from charset import CHARSET


def test_align_box_labels_requires_exact_expected_text():
    assert prepare_chars.align_box_labels("A B", ["A", "B"]) == ["A", "B"]

    with pytest.raises(ValueError, match="does not match"):
        prepare_chars.align_box_labels("A B", ["A", "C"])
    with pytest.raises(ValueError, match="does not match"):
        prepare_chars.align_box_labels("A B", ["A"])


def test_tesseract_calls_have_timeouts(monkeypatch):
    seen = []

    def fake_data(image, output_type, timeout):
        seen.append(("data", timeout))
        return {"conf": ["90"]}

    def fake_boxes(image, output_type, timeout):
        seen.append(("boxes", timeout))
        return {
            "char": ["A"],
            "left": [0],
            "right": [10],
            "top": [20],
            "bottom": [5],
        }

    monkeypatch.setattr(prepare_chars.pytesseract, "image_to_data", fake_data)
    monkeypatch.setattr(prepare_chars.pytesseract, "image_to_boxes", fake_boxes)
    image = Image.new("L", (10, 10), color=0)
    prepare_chars.extract_chars_from_image(image, "A")

    assert seen == [
        ("data", prepare_chars.TESSERACT_TIMEOUT_SECONDS),
        ("boxes", prepare_chars.TESSERACT_TIMEOUT_SECONDS),
    ]


def test_tesseract_timeout_names_the_image(tmp_path, monkeypatch):
    path = tmp_path / "deck1_123.jpg"
    Image.new("L", (10, 10), color=0).save(path, format="JPEG")

    def time_out(*args, **kwargs):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(prepare_chars.pytesseract, "image_to_data", time_out)
    with pytest.raises(RuntimeError, match="deck1_123.jpg"):
        prepare_chars.extract_chars(path, 1, expected_text="A")


def test_source_group_has_one_stable_split():
    first = {"source": "real", "source_image": "deck1_123_012345abcdef.jpg", "char": "A"}
    second = {"source": "real", "source_image": first["source_image"], "char": "B"}

    assert dataset_splits.split_for_entry(first) == dataset_splits.split_for_entry(second)


def test_synthetic_samples_never_enter_evaluation_splits():
    for font_size in range(10, 40):
        entry = {
            "source": "synthetic",
            "font": "Coda-Regular.ttf",
            "font_size": font_size,
        }
        assert dataset_splits.split_for_entry(entry) in {"train", "validation"}


def test_missing_training_class_is_an_error():
    samples = [dataset_splits.Sample(Path("a.png"), char, 0, "train") for char in CHARSET[:-1]]

    with pytest.raises(RuntimeError, match=repr(CHARSET[-1])):
        dataset_splits.require_class_coverage(samples, "train")


def test_duplicate_character_image_is_rejected(tmp_path, monkeypatch):
    image_name = "0123456789abcdef0123456789abcdef.png"
    Image.new("L", (24, 24), color=0).save(tmp_path / image_name)
    labels = [
        {
            "image": image_name,
            "char": "A",
            "source": "real",
            "source_image": "deck1_100_012345abcdef.jpg",
        },
        {
            "image": image_name,
            "char": "A",
            "source": "real",
            "source_image": "deck1_200_012345abcdef.jpg",
        },
    ]
    monkeypatch.setattr(dataset_splits.chars_dataset, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(dataset_splits.chars_dataset, "load_labels", lambda: labels)

    with pytest.raises(RuntimeError, match="duplicate character image"):
        dataset_splits.load_samples()


def test_duplicate_content_cannot_cross_splits(tmp_path, monkeypatch):
    entries_by_split = {}
    for index in range(1000):
        entry = {
            "source": "real",
            "source_image": f"deck1_{index}_012345abcdef.jpg",
        }
        entries_by_split.setdefault(dataset_splits.split_for_entry(entry), entry)
        if len(entries_by_split) > 1:
            break
    first, second = list(entries_by_split.values())[:2]
    first_name = "0123456789abcdef0123456789abcdef.png"
    second_name = "fedcba9876543210fedcba9876543210.png"
    Image.new("L", (24, 24), color=0).save(tmp_path / first_name)
    (tmp_path / second_name).write_bytes((tmp_path / first_name).read_bytes())
    labels = [
        {**first, "image": first_name, "char": "A"},
        {**second, "image": second_name, "char": "A"},
    ]
    monkeypatch.setattr(dataset_splits.chars_dataset, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(dataset_splits.chars_dataset, "load_labels", lambda: labels)

    with pytest.raises(RuntimeError, match="duplicate image content crosses"):
        dataset_splits.load_samples()


def test_decoded_duplicate_content_cannot_cross_splits(tmp_path, monkeypatch):
    entries_by_split = {}
    for index in range(1000):
        entry = {
            "source": "real",
            "source_image": f"deck1_{index}_012345abcdef.jpg",
        }
        entries_by_split.setdefault(dataset_splits.split_for_entry(entry), entry)
        if len(entries_by_split) > 1:
            break
    first, second = list(entries_by_split.values())[:2]
    first_name = "0123456789abcdef0123456789abcdef.png"
    second_name = "fedcba9876543210fedcba9876543210.png"
    image = Image.new("L", (24, 24), color=0)
    image.save(tmp_path / first_name, compress_level=0)
    image.save(tmp_path / second_name, compress_level=9)
    assert (tmp_path / first_name).read_bytes() != (tmp_path / second_name).read_bytes()
    labels = [
        {**first, "image": first_name, "char": "A"},
        {**second, "image": second_name, "char": "A"},
    ]
    monkeypatch.setattr(dataset_splits.chars_dataset, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(dataset_splits.chars_dataset, "load_labels", lambda: labels)

    with pytest.raises(RuntimeError, match="duplicate image content crosses"):
        dataset_splits.load_samples()
