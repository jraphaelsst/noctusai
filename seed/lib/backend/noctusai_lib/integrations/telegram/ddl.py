"""DDL for the Telegram integration tables, rendered per product schema (WhatsApp precedent).

Authoring-time helper: a product copies ``telegram_tables_sql(schema)`` into its OWN migration (idempotent).
Assumes ``public.current_org_id()`` exists on the target project. Access tiers (``KB § PATTERNS/security/access-tiers.md``;
each table carries a ``COMMENT ... 'tier:<x>'`` and an explicit GRANT/REVOKE):

* ``telegram_lines``            tier:service  -- holds encrypted bot token + webhook secret; browsers never read it
                                                 (org members see lines through a backend route returning last-4 only).
* ``telegram_channels``         tier:org      -- org-member SELECT; writes only via the backend (service role).
* ``telegram_posts``            tier:org      -- org-member SELECT; message_id powers edit/delete (48h window).
* ``telegram_line_events``      tier:service  -- append-only (UPDATE/DELETE refused by trigger and ungranted).
* ``telegram_channel_snapshots``tier:org      -- one row per channel per day (member count); no per-follower PII.
"""
from __future__ import annotations

from noctusai_lib.domain.sql_templates import rls_subquery_policy, service_role_bypass, updated_at_function, updated_at_trigger

TABLES = ("telegram_lines", "telegram_channels", "telegram_posts", "telegram_line_events", "telegram_channel_snapshots")
POST_STATUSES = ("queued", "sent", "edited", "deleted", "expired", "failed")
LINE_STATUSES = ("active", "suspended", "needs_reconnection")


def _checked(schema: str) -> str:
    if not schema or not schema.replace("_", "").isalnum():
        raise ValueError(f"invalid schema name {schema!r}")
    return schema


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _service_only(s: str, t: str) -> str:
    return (f"ALTER TABLE {s}.{t} ENABLE ROW LEVEL SECURITY;\n"
            f"DROP POLICY IF EXISTS service_role_bypass ON {s}.{t};\n{service_role_bypass(t, schema=s)}\n"
            f"REVOKE ALL ON {s}.{t} FROM PUBLIC, anon, authenticated;\n"
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {s}.{t} TO service_role;\n"
            f"COMMENT ON TABLE {s}.{t} IS 'tier:service';")


def _org_read(s: str, t: str) -> str:
    policy = rls_subquery_policy(s, t, f"{t}_select_own_org", "SELECT", using="org_id = current_org_id()")
    return (f"ALTER TABLE {s}.{t} ENABLE ROW LEVEL SECURITY;\n"
            f"DROP POLICY IF EXISTS {t}_select_own_org ON {s}.{t};\n{policy}\n"
            f"DROP POLICY IF EXISTS service_role_bypass ON {s}.{t};\n{service_role_bypass(t, schema=s)}\n"
            f"REVOKE ALL ON {s}.{t} FROM PUBLIC, anon, authenticated;\n"
            f"GRANT SELECT ON {s}.{t} TO authenticated;\n"
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {s}.{t} TO service_role;\n"
            f"COMMENT ON TABLE {s}.{t} IS 'tier:org';")


def telegram_tables_sql(schema: str) -> str:
    s = _checked(schema)
    fn = f"{s}.guard_telegram_line_events_append_only"
    parts = [
        updated_at_function(s),
        # ---- lines (service) ----
        f"""CREATE TABLE IF NOT EXISTS {s}.telegram_lines (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                   UUID NOT NULL,
    created_by               UUID NOT NULL,
    label                    TEXT NOT NULL,
    bot_id                   BIGINT NOT NULL,
    bot_username             TEXT NOT NULL DEFAULT '',
    encrypted_bot_token      TEXT NOT NULL,
    token_last4              TEXT NOT NULL,
    webhook_token            TEXT NOT NULL,
    encrypted_webhook_secret TEXT NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'active' CHECK (status IN ({_in(LINE_STATUSES)})),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, label)
);
CREATE UNIQUE INDEX IF NOT EXISTS telegram_lines_bot_id_uq ON {s}.telegram_lines (bot_id);
CREATE UNIQUE INDEX IF NOT EXISTS telegram_lines_webhook_token_uq ON {s}.telegram_lines (webhook_token);
CREATE INDEX IF NOT EXISTS telegram_lines_org_idx ON {s}.telegram_lines (org_id, created_at DESC);
{updated_at_trigger(s, "telegram_lines")}
{_service_only(s, "telegram_lines")}""",
        # ---- channels (org read) ----
        f"""CREATE TABLE IF NOT EXISTS {s}.telegram_channels (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    line_id      UUID NOT NULL REFERENCES {s}.telegram_lines (id) ON DELETE CASCADE,
    chat_id      BIGINT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    username     TEXT,
    bot_can_post BOOLEAN NOT NULL DEFAULT false,
    verified_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (line_id, chat_id)
);
CREATE INDEX IF NOT EXISTS telegram_channels_org_idx ON {s}.telegram_channels (org_id);
{updated_at_trigger(s, "telegram_channels")}
{_org_read(s, "telegram_channels")}""",
        # ---- posts (org read) ----
        f"""CREATE TABLE IF NOT EXISTS {s}.telegram_posts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    channel_id      UUID NOT NULL REFERENCES {s}.telegram_channels (id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    source_ref      TEXT,
    message_id      BIGINT,
    status          TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ({_in(POST_STATUSES)})),
    text_sha256     TEXT,
    error_code      TEXT,
    sent_at         TIMESTAMPTZ,
    delete_deadline TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS telegram_posts_channel_idx ON {s}.telegram_posts (channel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS telegram_posts_deadline_idx ON {s}.telegram_posts (delete_deadline) WHERE status IN ('sent', 'edited');
{updated_at_trigger(s, "telegram_posts")}
{_org_read(s, "telegram_posts")}""",
        # ---- line events (service, append-only) ----
        f"""CREATE TABLE IF NOT EXISTS {s}.telegram_line_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event       TEXT NOT NULL,
    line_id     UUID NOT NULL,
    org_id      UUID,
    reason      TEXT NOT NULL DEFAULT '',
    detail      JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS telegram_line_events_line_idx ON {s}.telegram_line_events (line_id, occurred_at DESC);
ALTER TABLE {s}.telegram_line_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS service_role_select ON {s}.telegram_line_events;
CREATE POLICY service_role_select ON {s}.telegram_line_events FOR SELECT TO service_role USING (true);
DROP POLICY IF EXISTS service_role_insert ON {s}.telegram_line_events;
CREATE POLICY service_role_insert ON {s}.telegram_line_events FOR INSERT TO service_role WITH CHECK (true);
REVOKE ALL ON {s}.telegram_line_events FROM PUBLIC, anon, authenticated;
REVOKE UPDATE, DELETE, TRUNCATE ON {s}.telegram_line_events FROM service_role;
GRANT SELECT, INSERT ON {s}.telegram_line_events TO service_role;
COMMENT ON TABLE {s}.telegram_line_events IS 'tier:service';

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
DROP TRIGGER IF EXISTS guard_telegram_line_events_append_only ON {s}.telegram_line_events;
CREATE TRIGGER guard_telegram_line_events_append_only
    BEFORE UPDATE OR DELETE ON {s}.telegram_line_events
    FOR EACH ROW EXECUTE FUNCTION {fn}();""",
        # ---- daily snapshots (org read) ----
        f"""CREATE TABLE IF NOT EXISTS {s}.telegram_channel_snapshots (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    channel_id   UUID NOT NULL REFERENCES {s}.telegram_channels (id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    member_count INTEGER NOT NULL CHECK (member_count >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS telegram_channel_snapshots_org_idx ON {s}.telegram_channel_snapshots (org_id, snapshot_date DESC);
{_org_read(s, "telegram_channel_snapshots")}""",
    ]
    return "\n\n".join(parts)
