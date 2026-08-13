"""Generate firmware/src/charset.h from charset.py.

The class order must be identical on both sides: this is the only
generator for that header, so the firmware and the training pipeline
never drift apart by hand-editing.
"""

from __future__ import annotations

from charset import CHARSET

OUTPUT_PATH = "../firmware/src/charset.h"


def escape_char(char: str) -> str:
    if char == "'":
        return "'\\''"
    if char == "\\":
        return "'\\\\'"
    return f"'{char}'"


def generate() -> str:
    entries = ", ".join(escape_char(char) for char in CHARSET)
    return (
        "// Generated from ml/charset.py by ml/export_charset.py.\n"
        "// Do not hand-edit: the class order must match training exactly.\n\n"
        "#pragma once\n\n"
        f"static const char CHARSET[] = {{{entries}}};\n"
        "static const int CHARSET_SIZE = sizeof(CHARSET) / sizeof(CHARSET[0]);\n"
    )


if __name__ == "__main__":
    content = generate()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"wrote {OUTPUT_PATH}")
