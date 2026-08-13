#!/usr/bin/env python3
"""Warn when code changes land without touching README or CHANGELOG.

AGENTS.md workflow rule: update README (substantial changes) and
CHANGELOG (all changes). This rule went unenforced through seven build
phases while every other rule had a script, which is the gap AGENTS.md
rule 13 exists to prevent.

Warning only: it always exits 0. "Substantial" is not mechanically
decidable, so a blocking version would either nag on typo fixes or need
an override flag, and an override flag on a rule this soft gets used
reflexively until the check means nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

CODE_PREFIXES = ("firmware/", "server/", "ml/")
DOC_PATHS = ("README.md", "CHANGELOG.md")


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def changed_files(base: str, head: str) -> list[str]:
    output = run_git(["diff", "--name-only", f"{base}...{head}"])
    return [line for line in output.splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()

    try:
        paths = changed_files(args.base, args.head)
    except RuntimeError as error:
        # A missing base ref (shallow clone, unrelated history) must not
        # fail the build for a warning-only check.
        print(f"Docs check skipped: {error}")
        return 0

    code_changes = [path for path in paths if path.startswith(CODE_PREFIXES)]
    if not code_changes:
        print("Docs check passed (no code changes).")
        return 0

    touched_docs = [path for path in paths if path in DOC_PATHS]
    if touched_docs:
        print(f"Docs check passed ({', '.join(touched_docs)} updated).")
        return 0

    print("Docs check (warning only):")
    print(f"  - {len(code_changes)} file(s) changed under {', '.join(CODE_PREFIXES)}")
    print(f"  - neither {' nor '.join(DOC_PATHS)} was updated")
    print("  - update CHANGELOG for any change, README for substantial ones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
