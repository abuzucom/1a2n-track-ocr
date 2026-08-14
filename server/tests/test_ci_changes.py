import pytest

from scripts.detect_app_changes import classify_changed_paths


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("README.md", set()),
        ("server/app.py", {"backend"}),
        ("ml/train.py", {"backend"}),
        ("server/requirements-dev.lock", {"backend", "lock"}),
        ("firmware/src/main.cpp", {"firmware"}),
        ("firmware/platformio.ini", {"backend", "firmware"}),
        ("Caddyfile", {"caddy"}),
        ("dependency-provenance.json", {"backend", "firmware"}),
        ("scripts/check_lock_sync.py", {"lock"}),
        (
            "scripts/verify_dependency_provenance.py",
            {"backend", "firmware"},
        ),
        (
            "scripts/detect_app_changes.py",
            {"backend", "caddy", "firmware", "lock"},
        ),
        (
            ".github/workflows/app-tests.yml",
            {"backend", "caddy", "firmware", "lock"},
        ),
    ],
)
def test_classify_changed_path(path: str, expected: set[str]) -> None:
    changes = classify_changed_paths([path])

    assert {name for name, changed in changes.items() if changed} == expected


def test_classify_changed_paths_combines_categories() -> None:
    changes = classify_changed_paths(["server/app.py", "Caddyfile"])

    assert changes == {
        "backend": True,
        "caddy": True,
        "firmware": False,
        "lock": False,
    }
