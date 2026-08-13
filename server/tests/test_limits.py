"""Bounds on untrusted input: confidence range and image size.

Each test here corresponds to an audit finding. They are written to fail
against the pre-fix code so a pass means the bound exists, not that the
path merely ran.
"""

import importlib
import io
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

TOKEN = "test-token-abcdefghijklmnop"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKEND_TOKEN", TOKEN)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DATASET_DIR", str(tmp_path / "dataset"))
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)

    import auth, sinks, dataset, app as app_module
    for module in (auth, sinks, dataset, app_module):
        importlib.reload(module)

    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def post_result(client, confidence):
    return client.post(
        "/result",
        json={
            "player_id": "deck1",
            "capture_id": "100",
            "track": "Artist - Title",
            "confidence": confidence,
        },
        headers=AUTH,
    )


# --- non-finite confidence, audit finding 8 --------------------------
#
# NaN < threshold is False, so a NaN confidence passed the low-confidence
# gate and counted toward on-device trust. Infinity has the same effect
# in the opposite direction.

@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_confidence_rejected(client, value):
    assert post_result(client, value).status_code == 422


@pytest.mark.parametrize("value", [-0.5, 1.5, 1e308])
def test_out_of_range_confidence_rejected(client, value):
    assert post_result(client, value).status_code == 422


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_valid_confidence_accepted(client, value):
    assert post_result(client, value).status_code == 200


def test_nan_would_have_bypassed_the_threshold():
    """Document why the validation above is load bearing.

    This is the comparison arbiter.py performs. It is False for NaN, so
    without a finiteness check an unmeasured result reads as confident.
    """
    import arbiter
    assert (float("nan") < arbiter.ONDEVICE_CONFIDENCE_THRESHOLD) is False
    assert math.isfinite(float("nan")) is False


# --- image bounds, audit finding 3 -----------------------------------

def build_png(width: int, height: int) -> bytes:
    """Return a solid PNG of the given size, compressing to very little."""
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_oversized_image_rejected_before_decode(monkeypatch):
    """A decompression bomb must be refused from its header.

    A solid 12000x12000 PNG is a few tens of KB on the wire but about
    430 MB decoded, and the pipeline then upscales 3x on top of that.

    Asserting only that this raises would pass against the old code too,
    since the old dimension check rejected it after decoding. The point
    is the ordering, so this fails the test if cv2.imdecode is reached
    at all: by then the allocation has already happened.
    """
    import ocr
    payload = build_png(12000, 12000)
    assert len(payload) < 1_000_000, "test image should be small compressed"

    def fail_if_called(*args, **kwargs):
        raise AssertionError("cv2.imdecode reached: bomb was decoded before rejection")

    monkeypatch.setattr(ocr.cv2, "imdecode", fail_if_called)
    with pytest.raises(ValueError, match="exceed|limit|large"):
        ocr.preprocess(payload)


def test_pixel_budget_is_realistic_for_an_roi_crop():
    """The budget must reflect a one-line crop, not an arbitrary photo.

    The ROI is a single line of text from a VGA frame. A budget that
    permits a multi-hundred-megabyte array after the 3x upscale is not a
    bound in any useful sense.
    """
    import ocr
    upscaled_pixels = ocr.MAX_IMAGE_PIXELS * 9
    grayscale_mib = upscaled_pixels / (1024 * 1024)
    assert grayscale_mib < 32, (
        f"post-upscale worst case is {grayscale_mib:.0f} MiB, too permissive"
    )


def test_undecodable_bytes_still_rejected():
    import ocr
    with pytest.raises(ValueError):
        ocr.preprocess(b"not an image at all")
