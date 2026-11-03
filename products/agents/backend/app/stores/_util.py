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


# NOC-REMEDIATE[store-ts-passthrough]: the other agents store row mappers (approvals, personas, messages,
# conversations, studio_*, agent_packages, channel_inbound) still pass PostgREST ISO strings into fields typed
# `datetime`. Their consumers only serialize them today, so nothing breaks yet; route each through db_ts as a batch.
def db_ts(value: object) -> datetime | None:
    """A ``timestamptz`` read back from the store, as a tz-aware ``datetime`` (``None`` stays ``None``).

    The Fake stores hold ``datetime`` objects; PostgREST hands the Real stores an ISO-8601 string. A row
    mapper that passes the string through makes the Fake and the Real disagree on the field's type, and
    the first ``.isoformat()`` or subtraction in prod raises (2026-11-03: a published qualification
    version 500'd every read). Every store row mapper parses through here. An unparseable value raises:
    a timestamp column that is not a timestamp is a data bug, never something to swallow."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
