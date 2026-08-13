"""Shared-secret authentication for the capture endpoints.

The backend binds to all interfaces so the rig can reach it over the
LAN, which means anyone else on that LAN can reach it too. Input
validation does not help here: a POST to /result from an unauthorized
host is a perfectly well formed request, and its payload goes straight
to a live stream overlay. A shared secret is what separates the rig from
everyone else on the venue network.

Scope: /frame and /result only. The /static and /output mounts stay
open, because OBS reads them and cannot send a header.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException

ENV_VAR = "BACKEND_TOKEN"


def expected_token() -> str:
    """Return the configured token, or raise if it is unset.

    Refuses to fall back to a default or to an unauthenticated mode. A
    missing token is a misconfiguration, and the safe response is to stop
    rather than to silently serve the endpoints to anyone.
    """
    token = os.environ.get(ENV_VAR, "")
    if not token:
        raise RuntimeError(
            f"{ENV_VAR} is not set. Set it to the same value as BACKEND_TOKEN "
            "in the firmware's config.h. The capture endpoints will not run "
            "unauthenticated."
        )
    return token


def require_token(authorization: str = Header(default="")) -> None:
    """FastAPI dependency enforcing the bearer token on an endpoint."""
    prefix = "Bearer "
    presented = authorization[len(prefix):] if authorization.startswith(prefix) else ""

    # compare_digest, never ==. A plain comparison short-circuits on the
    # first differing byte, which leaks the token prefix by prefix to
    # anyone able to time the responses.
    if not hmac.compare_digest(presented, expected_token()):
        raise HTTPException(
            status_code=401,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
