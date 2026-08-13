#!/usr/bin/env python3
"""Flag containers with no non-root user configured (Rule 12).

A portable, path-generic checker: copy this file into any repo and point
it at Dockerfiles, compose files, and Kubernetes manifests. Text/regex
based, not a real Dockerfile or YAML parser, to stay stdlib-only like its
sibling checkers.

Dockerfiles: only the final build stage matters (build-time root is
fine); it must carry a `USER` instruction that is not root/0. Compose:
each service under `services:` must set `user:`. Kubernetes: any manifest
defining `containers:` must set `runAsNonRoot: true` somewhere, checked
file-wide rather than per container. The exact-string Rule 12 exception
comment, `# runtime-root: this container <reason> (Rule 12 exception).`,
allow-lists an already-approved root container. Blocking: exits 1 on any
violation.
"""
import re
import sys
from pathlib import Path

FROM_STAGE = re.compile(r"^\s*FROM\s+\S+", re.IGNORECASE)
USER_NONROOT = re.compile(r"^\s*USER\s+(?!root\b|0\b)\S+", re.IGNORECASE)
RUN_AS_NON_ROOT = re.compile(r"runAsNonRoot:\s*true\b")
EXCEPTION_COMMENT = re.compile(r"#\s*runtime-root:.*\(Rule 12 exception\)\.")


def _indent(line: str) -> int:
    """Return the number of leading spaces on `line`."""
    return len(line) - len(line.lstrip(" "))


def _block(lines: list[str], start: int) -> list[str]:
    """Return the lines belonging to the block introduced at `start`."""
    indent = _indent(lines[start])
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if not lines[index].strip():
            continue
        if _indent(lines[index]) <= indent:
            end = index
            break
    return lines[start:end]


def _leading_comments(lines: list[str], start: int) -> list[str]:
    """Return comment lines immediately above `start`, in original order."""
    comments = []
    index = start - 1
    while index >= 0:
        stripped = lines[index].strip()
        if stripped.startswith("#") or not stripped:
            comments.append(lines[index])
            index -= 1
            continue
        break
    return list(reversed(comments))


def _dockerfile_violations(text: str, path: str) -> list[str]:
    """Check the final build stage for a non-root USER instruction."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if FROM_STAGE.match(line)]
    stage = lines[starts[-1]:] if starts else lines
    stage_text = "\n".join(stage)
    if any(USER_NONROOT.match(line) for line in stage):
        return []
    if EXCEPTION_COMMENT.search(stage_text):
        return []
    return [f"{path}: final build stage has no non-root USER (Rule 12)"]


def _compose_violations(text: str, path: str) -> list[str]:
    """Check every service under `services:` for a `user:` key."""
    lines = text.splitlines()
    violations = []
    for number, line in enumerate(lines):
        if line.strip() != "services:":
            continue
        services_indent = _indent(line)
        service_indent = None
        for index in range(number + 1, len(lines)):
            if not lines[index].strip():
                continue
            indent = _indent(lines[index])
            if indent <= services_indent:
                break
            if service_indent is None:
                service_indent = indent
            if indent != service_indent:
                continue
            block_lines = _leading_comments(lines, index) + _block(lines, index)
            block = "\n".join(block_lines)
            if re.search(r"^\s*user:\s*\S", block, re.MULTILINE):
                continue
            if EXCEPTION_COMMENT.search(block):
                continue
            name = lines[index].strip().rstrip(":")
            violations.append(
                f"{path}:{index + 1}: service '{name}' has no non-root user (Rule 12)"
            )
        break
    return violations


def _k8s_violations(text: str, path: str) -> list[str]:
    """Check a manifest defining `containers:` for a file-wide runAsNonRoot."""
    if "containers:" not in text:
        return []
    if RUN_AS_NON_ROOT.search(text) or EXCEPTION_COMMENT.search(text):
        return []
    return [f"{path}: containers with no runAsNonRoot: true (Rule 12)"]


def find_violations(text: str, path: str) -> list[str]:
    """Dispatch to the Dockerfile, compose, or Kubernetes check by filename."""
    name = Path(path).name.lower()
    if name == "dockerfile" or name.startswith(("dockerfile.", "dockerfile-")):
        return _dockerfile_violations(text, path)
    if name.endswith((".yml", ".yaml")) and name.startswith(("docker-compose", "compose")):
        return _compose_violations(text, path)
    if name.endswith((".yml", ".yaml")):
        return _k8s_violations(text, path)
    return []


def main() -> int:
    """Check each given file. Return 0 when all are clean, 1 otherwise."""
    paths = sys.argv[1:]
    if not paths:
        print("usage: check_dockerfile_root.py FILE [FILE ...]", file=sys.stderr)
        return 1

    all_violations = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        all_violations.extend(find_violations(text, path))

    if all_violations:
        for message in all_violations:
            print(message, file=sys.stderr)
        print(
            "fix: set a non-root user, or add the Rule 12 exception comment",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
