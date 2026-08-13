#!/usr/bin/env python3
"""Enforce the `type: description` commit subject format.

A portable, path-generic checker: copy this file into any repo and run
it in CI on `pull_request` events, over a `--base`/`--head` commit range.
Not a drop-in `commit-msg` hook: that hook receives a message-file path,
not two refs. Strips a trailing GitHub squash-merge suffix (` (#123)`)
before checking length, since that suffix is not user-authored. Cannot
verify imperative mood, only shape. Blocking: exits 1 on any violation.
"""
import argparse
import re
import subprocess
import sys

SUBJECT_PATTERN = re.compile(r"^(feat|fix|chore|docs|test): \S.*$")
SQUASH_SUFFIX = re.compile(r" \(#\d+\)$")
MAX_LENGTH = 50


def _strip_squash_suffix(subject: str) -> str:
    """Remove a trailing GitHub squash-merge ` (#123)` suffix, if present."""
    return SQUASH_SUFFIX.sub("", subject)


def find_violations(subjects: list[tuple[str, str]]) -> list[str]:
    """Return one message per commit subject violating the format rule.

    `subjects` is a list of (sha, subject) pairs.
    """
    violations = []
    for sha, raw_subject in subjects:
        short_sha = sha[:12] if sha else ""
        prefix = f"{short_sha}: " if short_sha else ""
        subject = _strip_squash_suffix(raw_subject)
        if not SUBJECT_PATTERN.match(subject):
            violations.append(
                f"{prefix}subject '{raw_subject}' must start with "
                "'type: description' (feat, fix, chore, docs, test)"
            )
            continue
        if len(subject) > MAX_LENGTH:
            violations.append(
                f"{prefix}subject '{raw_subject}' exceeds {MAX_LENGTH} "
                f"characters ({len(subject)})"
            )
        if subject.endswith("."):
            violations.append(f"{prefix}subject '{raw_subject}' ends with a period")
    return violations


def load_commits(base: str, head: str) -> list[tuple[str, str]]:
    """Collect (sha, subject) pairs for the base..head range via git log."""
    result = subprocess.run(
        ["git", "log", f"{base}..{head}", "--format=%H\x1f%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    commits = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        sha, subject = line.split("\x1f", 1)
        commits.append((sha, subject))
    return commits


def check(base: str, head: str) -> int:
    """Check the base..head commit range. Return 0 when clean, 1 otherwise."""
    violations = find_violations(load_commits(base, head))
    if violations:
        for message in violations:
            print(message, file=sys.stderr)
        return 1
    print("no commit-message violations found")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base ref (exclusive)")
    parser.add_argument("--head", required=True, help="head ref (inclusive)")
    args = parser.parse_args()
    try:
        return check(args.base, args.head)
    except subprocess.CalledProcessError as error:
        print(f"error: git log failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
