#!/usr/bin/env python3
"""Verify deployed runtime artifacts against dependency-provenance.json."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_PATH = ROOT / "dependency-provenance.json"


def calculate_file_hash(path: Path) -> str:
    """Return the SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file_hash(path: Path, expected: str) -> None:
    """Raise when `path` does not match its reviewed SHA-256 digest."""
    actual = calculate_file_hash(path)
    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {path}: expected {expected}, got {actual}. "
            "Install the reviewed artifact before continuing."
        )


def verify_url_hash(url: str, expected: str) -> None:
    """Raise when a remote artifact does not match its reviewed digest."""
    digest = hashlib.sha256()
    with urlopen(url, timeout=120) as response:
        for block in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {url}: expected {expected}, got {actual}. "
            "Do not build with the changed artifact."
        )


def download_verified_artifact(url: str, expected: str, output_dir: Path) -> Path:
    """Download an artifact and retain it only when its digest matches."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(urlparse(url).path).name
    target = output_dir / filename
    digest = hashlib.sha256()
    with urlopen(url, timeout=120) as response, open(target, "wb") as handle:
        for block in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(block)
            handle.write(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {url}: expected {expected}, got {actual}. "
            f"Remove {target} and stop the build."
        )
    return target


def verify_firmware_archives(provenance: dict, output_dir: Path | None = None) -> None:
    """Verify mutable release archives used by the firmware platform."""
    platform = provenance["firmware"]["platform"]
    arduino = provenance["firmware"]["arduino_esp32"]
    artifacts = [
        (platform["release_url"], platform["archive_sha256"]),
        (arduino["core_url"], arduino["core_sha256"]),
        (arduino["libraries_url"], arduino["libraries_sha256"]),
    ]
    for url, expected in artifacts:
        if output_dir is None:
            verify_url_hash(url, expected)
        else:
            download_verified_artifact(url, expected, output_dir)


def bind_platform_packages(
    manifest_path: Path,
    package_dir: Path,
    provenance: dict,
) -> None:
    """Bind PlatformIO framework packages to verified local archives."""
    arduino = provenance["firmware"]["arduino_esp32"]
    archive_paths = {
        "framework-arduinoespressif32": (
            package_dir / Path(urlparse(arduino["core_url"]).path).name,
            arduino["core_sha256"],
        ),
        "framework-arduinoespressif32-libs": (
            package_dir / Path(urlparse(arduino["libraries_url"]).path).name,
            arduino["libraries_sha256"],
        ),
    }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    packages = manifest.get("packages")
    if not isinstance(packages, dict):
        raise ValueError(f"Platform manifest lacks packages: {manifest_path}")

    for package_name, (archive_path, expected) in archive_paths.items():
        verify_file_hash(archive_path, expected)
        package = packages.get(package_name)
        if not isinstance(package, dict):
            raise ValueError(f"Platform manifest lacks package: {package_name}")
        package["version"] = f"file://{archive_path.resolve()}"

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Verify selected local runtime artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tesseract", type=Path)
    parser.add_argument("--traineddata", type=Path)
    parser.add_argument("--firmware-archives", action="store_true")
    parser.add_argument("--firmware-output-dir", type=Path)
    parser.add_argument("--bind-platform", type=Path)
    parser.add_argument("--firmware-package-dir", type=Path)
    args = parser.parse_args()

    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    if args.bind_platform is not None:
        if args.firmware_package_dir is None:
            parser.error("--bind-platform requires --firmware-package-dir")
        bind_platform_packages(
            args.bind_platform,
            args.firmware_package_dir,
            provenance,
        )
        print("PlatformIO framework packages bound to verified archives")
        return 0
    if (args.tesseract is None) != (args.traineddata is None):
        parser.error("--tesseract and --traineddata must be provided together")
    if args.tesseract is not None:
        verify_file_hash(args.tesseract, provenance["runtime"]["tesseract"]["binary_sha256"])
        verify_file_hash(args.traineddata, provenance["runtime"]["traineddata"]["eng_sha256"])
    if args.firmware_archives or args.firmware_output_dir is not None:
        verify_firmware_archives(provenance, args.firmware_output_dir)
    if args.tesseract is None and not args.firmware_archives and args.firmware_output_dir is None:
        parser.error("select runtime paths or --firmware-archives")
    print("Dependency provenance verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
