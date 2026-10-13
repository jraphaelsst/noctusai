"""`event_inbox_table_sql(schema)` — the DDL `RealSupabaseEventInbox` expects.

`event_inbox.RealSupabaseEventInbox` documented its table as a comment and left
every consumer to retype it. This is that comment made executable, so a product
(or a vertical organ such as `domain/commerce`) renders the table into its own
schema instead of copying a snippet.

The table is keyed by `(gateway, event_id)` — the PRIMARY KEY IS the
idempotency guarantee (`claim` INSERTs and reads a `23505` as "already
claimed"). It is deliberately NOT org-scoped: a gateway event id is unique per
gateway, and the Real inbox inserts only `(gateway, event_id, claimed_at)`.
RLS is on with a `service_role_bypass` policy only — `authenticated` has no
policy, so the table is deny-all to everyone but the backend.

Re-runnable (`IF NOT EXISTS`, `DROP POLICY IF EXISTS`). Pure string emission.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import service_role_bypass

DEFAULT_EVENT_INBOX_TABLE = "payment_gateway_events"


def event_inbox_table_sql(schema: str, *, table: str = DEFAULT_EVENT_INBOX_TABLE) -> str:
    """The `payment_gateway_events` table for `schema` (default table name matches
    `make_event_inbox`'s default)."""
    if not schema or not schema.strip():
        raise ValueError("event_inbox_table_sql requires a non-empty schema")
    return f"""CREATE TABLE IF NOT EXISTS {schema}.{table} (
    gateway     TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    claimed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (gateway, event_id)
);
ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON {schema}.{table};
{service_role_bypass(table, schema=schema)}"""


__all__ = ["DEFAULT_EVENT_INBOX_TABLE", "event_inbox_table_sql"]
