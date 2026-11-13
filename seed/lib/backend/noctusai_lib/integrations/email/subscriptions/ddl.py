"""Per-product-schema DDL of the e-mail audience: ``subscribers``, ``suppression``, ``subscriber_events``.

Each table is SERVICE ROLE ONLY (``COMMENT ... 'tier:service'``): no ``anon``/``authenticated``
grant. ``suppression`` stores only the sha256 of the normalised address. ``subscriber_events`` is
append-only (trigger + no UPDATE/DELETE grant). No IP column anywhere (IP-free consent). Idempotent.
Render into a product migration with ``noctus.dev.scaffold_migration``.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import _checked_schema

from .types import EVENT_KINDS, STATUSES, SUPPRESSION_REASONS


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def email_audience_tables_sql(schema: str) -> str:
    s = _checked_schema(schema)
    fn = f"{s}.guard_subscriber_events_append_only"
    return f"""CREATE TABLE IF NOT EXISTS {s}.subscribers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    email_hash      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ({_in(STATUSES)})),
    consent_source  TEXT NOT NULL DEFAULT '',
    consent_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at    TIMESTAMPTZ,
    unsubscribed_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS subscribers_email_hash_uidx ON {s}.subscribers (email_hash);
CREATE INDEX IF NOT EXISTS subscribers_status_idx ON {s}.subscribers (status);
ALTER TABLE {s}.subscribers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_all ON {s}.subscribers;
CREATE POLICY service_role_all ON {s}.subscribers FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON {s}.subscribers FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON {s}.subscribers TO service_role;
COMMENT ON TABLE {s}.subscribers IS 'tier:service';

CREATE TABLE IF NOT EXISTS {s}.suppression (
    email_hash TEXT PRIMARY KEY,
    reason     TEXT NOT NULL CHECK (reason IN ({_in(SUPPRESSION_REASONS)})),
    source     TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE {s}.suppression ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_all ON {s}.suppression;
CREATE POLICY service_role_all ON {s}.suppression FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON {s}.suppression FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON {s}.suppression TO service_role;
COMMENT ON TABLE {s}.suppression IS 'tier:service';

CREATE TABLE IF NOT EXISTS {s}.subscriber_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscriber_id UUID NOT NULL REFERENCES {s}.subscribers(id),
    kind          TEXT NOT NULL CHECK (kind IN ({_in(EVENT_KINDS)})),
    detail        JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS subscriber_events_sub_idx ON {s}.subscriber_events (subscriber_id, occurred_at);
ALTER TABLE {s}.subscriber_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_select ON {s}.subscriber_events;
CREATE POLICY service_role_select ON {s}.subscriber_events FOR SELECT TO service_role USING (true);
DROP POLICY IF EXISTS service_role_insert ON {s}.subscriber_events;
CREATE POLICY service_role_insert ON {s}.subscriber_events FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON {s}.subscriber_events FROM PUBLIC, anon, authenticated;
REVOKE UPDATE, DELETE, TRUNCATE ON {s}.subscriber_events FROM service_role;
GRANT SELECT, INSERT ON {s}.subscriber_events TO service_role;
COMMENT ON TABLE {s}.subscriber_events IS 'tier:service';

CREATE OR REPLACE FUNCTION {fn}()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = {s}, public
AS $$
BEGIN
    RAISE EXCEPTION 'append_only' USING ERRCODE = 'P0001';
END;
$$;
REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {fn}() TO service_role;
DROP TRIGGER IF EXISTS guard_subscriber_events_append_only ON {s}.subscriber_events;
CREATE TRIGGER guard_subscriber_events_append_only
    BEFORE UPDATE OR DELETE ON {s}.subscriber_events
    FOR EACH ROW EXECUTE FUNCTION {fn}();"""


__all__ = ["email_audience_tables_sql"]
