"""Output sinks: now_playing text/JSON files, keyed by player_id."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional

import validation

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output")).resolve()

# _state is keyed by a request-supplied player_id and never evicted, so
# without a ceiling a caller can grow it, and now_playing.json with it,
# without bound. A real deployment runs one rig per deck.
MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", "16"))

logger = logging.getLogger(__name__)

_ARTIST_TITLE_RE = re.compile(r"^(?P<artist>.+?) - (?P<title>.+)$")

_lock = threading.Lock()
_state: dict[str, dict] = {}
_dirs_created = False


def split_artist(track: str) -> Optional[str]:
    """Return the artist from a leading "Artist - Title" pattern, or None."""
    match = _ARTIST_TITLE_RE.match(track)
    if not match:
        return None
    return match.group("artist")


def _write_text(player_id: str, track: str, state_length: int) -> None:
    # track is the verbatim screen text; when split_artist matched, track
    # already reads "Artist - Title", so no artist prefix needs adding.
    #
    # player_id is validated at the HTTP boundary, but it lands in a
    # filename here, so the resolved path is checked against OUTPUT_DIR
    # as well. See validation.resolve_within for why both exist.
    target = validation.resolve_within(OUTPUT_DIR, OUTPUT_DIR / f"now_playing_{player_id}.txt")
    target.write_text(track, encoding="utf-8")
    if state_length == 1:
        (OUTPUT_DIR / "now_playing.txt").write_text(track, encoding="utf-8")


def _write_json(state_snapshot: dict) -> None:
    payload = {"players": state_snapshot}
    (OUTPUT_DIR / "now_playing.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def update(player_id: str, track: str, source: str, confidence: Optional[float] = None) -> bool:
    """Record a track result for player_id. Returns True if it changed output."""
    global _dirs_created
    if not _dirs_created:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _dirs_created = True

    artist = split_artist(track)

    with _lock:
        previous = _state.get(player_id)
        if previous is not None and previous["track"] == track:
            return False

        if previous is None and len(_state) >= MAX_PLAYERS:
            logger.warning(
                "refusing new player_id %r: already tracking %d, the MAX_PLAYERS limit",
                player_id, MAX_PLAYERS,
            )
            return False

        _state[player_id] = {
            "track": track,
            "artist": artist,
            "source": source,
            "confidence": confidence,
        }
        state_snapshot = dict(_state)
        state_length = len(_state)

    _write_text(player_id, track, state_length)
    _write_json(state_snapshot)
    return True
