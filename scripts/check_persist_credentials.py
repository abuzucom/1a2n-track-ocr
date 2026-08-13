#!/usr/bin/env python3
"""Enforce persist-credentials: false on actions/checkout steps (Rule 10).

A portable, path-generic checker: copy this file into any repo and point
it at that repo's GitHub Actions workflow files. Text/regex-based, not a
full YAML parser, to stay stdlib-only like its sibling checkers.

A checkout step is clean if its block contains `persist-credentials:
false`, or the exact Rule 10 exception comment naming why the job keeps
the credential. Blocking: exits 1 on any violation.
"""
import re
import sys
from pathlib import Path

CHECKOUT_USES = re.compile(r"uses:\s*actions/checkout@")
PERSIST_FALSE = re.compile(r"persist-credentials:\s*false\b")
EXCEPTION_COMMENT = re.compile(r"#\s*persist-credentials:\s*true:.*\(Rule 10 exception\)\.")


def _indent(line: str) -> int:
    """Return the number of leading spaces on `line`."""
    return len(line) - len(line.lstrip(" "))


def _step_start(lines: list[str], uses_index: int) -> int:
    """Return the index of the `- ` step marker that owns `uses_index`."""
    uses_indent = _indent(lines[uses_index])
    for index in range(uses_index, -1, -1):
        stripped = lines[index].lstrip(" ")
        if stripped.startswith("- ") and _indent(lines[index]) <= uses_indent:
            return index
    return uses_index


def _block(lines: list[str], start: int) -> list[str]:
    """Return the lines belonging to the block introduced at `start`."""
    indent = _indent(lines[start])
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if not lines[index].strip():
            continue
        if _indent(lines[index]) <= indent:
            end = index
            break
    return lines[start:end]


def _leading_comments(lines: list[str], start: int) -> list[str]:
    """Return comment lines immediately above `start`, in original order."""
    comments = []
    index = start - 1
    while index >= 0:
        stripped = lines[index].strip()
        if stripped.startswith("#") or not stripped:
            comments.append(lines[index])
            index -= 1
            continue
        break
    return list(reversed(comments))


def find_violations(text: str, path: str) -> list[str]:
    """Return one message per checkout step missing persist-credentials: false."""
    violations = []
    lines = text.splitlines()
    for number, line in enumerate(lines):
        if not CHECKOUT_USES.search(line):
            continue
        start = _step_start(lines, number)
        block_lines = _leading_comments(lines, start) + _block(lines, start)
        block = "\n".join(block_lines)
        if PERSIST_FALSE.search(block) or EXCEPTION_COMMENT.search(block):
            continue
        violations.append(
            f"{path}:{number + 1}: actions/checkout missing "
            "persist-credentials: false (Rule 10)"
        )
    return violations


def main() -> int:
    """Check each given workflow file. Return 0 when all are clean, 1 otherwise."""
    paths = sys.argv[1:]
    if not paths:
        print("usage: check_persist_credentials.py FILE [FILE ...]", file=sys.stderr)
        return 1

    all_violations = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        all_violations.extend(find_violations(text, path))

    if all_violations:
        for message in all_violations:
            print(message, file=sys.stderr)
        print(
            "fix: add `with: persist-credentials: false`, or the Rule 10 "
            "exception comment",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
