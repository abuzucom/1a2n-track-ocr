#!/usr/bin/env python3
"""Flag MD5/SHA-1 usage that lacks a justifying comment.

AGENTS.md rule 7: MD5/SHA-1 are banned in security-sensitive contexts
(passwords, tokens, signatures, untrusted integrity checks, session IDs,
key derivation) and require a comment naming the non-security use
everywhere else. This script cannot judge whether a comment's stated
justification is true, only whether one is present; human review still
decides whether the justification holds for security-sensitive contexts.
"""

from __future__ import annotations

import re
import subprocess
import sys

SCANNED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".php",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rs", ".sh", ".bash",
}

HASH_CALL_PATTERNS = [
    re.compile(r"hashlib\.(md5|sha1)\s*\(", re.IGNORECASE),
    re.compile(r"createHash\s*\(\s*['\"](md5|sha1)['\"]", re.IGNORECASE),
    re.compile(r"MessageDigest\.getInstance\s*\(\s*['\"](MD5|SHA-?1)['\"]", re.IGNORECASE),
    re.compile(r"\b(md5|sha1)sum\b", re.IGNORECASE),
    re.compile(r"\bcrypto/(md5|sha1)\b", re.IGNORECASE),
    re.compile(r"\b(?:md5|sha1)\.New\s*\(\s*\)", re.IGNORECASE),
    re.compile(r"OpenSSL::Digest::(MD5|SHA1)", re.IGNORECASE),
]

COMMENT_MARKERS = ("#", "//")

SELF_PATH_SUFFIX = "check_weak_hashing.py"


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tracked_files() -> list[str]:
    output = run_git(["ls-files"])
    return [line for line in output.splitlines() if line]


def line_has_comment(line: str) -> bool:
    return any(marker in line for marker in COMMENT_MARKERS)


def scan_file(path: str) -> list[str]:
    violations = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError:
        return violations

    for lineno, line in enumerate(lines, start=1):
        for pattern in HASH_CALL_PATTERNS:
            if pattern.search(line) and not line_has_comment(line):
                violations.append(
                    f"{path}:{lineno}: weak hash use without a justifying comment: "
                    f"{line.strip()}"
                )
    return violations


def main() -> int:
    violations = []
    for path in tracked_files():
        if path.endswith(SELF_PATH_SUFFIX):
            continue
        if path.lower().endswith(".md"):
            continue
        if not any(path.endswith(ext) for ext in SCANNED_EXTENSIONS):
            continue
        violations.extend(scan_file(path))

    if violations:
        print("Weak hashing check failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        print(
            "\nAdd a comment naming the non-security use, or replace MD5/SHA-1 "
            "with SHA-256/SHA-3 (bcrypt/scrypt/Argon2 for passwords).",
            file=sys.stderr,
        )
        return 1

    print("Weak hashing check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
