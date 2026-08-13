#!/usr/bin/env python3
"""Block em/en dash characters and their ASCII substitutes.

AGENTS.md style rule: never use the em/en dash character, and never
substitute "--", "---", or a spaced hyphen (" - ") for one.

This script reliably detects the unambiguous cases: the literal
U+2014/U+2013 characters and "--"/"---" sequences. It does not attempt
to flag a spaced single hyphen (" - "), because that construct is also
legitimate for numeric ranges ("9 - 5") and other non-dash uses; a
mechanical check there would produce too many false positives to be
useful. It also does not attempt to detect run-on sentences, which is
not mechanically checkable. Both gaps are called out here rather than
silently claimed as covered, per AGENTS.md rule 13.
"""

from __future__ import annotations

import re
import subprocess
import sys

SELF_PATH_SUFFIX = "lint_style.py"

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".exe", ".dll",
}

# Third-party license text must be preserved verbatim, not edited to fit
# this repo's style rules.
LICENSE_FILENAMES = {
    "license", "license.txt", "license.md",
    "copying", "copying.txt",
    "notice", "notice.txt",
    "ofl.txt",
}

EM_DASH = "\u2014"
EN_DASH = "\u2013"

# Unicode dash characters are always a violation; there is no legitimate use.
UNICODE_DASH_RE = re.compile(f"[{EM_DASH}{EN_DASH}]")

# A run of exactly 2 or 3 ASCII hyphens, not part of a longer run (so
# "-----BEGIN ... KEY-----" markers are left alone).
ASCII_DASH_RUN_RE = re.compile(r"(?<!-)-{2,3}(?!-)")

# "--flag" or "---flag" immediately after start/whitespace/quote is a CLI
# flag (e.g. "--base", '"--head"'), which AGENTS.md exempts.
FLAG_PRECEDING_CHARS = " \t\"'[("

# Markdown table separator rows ("|---|---|") are structural syntax, not
# prose dashes.
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")

# Inline code spans (`...`) are how AGENTS.md itself cites the literal
# banned patterns ("--", "---") while documenting this very rule. Strip
# them before scanning so the rule's own text does not fail its own check.
INLINE_CODE_SPAN_RE = re.compile(r"`[^`]*`")


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tracked_files() -> list[str]:
    output = run_git(["ls-files"])
    return [line for line in output.splitlines() if line]


def is_binary_path(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in BINARY_EXTENSIONS)


def is_license_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return name in LICENSE_FILENAMES


def has_ascii_dash_violation(line: str) -> bool:
    for match in ASCII_DASH_RUN_RE.finditer(line):
        start, end = match.span()
        preceding = line[start - 1] if start > 0 else ""
        following = line[end] if end < len(line) else ""
        looks_like_flag = (start == 0 or preceding in FLAG_PRECEDING_CHARS) and following.isalnum()
        looks_like_html_comment = line[max(0, start - 2) : start] == "<!" or following == ">"
        if not looks_like_flag and not looks_like_html_comment:
            return True
    return False


def scan_file(path: str) -> list[str]:
    violations = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError:
        return violations

    for lineno, line in enumerate(lines, start=1):
        if TABLE_SEPARATOR_RE.match(line):
            continue
        scannable = INLINE_CODE_SPAN_RE.sub("", line)
        if UNICODE_DASH_RE.search(scannable) or has_ascii_dash_violation(scannable):
            violations.append(f"{path}:{lineno}: dash character/substitute found: {line.strip()[:120]}")
    return violations


def main() -> int:
    violations = []
    for path in tracked_files():
        if path.endswith(SELF_PATH_SUFFIX) or is_binary_path(path) or is_license_file(path):
            continue
        violations.extend(scan_file(path))

    if violations:
        print("Style check (dashes) failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        print(
            "\nUse a period, comma, colon, or semicolon instead of an em/en "
            "dash or '--'/'---'.",
            file=sys.stderr,
        )
        return 1

    print("Style check (dashes) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
