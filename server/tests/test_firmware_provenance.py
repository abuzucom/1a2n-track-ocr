import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_provenance_matches_firmware_and_caddy_configuration():
    provenance = json.loads((ROOT / "dependency-provenance.json").read_text(encoding="utf-8"))
    platformio = (ROOT / "firmware" / "platformio.ini").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "app-tests.yml").read_text(
        encoding="utf-8"
    )

    platform_commit = provenance["firmware"]["platform"]["commit"]
    caddy_digest = provenance["runtime"]["caddy"]["image_digest"]
    assert platform_commit in platformio
    assert caddy_digest in workflow
    assert "--firmware-output-dir" in workflow
    assert "--bind-platform" in workflow
    assert "pio pkg install --global --tool" in workflow

    sha256_pattern = re.compile(r"[0-9a-f]{64}")
    assert sha256_pattern.fullmatch(provenance["firmware"]["platform"]["archive_sha256"])
    assert sha256_pattern.fullmatch(provenance["runtime"]["tesseract"]["binary_sha256"])
    assert sha256_pattern.fullmatch(provenance["runtime"]["traineddata"]["eng_sha256"])


def test_production_profile_enables_hardware_security():
    platformio = (ROOT / "firmware" / "platformio.ini").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "app-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "[env:w11-esp32s3-production]" in platformio
    assert "CONFIG_SECURE_BOOT_V2_ENABLED=y" in platformio
    assert "CONFIG_SECURE_FLASH_ENC_ENABLED=y" in platformio
    assert "CONFIG_SECURE_FLASH_ENCRYPTION_MODE_RELEASE=y" in platformio
    assert "CONFIG_SECURE_FLASH_ENCRYPTION_AES256=y" in platformio
    assert "sdkconfig.w11-esp32s3-production" in workflow


def test_hash_verifier_rejects_changed_artifact(tmp_path):
    from scripts.verify_dependency_provenance import verify_file_hash

    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"reviewed")
    verify_file_hash(
        artifact,
        "e4f934f321eb76c9bf8b5103e0a0d9afe72d6e62ace3d3ea849790619bf7487a",
    )

    artifact.write_bytes(b"changed")
    try:
        verify_file_hash(
            artifact,
            "e4f934f321eb76c9bf8b5103e0a0d9afe72d6e62ace3d3ea849790619bf7487a",
        )
    except RuntimeError as error:
        assert "SHA-256" in str(error)
    else:
        raise AssertionError("changed artifact passed provenance verification")


def test_url_verifier_rejects_changed_artifact(tmp_path):
    from scripts.verify_dependency_provenance import verify_url_hash

    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"reviewed")
    verify_url_hash(
        artifact.as_uri(),
        "e4f934f321eb76c9bf8b5103e0a0d9afe72d6e62ace3d3ea849790619bf7487a",
    )

    artifact.write_bytes(b"changed")
    try:
        verify_url_hash(
            artifact.as_uri(),
            "e4f934f321eb76c9bf8b5103e0a0d9afe72d6e62ace3d3ea849790619bf7487a",
        )
    except RuntimeError as error:
        assert "SHA-256" in str(error)
    else:
        raise AssertionError("changed URL artifact passed provenance verification")


def test_platform_manifest_binds_verified_frameworks(tmp_path):
    from scripts.verify_dependency_provenance import bind_platform_packages

    provenance = json.loads((ROOT / "dependency-provenance.json").read_text(encoding="utf-8"))
    packages = tmp_path / "packages"
    packages.mkdir()
    core = packages / "esp32-core-3.3.11.tar.xz"
    libraries = packages / "esp32-core-3.3.11-libs.tar.xz"
    core.write_bytes(b"core")
    libraries.write_bytes(b"libraries")
    provenance["firmware"]["arduino_esp32"]["core_sha256"] = (
        hashlib.sha256(b"core").hexdigest()
    )
    provenance["firmware"]["arduino_esp32"]["libraries_sha256"] = (
        hashlib.sha256(b"libraries").hexdigest()
    )
    manifest_path = tmp_path / "platform.json"
    manifest_path.write_text(
        json.dumps({
            "packages": {
                "framework-arduinoespressif32": {"version": "remote"},
                "framework-arduinoespressif32-libs": {"version": "remote"},
            }
        }),
        encoding="utf-8",
    )

    bind_platform_packages(manifest_path, packages, provenance)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["packages"]["framework-arduinoespressif32"]["version"] == (
        f"file://{core.resolve()}"
    )
    assert manifest["packages"]["framework-arduinoespressif32-libs"]["version"] == (
        f"file://{libraries.resolve()}"
    )
