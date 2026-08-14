"""Per-device credentials for the capture endpoints.

Anyone on the LAN can reach these endpoints. Input validation does not
help: a POST from an unauthorized host is a well formed request whose
payload reaches a live stream overlay. A credential is what separates a
rig from everyone else on the network.

Each credential authorizes exactly one player_id, so a compromised or
misconfigured rig can only affect its own output and its own training
data, not another deck's.

Covers /frame and /result only. /static and /output stay open, since OBS
cannot send a header.
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Optional

from fastapi import Header, HTTPException

ENV_VAR = "BACKEND_TOKENS"
LEGACY_ENV_VAR = "BACKEND_TOKEN"

# The shape validation.IDENTIFIER_RE enforces on requests, repeated here
# so a configuration typo fails at startup rather than as a puzzling 403.
PLAYER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

MIN_TOKEN_LENGTH = 16


def _parse(raw: str) -> dict[str, str]:
    """Parse comma separated `player_id:token` pairs."""
    credentials_by_player: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # Split on the first colon only. player_id cannot contain one, so
        # the remainder is unambiguously the token, and tokens are free
        # to contain colons.
        player_id, separator, token = entry.partition(":")
        if not separator:
            raise RuntimeError(
                f"{ENV_VAR} entry {entry!r} is not in player_id:token form"
            )
        if not PLAYER_RE.match(player_id):
            raise RuntimeError(f"{ENV_VAR}: {player_id!r} is not a valid player_id")
        if len(token) < MIN_TOKEN_LENGTH:
            raise RuntimeError(
                f"{ENV_VAR}: token for {player_id!r} is shorter than "
                f"{MIN_TOKEN_LENGTH} characters"
            )
        if player_id in credentials_by_player:
            raise RuntimeError(f"{ENV_VAR}: duplicate player_id {player_id!r}")
        credentials_by_player[player_id] = token
    return credentials_by_player


def credentials() -> dict[str, str]:
    """Return player_id to token, or raise if unconfigured.

    Never falls back to a default or an unauthenticated mode. Missing
    configuration is an error, and the safe response is to stop rather
    than serve the endpoints to anyone.
    """
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        if os.environ.get(LEGACY_ENV_VAR, "").strip():
            raise RuntimeError(
                f"{LEGACY_ENV_VAR} is no longer accepted: a single token "
                f"authorized every player, so any rig could overwrite "
                f"another's output. Set {ENV_VAR} to comma separated "
                f"player_id:token pairs instead, for example "
                f"{ENV_VAR}=deck1:<token1>,deck2:<token2>."
            )
        raise RuntimeError(
            f"{ENV_VAR} is not set. Provide comma separated player_id:token "
            f"pairs matching each rig's BACKEND_TOKEN in config.h. The "
            f"capture endpoints will not run unauthenticated."
        )

    parsed = _parse(raw)
    if not parsed:
        raise RuntimeError(f"{ENV_VAR} contains no usable player_id:token pairs")
    return parsed


def authorized_player(authorization: str = Header(default="")) -> str:
    """Return the player_id the presented credential authorizes.

    Raises 401 when no configured credential matches.
    """
    prefix = "Bearer "
    presented = authorization[len(prefix):] if authorization.startswith(prefix) else ""

    # compare_digest, never a plain comparison, which short-circuits on
    # the first differing byte and leaks the token prefix by prefix to
    # anyone able to time responses.
    #
    # Every candidate is compared even after a match, so the number of
    # comparisons does not reveal a credential's position in the set.
    matched: Optional[str] = None
    for player_id, token in credentials().items():
        if hmac.compare_digest(presented, token):
            matched = player_id

    if matched is None:
        raise HTTPException(
            status_code=401,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return matched


def require_player_match(authorized: str, requested: str) -> None:
    """Reject a request claiming a player_id its credential does not own."""
    if not hmac.compare_digest(authorized, requested):
        raise HTTPException(
            status_code=403,
            detail="credential is not authorized for this player_id",
        )
