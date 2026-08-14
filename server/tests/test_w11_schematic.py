import importlib.util
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPOSITORY_ROOT / "docs" / "w11-kicad" / "generate_schematic.py"


def test_generated_schematic_has_release_title_block() -> None:
    """Require the documented title, SemVer revision, and issue date."""
    module_spec = importlib.util.spec_from_file_location("w11_schematic_generator", GENERATOR_PATH)
    assert module_spec is not None
    assert module_spec.loader is not None

    generator = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = generator
    try:
        module_spec.loader.exec_module(generator)
    finally:
        sys.modules.pop(module_spec.name, None)

    schematic = generator.build_schematic(generator.load_parts())
    assert '(title "1A2N-OCR")' in schematic
    assert '(date "2026-08-14")' in schematic
    assert '(rev "0.1.0")' in schematic
