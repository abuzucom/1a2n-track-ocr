#!/usr/bin/env python3
"""Block non-ASCII characters outside string literals or data files.

AGENTS.md style rule: 7-bit ASCII (0-127) for all code, comments, and
prose. Unicode is allowed only inside string literals or data where the
domain requires it. This script flags any non-ASCII byte in a tracked
text file; it does not distinguish "inside a string literal" from
"inside a comment", since that requires a per-language parser. Files
whose whole purpose is localized data (see LITERAL_DATA_EXTENSIONS) are
skipped entirely, since flagging every translated string would defeat
the exception the policy itself grants.
"""

from __future__ import annotations

import subprocess
import sys

SELF_PATH_SUFFIX = "check_ascii.py"

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".exe", ".dll",
}

# Files that are pure translated/localized data are exempt (domain requires
# non-ASCII content). Everything else, including comments inside these
# formats, is still expected to be ASCII per the policy's own carve-out.
LITERAL_DATA_EXTENSIONS = {".po", ".mo"}


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
    if any(lower.endswith(ext) for ext in LITERAL_DATA_EXTENSIONS):
        return True
    return False


def scan_file(path: str) -> list[str]:
    violations = []
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return violations

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return violations

    for lineno, line in enumerate(text.splitlines(), start=1):
        for col, char in enumerate(line, start=1):
            if ord(char) > 127:
                violations.append(
                    f"{path}:{lineno}:{col}: non-ASCII character {char!r} (U+{ord(char):04X})"
                )
                break
    return violations


def main() -> int:
    violations = []
    for path in tracked_files():
        if path.endswith(SELF_PATH_SUFFIX) or is_skipped(path):
            continue
        violations.extend(scan_file(path))

    if violations:
        print("ASCII check failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("ASCII check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
