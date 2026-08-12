#!/usr/bin/env python3
"""Validate the current (or given) branch name against AGENTS.md conventions.

Required format: <type>/<short-kebab-description>, where type is one of
feat, fix, chore, docs, test. release/ and hotfix/ are always rejected.
Primary branches (main, master) are exempt from the pattern check but
are reported so callers can decide whether committing there is allowed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

ALLOWED_PREFIXES = ("feat", "fix", "chore", "docs", "test")
BANNED_PREFIXES = ("release", "hotfix")
PRIMARY_BRANCHES = ("main", "master")

BRANCH_RE = re.compile(
    r"^(" + "|".join(ALLOWED_PREFIXES) + r")/[a-z0-9]+(-[a-z0-9]+)*$"
)


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def current_branch() -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", nargs="?", default=None)
    args = parser.parse_args()

    branch = args.branch or current_branch()

    if branch in PRIMARY_BRANCHES:
        print(
            f"Branch '{branch}' is a primary branch; do not commit directly to it.",
            file=sys.stderr,
        )
        return 1

    prefix = branch.split("/", 1)[0]
    if prefix in BANNED_PREFIXES:
        print(f"Branch '{branch}' uses a banned prefix '{prefix}/'.", file=sys.stderr)
        return 1

    if not BRANCH_RE.match(branch):
        print(
            f"Branch '{branch}' does not match <type>/<short-kebab-description> "
            f"with type in {ALLOWED_PREFIXES}.",
            file=sys.stderr,
        )
        return 1

    print(f"Branch name check passed: '{branch}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
