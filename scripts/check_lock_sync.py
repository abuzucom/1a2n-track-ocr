#!/usr/bin/env python3
"""Verify each requirements manifest agrees with its compiled lock file.

A manifest pin and its lock can drift silently: an automated dependency
bump edits `requirements-dev.txt` but leaves `requirements-dev.lock`
alone, so CI and every developer keep installing the old version while
the manifest advertises the new one. Nothing catches that by eye.

Pairs are discovered by replacing the manifest's `.txt` suffix with
`.lock`. Manifests with no matching lock are skipped, since not every
manifest is compiled. Blocking: exits 1 on any disagreement.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PIN_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;\\#]+)")


def normalize_name(name: str) -> str:
    """Return the PEP 503 normalized form of a distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(path: Path) -> dict[str, str]:
    """Return {normalized name: version} for every `name==version` pin."""
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-r", "--")):
            continue
        match = PIN_RE.match(stripped)
        if match:
            pins[normalize_name(match.group(1))] = match.group(2)
    return pins


def tracked_manifests() -> list[Path]:
    """Return tracked requirements*.txt paths that have a sibling lock."""
    result = subprocess.run(
        ["git", "ls-files", "*requirements*.txt"],
        capture_output=True, text=True, check=True,
    )
    manifests = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        manifest = Path(line)
        if manifest.with_suffix(".lock").is_file():
            manifests.append(manifest)
    return manifests


def find_violations(manifest: Path) -> list[str]:
    """Return one message per pin the lock does not agree with."""
    lock = manifest.with_suffix(".lock")
    manifest_pins = parse_pins(manifest)
    lock_pins = parse_pins(lock)

    violations = []
    for name, version in sorted(manifest_pins.items()):
        locked = lock_pins.get(name)
        if locked is None:
            violations.append(
                f"{manifest}: pins {name}=={version} but {lock} does not contain it"
            )
        elif locked != version:
            violations.append(
                f"{manifest}: pins {name}=={version} but {lock} has {name}=={locked}"
            )
    return violations


def main() -> int:
    """Check every manifest and lock pair. Return 0 when all agree."""
    manifests = tracked_manifests()
    if not manifests:
        print("Lock sync check passed (no compiled manifests found).")
        return 0

    violations = []
    for manifest in manifests:
        violations.extend(find_violations(manifest))

    if violations:
        print("Lock sync check failed:", file=sys.stderr)
        for message in violations:
            print(f"  - {message}", file=sys.stderr)
        print(
            "\nfix: regenerate the lock, e.g. python -m piptools compile "
            "--generate-hashes --strip-extras --output-file <lock> <manifest>",
            file=sys.stderr,
        )
        return 1

    print(f"Lock sync check passed ({len(manifests)} manifest/lock pair(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
