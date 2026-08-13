#!/usr/bin/env python3
"""Heuristic secret and credential scanner for tracked files.

AGENTS.md rule 8: never commit keys, tokens, passwords, private keys, or
.env files. This is a pattern-matching heuristic, not entropy analysis;
it will miss novel secret formats and may flag placeholders. Treat a
clean run as necessary, not sufficient, and review diffs by eye too.
"""

from __future__ import annotations

import re
import subprocess
import sys

SELF_PATH_SUFFIX = "check_secrets_heuristic.py"

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".exe", ".dll",
}

PLACEHOLDER_MARKERS = (
    "changeme", "change_me", "xxxx", "your-", "your_", "example",
    "placeholder", "<", "redacted", "dummy", "fake", "sample", "insert",
    "todo", "***",
)

SECRET_PATTERNS = [
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("Private key block", re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY-----")),
    (
        "Generic credential assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*"
            r"['\"]([^'\"]{8,})['\"]"
        ),
    ),
]


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


def is_tracked_env_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name == ".env.example":
        return False
    return name == ".env" or name.startswith(".env.")


def looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def scan_file(path: str) -> list[str]:
    violations = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError:
        return violations

    for lineno, line in enumerate(lines, start=1):
        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            captured = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(0)
            if looks_like_placeholder(captured):
                continue
            violations.append(f"{path}:{lineno}: possible {label}: {line.strip()[:120]}")
    return violations


def main() -> int:
    violations = []
    for path in tracked_files():
        if path.endswith(SELF_PATH_SUFFIX) or is_binary_path(path):
            continue
        if is_tracked_env_file(path):
            violations.append(f"{path}: tracked .env file (only .env.example is allowed)")
            continue
        violations.extend(scan_file(path))

    if violations:
        print("Secrets heuristic check failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        print(
            "\nIf a match is a false positive placeholder, rename it to include "
            "one of: changeme, example, placeholder, your-, <...>.",
            file=sys.stderr,
        )
        return 1

    print("Secrets heuristic check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
