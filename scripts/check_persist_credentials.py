#!/usr/bin/env python3
"""Ensure actions/checkout steps set persist-credentials: false.

AGENTS.md rule 11: every actions/checkout step must set
persist-credentials: false unless the job needs the checked-out
credential afterward, in which case the step (or the line right above
it) must carry a comment in the exact form:
  # persist-credentials: true: this job <reason> (Rule 11 exception).

This is a line-based scanner, not a full YAML parser (no new
dependency), so it relies on standard two-space GitHub Actions
indentation.
"""

from __future__ import annotations

import glob
import re
import sys

CHECKOUT_USES_RE = re.compile(r"^\s*-\s*uses:\s*actions/checkout@")
PERSIST_FALSE_RE = re.compile(r"persist-credentials:\s*false\b")
PERSIST_TRUE_RE = re.compile(r"persist-credentials:\s*true\b")
EXCEPTION_COMMENT_RE = re.compile(
    r"#\s*persist-credentials:\s*true:\s*this job .+\(Rule 11 exception\)\.\s*$"
)

WORKFLOW_GLOBS = [".github/workflows/*.yml", ".github/workflows/*.yaml"]


def indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def step_block(lines: list[str], start_index: int) -> list[str]:
    step_indent = indentation(lines[start_index])
    block = [lines[start_index]]
    for line in lines[start_index + 1 :]:
        if not line.strip():
            block.append(line)
            continue
        if indentation(line) <= step_indent and line.lstrip().startswith("-"):
            break
        if indentation(line) < step_indent:
            break
        block.append(line)
    return block


def check_file(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()

    violations = []
    for index, line in enumerate(lines):
        if not CHECKOUT_USES_RE.match(line):
            continue

        block = step_block(lines, index)
        block_text = "".join(block)
        preceding_line = lines[index - 1] if index > 0 else ""

        if PERSIST_FALSE_RE.search(block_text):
            continue

        has_exception_comment = bool(
            EXCEPTION_COMMENT_RE.search(block_text) or EXCEPTION_COMMENT_RE.search(preceding_line)
        )
        if PERSIST_TRUE_RE.search(block_text) and has_exception_comment:
            continue

        if has_exception_comment:
            continue

        lineno = index + 1
        if PERSIST_TRUE_RE.search(block_text):
            violations.append(
                f"{path}:{lineno}: persist-credentials: true without a Rule 11 "
                "exception comment"
            )
        else:
            violations.append(
                f"{path}:{lineno}: actions/checkout missing persist-credentials: false"
            )
    return violations


def main() -> int:
    files = sorted({p for pattern in WORKFLOW_GLOBS for p in glob.glob(pattern)})
    violations = []
    for path in files:
        violations.extend(check_file(path))

    if violations:
        print("persist-credentials check failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print(f"persist-credentials check passed ({len(files)} workflow file(s) scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
