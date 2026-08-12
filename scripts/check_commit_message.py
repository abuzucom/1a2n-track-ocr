#!/usr/bin/env python3
"""Validate a commit message subject line's shape.

AGENTS.md format: "type: description", <= 50 characters, no trailing
period. type is one of feat, fix, chore, docs, test. This checks shape
only; it cannot verify imperative mood.
"""

from __future__ import annotations

import re
import sys

ALLOWED_TYPES = ("feat", "fix", "chore", "docs", "test")
MAX_SUBJECT_LENGTH = 50

SUBJECT_RE = re.compile(r"^(" + "|".join(ALLOWED_TYPES) + r"): .+[^.]$")


def check_subject(subject: str) -> list[str]:
    errors = []
    if len(subject) > MAX_SUBJECT_LENGTH:
        errors.append(f"subject is {len(subject)} chars, max {MAX_SUBJECT_LENGTH}")
    if subject.endswith("."):
        errors.append("subject has a trailing period")
    if not SUBJECT_RE.match(subject):
        errors.append(f"subject must match 'type: description' with type in {ALLOWED_TYPES}")
    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_commit_message.py <commit-msg-file>", file=sys.stderr)
        return 2

    with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.read().splitlines()

    non_comment_lines = [line for line in lines if not line.startswith("#")]
    if not non_comment_lines or not non_comment_lines[0].strip():
        print("Commit message subject is empty.", file=sys.stderr)
        return 1

    subject = non_comment_lines[0].strip()
    errors = check_subject(subject)

    if errors:
        print(f"Commit message check failed for subject: {subject!r}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Commit message check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
