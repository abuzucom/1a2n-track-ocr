#!/usr/bin/env python3
"""Report which application CI categories changed between two commits."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import PurePosixPath


CATEGORY_CONTROL_PATHS = frozenset({
    ".github/workflows/app-tests.yml",
    "scripts/detect_app_changes.py",
})
BACKEND_PATHS = frozenset({
    "dependency-provenance.json",
    "firmware/platformio.ini",
    "scripts/verify_dependency_provenance.py",
})
FIRMWARE_PATHS = frozenset({
    "dependency-provenance.json",
    "scripts/verify_dependency_provenance.py",
})
LOCK_PATHS = frozenset({"scripts/check_lock_sync.py"})


def is_requirement_path(path: str) -> bool:
    """Return whether a path is a requirements manifest or lock."""
    name = PurePosixPath(path).name
    return name.startswith("requirements") and PurePosixPath(name).suffix in {
        ".lock",
        ".txt",
    }


def classify_changed_paths(paths: Iterable[str]) -> dict[str, bool]:
    """Return the application CI categories affected by changed paths."""
    changed_paths = set(paths)
    control_changed = bool(changed_paths & CATEGORY_CONTROL_PATHS)
    backend_changed = any(
        path.startswith(("server/", "ml/")) or path in BACKEND_PATHS
        for path in changed_paths
    )
    firmware_changed = any(
        path.startswith("firmware/") or path in FIRMWARE_PATHS
        for path in changed_paths
    )
    lock_changed = any(is_requirement_path(path) for path in changed_paths)
    return {
        "backend": control_changed or backend_changed,
        "caddy": control_changed or "Caddyfile" in changed_paths,
        "firmware": control_changed or firmware_changed,
        "lock": control_changed or lock_changed or bool(changed_paths & LOCK_PATHS),
    }


def find_changed_paths(base: str, head: str) -> list[str]:
    """Return paths changed from the merge base through head."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip().replace("\n", " ")
        raise RuntimeError(f"git diff failed: {message}")
    return [path for path in result.stdout.splitlines() if path]


def main() -> int:
    """Print GitHub Actions outputs for changed application categories."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        changes = classify_changed_paths(find_changed_paths(args.base, args.head))
    except RuntimeError as error:
        print(f"Change detection failed: {error}", file=sys.stderr)
        return 1
    for name, changed in changes.items():
        print(f"{name}={str(changed).lower()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
