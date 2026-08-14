"""On-device result ingestion, shared by every transport.

The HTTP /result endpoint and the BLE bridge deliver the same payload
over different wires, and both must apply the same checks: field shape,
identifier validation, and the credential-to-player binding. Keeping
that sequence here rather than in app.py is what stops the two paths
drifting, which would show up as one transport enforcing a rule the
other does not.

The bridge calls into this module directly, so nothing here may assume
an HTTP request exists. It does raise fastapi.HTTPException, which the
endpoint lets propagate and the bridge catches; see ble_bridge.py.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

import arbiter
import auth
import validation


class OndeviceResult(BaseModel):
    player_id: str
    capture_id: str
    track: str = Field(max_length=validation.MAX_TRACK_LENGTH)
    # Optional preserves the request contract, but a missing value no
    # longer skips the gate; see arbiter.py. allow_inf_nan matters:
    # Pydantic accepts NaN for a bare float, and "NaN < threshold" is
    # False. Confidence is a dequantized softmax value, so 0.0 to 1.0.
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, allow_inf_nan=False
    )


def record_ondevice_result(
    payload: OndeviceResult, authorized: str, *, sole_source: bool = False
) -> dict:
    """Validate, authorize, and record an on-device OCR result.

    `authorized` is the player_id the presented credential owns, from
    auth.authorized_player. Set sole_source for a transport that carries
    no frames, so the result publishes on its own; see arbiter.py.

    Raises HTTPException on a bad identifier (422) or a credential that
    does not own the claimed player_id (403).
    """
    validation.validate_identifier(payload.player_id, "player_id")
    validation.validate_identifier(payload.capture_id, "capture_id")
    # The credential decides which player_id it may write, so a rig
    # cannot claim another deck's identity.
    auth.require_player_match(authorized, payload.player_id)

    agree = arbiter.record_ondevice(
        payload.player_id,
        payload.capture_id,
        payload.track,
        payload.confidence,
        sole_source=sole_source,
    )
    return {"received": True, "agree": agree}
