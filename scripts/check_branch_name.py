#!/usr/bin/env python3
"""Enforce the <type>/<kebab-description> branch naming convention.

A portable, path-generic checker: copy this file into any repo and use
it as a pre-push hook or CI step on `pull_request` events. Never flags
`main`, `master`, or a detached HEAD (`git rev-parse --abbrev-ref HEAD`
reports the literal string "HEAD" in that state). Blocking: exits 1 on
a mismatch.
"""
import argparse
import os
import re
import subprocess
import sys

DEFAULT_PREFIXES = ("feat", "fix", "chore", "docs", "test")
EXEMPT_BRANCHES = ("main", "master", "HEAD")


def _pattern(prefixes: tuple[str, ...]) -> re.Pattern:
    """Build the <type>/<kebab-description> pattern for the given prefixes."""
    prefix_group = "|".join(re.escape(prefix) for prefix in prefixes)
    return re.compile(rf"^(?:{prefix_group})/[a-z0-9]+(?:-[a-z0-9]+)*$")


def find_violations(branch: str, prefixes: tuple[str, ...] = DEFAULT_PREFIXES) -> list[str]:
    """Return a violation message if `branch` breaks the naming convention."""
    if not branch or branch in EXEMPT_BRANCHES:
        return []
    if _pattern(prefixes).match(branch):
        return []
    allowed = ", ".join(f"{prefix}/" for prefix in prefixes)
    return [f"branch '{branch}' does not match <type>/<kebab-description> ({allowed})"]


def _current_branch() -> str:
    """Return the PR head branch in CI, or the local checked-out branch."""
    head_ref = os.environ.get("GITHUB_HEAD_REF", "")
    if head_ref:
        return head_ref
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", nargs="?", help="branch to check (default: current branch)")
    parser.add_argument(
        "--prefixes",
        default=",".join(DEFAULT_PREFIXES),
        help="comma-separated allowed prefixes",
    )
    args = parser.parse_args()
    branch = args.branch or _current_branch()
    prefixes = tuple(prefix.strip() for prefix in args.prefixes.split(",") if prefix.strip())

    violations = find_violations(branch, prefixes)
    if violations:
        for message in violations:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
