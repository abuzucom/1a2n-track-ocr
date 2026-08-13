"""Request validation and path containment for untrusted request fields.

`player_id` reaches the filesystem in two places (sinks.py and
dataset.py), so it is validated at the HTTP boundary here and the
resulting paths are checked again where they are built. The second check
is not redundant: a boundary check is one refactor or one new caller away
from being bypassed, and the failure mode is an arbitrary file write.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

# Deliberately strict. These values name a rig and a capture, so there is
# no legitimate need for separators, dots, or anything outside this set.
# Rejecting "." and "/" outright is what stops both "../" traversal and
# the absolute-path case, where pathlib's "/" operator discards the left
# operand entirely if the right side is absolute.
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

MAX_TRACK_LENGTH = 512


def validate_identifier(value: str, field: str) -> str:
    """Return value if it is a safe identifier, else raise HTTP 422."""
    if not IDENTIFIER_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field} must match {IDENTIFIER_RE.pattern} "
                "(letters, digits, underscore, hyphen; 1 to 64 characters)"
            ),
        )
    return value


def resolve_within(base: Path, candidate: Path) -> Path:
    """Return candidate resolved, or raise if it escapes base.

    Defense in depth behind validate_identifier. Raises ValueError rather
    than HTTPException because this runs below the HTTP layer, and a hit
    here means the boundary check was bypassed, which is a bug rather
    than a client error.

    Note: `base` must be pre-resolved to an absolute path by the caller.
    """
    candidate_resolved = candidate.resolve()
    if not candidate_resolved.is_relative_to(base):
        raise ValueError(
            f"refusing to write outside {base}: {candidate_resolved}"
        )
    return candidate_resolved
