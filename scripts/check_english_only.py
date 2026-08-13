#!/usr/bin/env python3
"""Warn on non-English-looking text in comments and prose.

AGENTS.md style rule: write code, comments, commit messages, and
documentation in English; non-English text is allowed only inside
string literals or data where the domain requires it. This is a
warning-only check: it always exits 0, per the policy's own stated
scope for this script.

Detecting "not English" precisely requires language identification,
which is out of scope for a dependency-free script (AGENTS.md rule 9
bars adding a new dependency for this). As a heuristic proxy, this
flags lines containing characters outside the Latin-adjacent script
ranges normally used to write English (CJK, Cyrillic, Arabic, Hebrew,
Hangul, Thai, Devanagari), skipping string-literal-shaped content
(quoted spans) since that is exactly what the policy exempts.
"""

from __future__ import annotations

import re
import subprocess
import sys

SELF_PATH_SUFFIX = "check_english_only.py"

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".exe", ".dll",
}

# Data/localization files are exempt outright: their entire purpose is
# non-English content.
DATA_FILE_EXTENSIONS = {".po", ".mo", ".json", ".csv"}

NON_LATIN_SCRIPT_RE = re.compile(
    "["
    "\u4e00-\u9fff"  # CJK unified ideographs
    "\u3040-\u30ff"  # hiragana / katakana
    "\uac00-\ud7a3"  # hangul syllables
    "\u0400-\u04ff"  # cyrillic
    "\u0600-\u06ff"  # arabic
    "\u0590-\u05ff"  # hebrew
    "\u0e00-\u0e7f"  # thai
    "\u0900-\u097f"  # devanagari
    "]"
)

QUOTED_SPAN_RE = re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`")


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tracked_files() -> list[str]:
    output = run_git(["ls-files"])
    return [line for line in output.splitlines() if line]


def is_skipped(path: str) -> bool:
    lower = path.lower()
    if any(lower.endswith(ext) for ext in BINARY_EXTENSIONS):
        return True
    if any(lower.endswith(ext) for ext in DATA_FILE_EXTENSIONS):
        return True
    return False


def scan_file(path: str) -> list[str]:
    warnings = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError:
        return warnings

    for lineno, line in enumerate(lines, start=1):
        outside_literals = QUOTED_SPAN_RE.sub("", line)
        if NON_LATIN_SCRIPT_RE.search(outside_literals):
            warnings.append(f"{path}:{lineno}: non-English-looking text outside a literal: {line.strip()[:120]}")
    return warnings


def main() -> int:
    warnings = []
    for path in tracked_files():
        if path.endswith(SELF_PATH_SUFFIX) or is_skipped(path):
            continue
        warnings.extend(scan_file(path))

    if warnings:
        print("English-only check (warning only):")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("English-only check passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
