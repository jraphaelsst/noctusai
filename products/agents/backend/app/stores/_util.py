"""Private helpers shared by the agents store modules.

Not part of the public store surface (leading underscore) — each store
module imports what it needs from here to avoid five copies of the same
five-line timestamp helper. Pure functions, no IO.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC now — every store timestamp column is ``timestamptz``."""
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    """ISO-8601 string form, for PostgREST payloads (which want JSON-safe values)."""
    return utcnow().isoformat()
