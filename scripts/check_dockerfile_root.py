#!/usr/bin/env python3
"""Ensure containers run as non-root unless an explicit exception is recorded.

AGENTS.md rule 12: Dockerfiles must end with a non-root USER, compose
services must set a non-root user, and Kubernetes pod/container specs
must set runAsNonRoot: true, unless the file carries a comment in the
exact form:
  # runtime-root: this container <reason> (Rule 12 exception).

This is a heuristic line/text scanner, not a full Dockerfile or YAML
parser (no new dependency). Kubernetes manifests are checked file-wide
rather than per-container, so a multi-container manifest with a mix of
root and non-root containers will not be caught precisely.
"""

from __future__ import annotations

import glob
import os
import re
import sys

EXCEPTION_COMMENT_RE = re.compile(
    r"#\s*runtime-root:\s*this container .+\(Rule 12 exception\)\.\s*$", re.MULTILINE
)

USER_DIRECTIVE_RE = re.compile(r"^\s*USER\s+(\S+)", re.IGNORECASE | re.MULTILINE)
COMPOSE_SERVICE_USER_RE = re.compile(r"^\s*user:\s*\S+", re.MULTILINE)
K8S_KIND_RE = re.compile(r"^\s*kind:\s*(Pod|Deployment|StatefulSet|DaemonSet|Job|CronJob)\s*$", re.MULTILINE)
K8S_RUN_AS_NONROOT_RE = re.compile(r"runAsNonRoot:\s*true", re.IGNORECASE)

ROOT_USER_VALUES = {"root", "0"}


def find_dockerfiles() -> list[str]:
    candidates = set()
    for root, _dirs, files in os.walk("."):
        if ".git" in root.split(os.sep):
            continue
        for name in files:
            if name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".dockerfile"):
                candidates.add(os.path.join(root, name))
    return sorted(candidates)


def find_compose_files() -> list[str]:
    patterns = ["docker-compose*.yml", "docker-compose*.yaml", "compose.yml", "compose.yaml"]
    return sorted({p for pattern in patterns for p in glob.glob(pattern)} | {
        p for pattern in patterns for p in glob.glob(os.path.join("**", pattern), recursive=True)
    })


def find_k8s_manifests() -> list[str]:
    manifests = []
    for path in glob.glob(os.path.join("**", "*.yml"), recursive=True) + glob.glob(
        os.path.join("**", "*.yaml"), recursive=True
    ):
        if ".git" in path.split(os.sep):
            continue
        if os.path.join("", ".github", "workflows") in path:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
        except OSError:
            continue
        if K8S_KIND_RE.search(text):
            manifests.append((path, text))
    return manifests


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def check_dockerfile(path: str) -> list[str]:
    text = read_text(path)
    if EXCEPTION_COMMENT_RE.search(text):
        return []

    users = USER_DIRECTIVE_RE.findall(text)
    effective_user = users[-1] if users else None

    if effective_user is None:
        return [f"{path}: no USER directive; container runs as root at runtime"]
    if effective_user.lower() in ROOT_USER_VALUES:
        return [f"{path}: final USER directive is root ('{effective_user}')"]
    return []


def check_compose_file(path: str) -> list[str]:
    text = read_text(path)
    if EXCEPTION_COMMENT_RE.search(text):
        return []
    if "services:" not in text:
        return []
    if COMPOSE_SERVICE_USER_RE.search(text):
        return []
    return [f"{path}: no service sets a non-root 'user:' and no Rule 12 exception comment found"]


def check_k8s_manifest(path: str, text: str) -> list[str]:
    if EXCEPTION_COMMENT_RE.search(text):
        return []
    if K8S_RUN_AS_NONROOT_RE.search(text):
        return []
    return [f"{path}: no securityContext.runAsNonRoot: true found and no Rule 12 exception comment"]


def main() -> int:
    violations = []
    for path in find_dockerfiles():
        violations.extend(check_dockerfile(path))
    for path in find_compose_files():
        violations.extend(check_compose_file(path))
    for path, text in find_k8s_manifests():
        violations.extend(check_k8s_manifest(path, text))

    if violations:
        print("Container root check failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("Container root check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
