#!/usr/bin/env python3
"""Flag banned-agent authorship on commits in a PR range.

Matches commit author, committer, and Co-authored-by trailer name/email,
plus the PR author's GitHub login, against a denylist. Never scans
free-form commit-message body or PR description text: "grok" is an
ordinary English verb and would false-positive constantly there.

Limitation: a banned agent committing under a human's own git identity,
with no Co-authored-by trailer, is invisible to this check. No mechanical
check can close that gap.
"""
import argparse
import json
import os
import re
import subprocess
import sys

DENYLIST_NAMES = ("grok", "xai")
DENYLIST_EMAIL_DOMAINS = ("x.ai",)

TRAILER = re.compile(r"^Co-authored-by:\s*(?P<name>[^<]*)<(?P<email>[^>]+)>", re.MULTILINE)
COMMIT_SEP = "\x1e"
FIELD_SEP = "\x1f"


def _matches_denylist(name: str, email: str) -> bool:
    """Return True if a structured author/email field names a banned agent."""
    name_lower = name.strip().lower()
    local_part = email.strip().lower().split("@", 1)[0]
    for term in DENYLIST_NAMES:
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, name_lower) or re.search(pattern, local_part):
            return True
    domain = email.strip().lower().rsplit("@", 1)[-1] if "@" in email else ""
    return domain in DENYLIST_EMAIL_DOMAINS


def find_violations(commits: list[dict], pr_author: str = "") -> list[str]:
    """Return one message per banned-agent authorship signal found.

    `commits` is a list of dicts with keys: sha, author_name, author_email,
    committer_name, committer_email, body (used only to parse trailers).
    """
    violations = []
    for commit in commits:
        sha = commit["sha"][:12]
        for role in ("author", "committer"):
            name = commit[f"{role}_name"]
            email = commit[f"{role}_email"]
            if _matches_denylist(name, email):
                violations.append(f"{sha}: banned-agent {role} '{name} <{email}>'")
        for match in TRAILER.finditer(commit.get("body", "")):
            name, email = match.group("name").strip(), match.group("email")
            if _matches_denylist(name, email):
                violations.append(f"{sha}: banned-agent co-author '{name} <{email}>'")
    if pr_author and _matches_denylist(pr_author, ""):
        violations.append(f"PR author: banned-agent login '{pr_author}'")
    return violations


def load_commits(base: str, head: str) -> list[dict]:
    """Collect commit metadata for the base..head range via git log."""
    fmt = FIELD_SEP.join(["%H", "%an", "%ae", "%cn", "%ce", "%B"])
    result = subprocess.run(
        ["git", "log", f"{base}..{head}", f"--format={fmt}{COMMIT_SEP}"],
        capture_output=True,
        text=True,
        check=True,
    )
    commits = []
    for record in result.stdout.split(COMMIT_SEP):
        record = record.strip("\n")
        if not record:
            continue
        sha, author_name, author_email, committer_name, committer_email, body = record.split(
            FIELD_SEP, 5
        )
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


def pr_author_from_event() -> str:
    """Read the PR author's GitHub login from the workflow event payload."""
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path or not os.path.isfile(event_path):
        return ""
    with open(event_path, encoding="utf-8") as handle:
        event = json.load(handle)
    return event.get("pull_request", {}).get("user", {}).get("login", "")


def check(base: str, head: str) -> int:
    """Check the base..head commit range. Return 0 when clean, 1 on a match."""
    commits = load_commits(base, head)
    violations = find_violations(commits, pr_author_from_event())
    if violations:
        for message in violations:
            print(message, file=sys.stderr)
        print("banned agents must not read, edit, commit, or open PRs here", file=sys.stderr)
        return 1
    print("no banned-agent authorship found")
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
