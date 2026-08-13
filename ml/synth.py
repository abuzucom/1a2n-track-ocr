"""Synthetic per-character renders using Coda.

Supplements real captures for classes underrepresented in normal
operation (e.g. "%", "&", digits). Not a replacement for real data:
these renders carry no camera lighting, angle, or lens distortion.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import chars_dataset
from charset import CHARSET, PATCH_SIZE

FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILES = ["Coda-Regular.ttf", "Coda-ExtraBold.ttf"]
FONT_SIZES = [14, 18, 22]


def render_char(char: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    canvas = Image.new("L", (PATCH_SIZE, PATCH_SIZE), color=0)
    if char == " ":
        return canvas

    draw = ImageDraw.Draw(canvas)
    left, top, right, bottom = draw.textbbox((0, 0), char, font=font)
    width = right - left
    height = bottom - top
    x = (PATCH_SIZE - width) // 2 - left
    y = (PATCH_SIZE - height) // 2 - top
    draw.text((x, y), char, fill=255, font=font)
    return canvas


def generate() -> int:
    chars_dataset.init_dirs()
    count = 0
    entries = []
    for font_name in FONT_FILES:
        font_path = FONT_DIR / font_name
        if not font_path.is_file():
            print(f"missing font file: {font_path}, skipping")
            continue
        for font_size in FONT_SIZES:
            font = ImageFont.truetype(str(font_path), font_size)
            for char in CHARSET:
                image = render_char(char, font)
                entry = chars_dataset.save_char(
                    image, char, source="synthetic", font=font_name, font_size=font_size
                )
                entries.append(entry)
                count += 1
    chars_dataset.save_labels(entries)
    return count


if __name__ == "__main__":
    total = generate()
    print(f"generated {total} synthetic character samples")
