#!/usr/bin/env python3
"""Reject commits or PRs attributed to a banned AI agent or vendor.

Checks, for each commit in the given range: author name/email, committer
name/email, and any "Co-authored-by:" trailer in the commit body, against
a denylist of banned agent/vendor identifiers. Also checks the PR author
login when running in GitHub Actions (GITHUB_ACTOR / pull_request event).

This cannot catch an agent committing under a human's own identity with
no trailer; that gap is documented in AGENTS.md.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

BANNED_PATTERNS = [
    re.compile(r"\bgrok\b", re.IGNORECASE),
    re.compile(r"\bxai\b", re.IGNORECASE),
    re.compile(r"x\.ai", re.IGNORECASE),
]

COMMIT_FIELD_SEPARATOR = "\x1f"
COMMIT_RECORD_SEPARATOR = "\x1e"


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def matches_banned(text: str) -> str | None:
    for pattern in BANNED_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def iter_commits(base: str, head: str) -> list[dict[str, str]]:
    fmt = COMMIT_FIELD_SEPARATOR.join(
        ["%H", "%an", "%ae", "%cn", "%ce", "%B"]
    ) + COMMIT_RECORD_SEPARATOR
    output = run_git(["log", f"{base}..{head}", f"--format={fmt}"])
    commits = []
    for raw in output.split(COMMIT_RECORD_SEPARATOR):
        raw = raw.strip("\n")
        if not raw:
            continue
        parts = raw.split(COMMIT_FIELD_SEPARATOR)
        if len(parts) != 6:
            continue
        sha, author_name, author_email, committer_name, committer_email, body = parts
        commits.append(
            {
                "sha": sha,
                "author_name": author_name,
                "author_email": author_email,
                "committer_name": committer_name,
                "committer_email": committer_email,
                "body": body,
            }
        )
    return commits


def find_coauthors(body: str) -> list[str]:
    return [
        line.split(":", 1)[1].strip()
        for line in body.splitlines()
        if line.strip().lower().startswith("co-authored-by:")
    ]


def check_commits(base: str, head: str) -> list[str]:
    violations = []
    for commit in iter_commits(base, head):
        fields_to_check = {
            "author": f"{commit['author_name']} {commit['author_email']}",
            "committer": f"{commit['committer_name']} {commit['committer_email']}",
        }
        for coauthor in find_coauthors(commit["body"]):
            fields_to_check[f"co-authored-by ({coauthor})"] = coauthor

        for field_name, value in fields_to_check.items():
            pattern = matches_banned(value)
            if pattern:
                violations.append(
                    f"{commit['sha'][:12]}: {field_name} matches banned pattern "
                    f"'{pattern}': {value!r}"
                )
    return violations


def check_pr_author() -> list[str]:
    actor = os.environ.get("GITHUB_ACTOR", "")
    if not actor:
        return []
    pattern = matches_banned(actor)
    if pattern:
        return [f"PR author matches banned pattern '{pattern}': {actor!r}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("GITHUB_BASE_REF", "origin/main"))
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()

    violations = check_commits(args.base, args.head) + check_pr_author()

    if violations:
        print("Banned agent check failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("Banned agent check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
