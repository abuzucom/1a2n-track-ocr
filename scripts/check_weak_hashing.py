#!/usr/bin/env python3
"""Flag MD5/SHA-1 calls without a same-line justification comment (Rule 7).

A portable, path-generic checker: copy this file into any repo and point
it at that repo's own source globs and CI. Verifies a comment exists on
the call's line; it cannot verify the justification is true, or catch
aliased imports and dynamic dispatch. Blocking: exits 1 on any violation.
"""
import re
import sys
from pathlib import Path

HASH_CALL = re.compile(
    r"hashlib\.(?:md5|sha1)\s*\("
    r"|createHash\(\s*['\"](?:md5|sha1)['\"]\s*\)"
    r"|\b(?:md5|sha1)\s*\("
    r"|Digest::(?:MD5|SHA1)\b",
    re.IGNORECASE,
)
COMMENT_MARKERS = ("#", "//")


def _has_same_line_comment(line: str, after: int) -> bool:
    """Return True if a comment with real text follows column `after`."""
    tail = line[after:]
    for marker in COMMENT_MARKERS:
        index = tail.find(marker)
        if index != -1 and tail[index + len(marker):].strip():
            return True
    return False


def find_violations(text: str, path: str) -> list[str]:
    """Return one message per unjustified MD5/SHA-1 call in `text`."""
    violations = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in HASH_CALL.finditer(line):
            if not _has_same_line_comment(line, match.end()):
                violations.append(
                    f"{path}:{number}: MD5/SHA-1 call without a "
                    "justification comment (Rule 7)"
                )
    return violations


def main() -> int:
    """Check each given file. Return 0 when all are clean, 1 otherwise."""
    paths = sys.argv[1:]
    if not paths:
        print("usage: check_weak_hashing.py FILE [FILE ...]", file=sys.stderr)
        return 1

    all_violations = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        all_violations.extend(find_violations(text, path))

    if all_violations:
        for message in all_violations:
            print(message, file=sys.stderr)
        print(
            "fix: use SHA-256/bcrypt, or add a same-line comment naming "
            "the non-security use",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
