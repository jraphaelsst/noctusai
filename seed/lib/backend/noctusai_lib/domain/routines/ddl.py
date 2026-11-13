"""Routines DDL for one product schema -- ``routines_tables_sql(schema)`` (migration-authoring helper).

Pure string emission; applying it is a migration decision (``noctus.dev.scaffold_migration``
+ ``migrate_product``). Three tables:

* ``routines``                -- org-scoped definitions (cron, mode, ``ativo``, ``killed``, ``config`` jsonb).
* ``routine_master_switches`` -- the per-product MASTER switch, one row per org (absent = on).
* ``routine_events``          -- append-only log (trigger blocks UPDATE/DELETE; ``service_role`` UPDATE/DELETE/TRUNCATE revoked).

Every state change goes through a SECURITY DEFINER function that changes the row AND
inserts its event in ONE transaction (EOA). The functions are EXECUTE-revoked from
PUBLIC / anon / authenticated and granted to ``service_role`` only. Tables are
RLS deny-by-default, browser-revoked, and declare ``tier:org`` (served through the
org-admin-gated router; PostgREST never exposes them to browser roles).
"""
from __future__ import annotations

import re

from noctusai_lib.domain.routines.types import EVENT_KINDS, MODES

_SCHEMA_RE = re.compile(r"[a-z_][a-z0-9_]*")


def _lits(values: tuple[str, ...]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


_SQL = """
CREATE TABLE IF NOT EXISTS {s}.routines (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    name        TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    cron        TEXT NOT NULL,
    mode        TEXT NOT NULL DEFAULT 'trigger' CHECK (mode IN (__MODES__)),
    ativo       BOOLEAN NOT NULL DEFAULT false,
    killed      BOOLEAN NOT NULL DEFAULT false,
    config      JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT routines_org_name_key UNIQUE (org_id, name),
    CONSTRAINT routines_killed_not_ativo CHECK (NOT (killed AND ativo))
);
CREATE INDEX IF NOT EXISTS routines_runnable_idx ON {s}.routines (org_id) WHERE ativo AND NOT killed;

CREATE TABLE IF NOT EXISTS {s}.routine_master_switches (
    org_id      UUID PRIMARY KEY,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {s}.routine_events (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      UUID NOT NULL,
    routine_id  UUID REFERENCES {s}.routines(id),
    scope       TEXT NOT NULL CHECK (scope IN ('routine', 'master')),
    kind        TEXT NOT NULL CHECK (kind IN (__KINDS__)),
    actor_id    UUID NOT NULL,
    reason      TEXT,
    detail      JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT routine_events_scope_ck CHECK ((scope = 'master') = (routine_id IS NULL)),
    CONSTRAINT routine_events_reason_ck CHECK (
        kind NOT IN ('enabled', 'disabled', 'killed', 'rejected') OR length(btrim(coalesce(reason, ''))) > 0
    )
);
CREATE INDEX IF NOT EXISTS routine_events_org_time_idx ON {s}.routine_events (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS routine_events_routine_idx ON {s}.routine_events (routine_id, id);

CREATE OR REPLACE FUNCTION {s}.routine_events_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = {s}, pg_temp AS $fn$
BEGIN
    RAISE EXCEPTION 'routines_event_append_only' USING ERRCODE = 'P0001';
END
$fn$;
DROP TRIGGER IF EXISTS routine_events_no_mutate ON {s}.routine_events;
CREATE TRIGGER routine_events_no_mutate BEFORE UPDATE OR DELETE ON {s}.routine_events
    FOR EACH ROW EXECUTE FUNCTION {s}.routine_events_append_only();

ALTER TABLE {s}.routines ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.routine_master_switches ENABLE ROW LEVEL SECURITY;
ALTER TABLE {s}.routine_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON {s}.routines FROM PUBLIC, anon, authenticated;
REVOKE ALL ON {s}.routine_master_switches FROM PUBLIC, anon, authenticated;
REVOKE ALL ON {s}.routine_events FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON {s}.routines TO service_role;
GRANT SELECT, INSERT, UPDATE ON {s}.routine_master_switches TO service_role;
GRANT SELECT, INSERT ON {s}.routine_events TO service_role;
REVOKE UPDATE, DELETE, TRUNCATE ON {s}.routine_events FROM service_role;

COMMENT ON TABLE {s}.routines IS 'tier:org';
COMMENT ON TABLE {s}.routine_master_switches IS 'tier:org';
COMMENT ON TABLE {s}.routine_events IS 'tier:org';

-- every mutation = row change + its event, one transaction ---------------------------------

CREATE OR REPLACE FUNCTION {s}.routines_create(
    p_org_id UUID, p_actor_id UUID, p_name TEXT, p_cron TEXT, p_mode TEXT, p_config JSONB
) RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = {s}, pg_temp AS $fn$
DECLARE v_id UUID;
BEGIN
    INSERT INTO {s}.routines (org_id, name, cron, mode, config)
    VALUES (p_org_id, btrim(p_name), p_cron, p_mode, coalesce(p_config, '{{}}'::jsonb))
    RETURNING id INTO v_id;
    INSERT INTO {s}.routine_events (org_id, routine_id, scope, kind, actor_id, detail)
    VALUES (p_org_id, v_id, 'routine', 'created', p_actor_id,
            jsonb_build_object('name', btrim(p_name), 'cron', p_cron, 'mode', p_mode));
    RETURN v_id;
END
$fn$;

CREATE OR REPLACE FUNCTION {s}.routines_update(
    p_org_id UUID, p_id UUID, p_actor_id UUID, p_name TEXT, p_cron TEXT, p_config JSONB,
    p_mode TEXT, p_reason TEXT
) RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = {s}, pg_temp AS $fn$
DECLARE r {s}.routines%ROWTYPE; v_changed TEXT[] := '{{}}'::text[];
BEGIN
    SELECT * INTO r FROM {s}.routines WHERE id = p_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'routines_not_found' USING ERRCODE = 'P0001'; END IF;
    IF p_name IS NOT NULL AND btrim(p_name) <> r.name THEN v_changed := v_changed || 'name'::text; END IF;
    IF p_cron IS NOT NULL AND p_cron <> r.cron THEN v_changed := v_changed || 'cron'::text; END IF;
    IF p_config IS NOT NULL AND p_config <> r.config THEN v_changed := v_changed || 'config'::text; END IF;
    IF array_length(v_changed, 1) IS NOT NULL THEN
        UPDATE {s}.routines SET name = coalesce(btrim(p_name), name), cron = coalesce(p_cron, cron),
               config = coalesce(p_config, config), updated_at = now() WHERE id = p_id;
        INSERT INTO {s}.routine_events (org_id, routine_id, scope, kind, actor_id, reason, detail)
        VALUES (p_org_id, p_id, 'routine', 'edited', p_actor_id, nullif(btrim(p_reason), ''),
                jsonb_build_object('changed', to_jsonb(v_changed)));
    END IF;
    IF p_mode IS NOT NULL AND p_mode <> r.mode THEN
        UPDATE {s}.routines SET mode = p_mode, updated_at = now() WHERE id = p_id;
        INSERT INTO {s}.routine_events (org_id, routine_id, scope, kind, actor_id, reason, detail)
        VALUES (p_org_id, p_id, 'routine', 'mode_changed', p_actor_id, nullif(btrim(p_reason), ''),
                jsonb_build_object('from', r.mode, 'to', p_mode));
    END IF;
    RETURN p_id;
END
$fn$;

CREATE OR REPLACE FUNCTION {s}.routines_set_enabled(
    p_org_id UUID, p_id UUID, p_actor_id UUID, p_enabled BOOLEAN, p_reason TEXT
) RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = {s}, pg_temp AS $fn$
DECLARE r {s}.routines%ROWTYPE;
BEGIN
    SELECT * INTO r FROM {s}.routines WHERE id = p_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'routines_not_found' USING ERRCODE = 'P0001'; END IF;
    IF r.ativo = p_enabled AND NOT (p_enabled AND r.killed) THEN RETURN p_id; END IF;
    UPDATE {s}.routines SET ativo = p_enabled, killed = CASE WHEN p_enabled THEN false ELSE killed END,
           updated_at = now() WHERE id = p_id;
    INSERT INTO {s}.routine_events (org_id, routine_id, scope, kind, actor_id, reason)
    VALUES (p_org_id, p_id, 'routine', CASE WHEN p_enabled THEN 'enabled' ELSE 'disabled' END,
            p_actor_id, p_reason);
    RETURN p_id;
END
$fn$;

CREATE OR REPLACE FUNCTION {s}.routines_kill(
    p_org_id UUID, p_id UUID, p_actor_id UUID, p_reason TEXT
) RETURNS UUID LANGUAGE plpgsql SECURITY DEFINER SET search_path = {s}, pg_temp AS $fn$
DECLARE r {s}.routines%ROWTYPE;
BEGIN
    SELECT * INTO r FROM {s}.routines WHERE id = p_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'routines_not_found' USING ERRCODE = 'P0001'; END IF;
    IF r.killed THEN RETURN p_id; END IF;
    UPDATE {s}.routines SET ativo = false, killed = true, updated_at = now() WHERE id = p_id;
    INSERT INTO {s}.routine_events (org_id, routine_id, scope, kind, actor_id, reason)
    VALUES (p_org_id, p_id, 'routine', 'killed', p_actor_id, p_reason);
    RETURN p_id;
END
$fn$;

CREATE OR REPLACE FUNCTION {s}.routines_set_master(
    p_org_id UUID, p_actor_id UUID, p_enabled BOOLEAN, p_reason TEXT
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = {s}, pg_temp AS $fn$
DECLARE v_cur BOOLEAN;
BEGIN
    SELECT enabled INTO v_cur FROM {s}.routine_master_switches WHERE org_id = p_org_id FOR UPDATE;
    IF FOUND AND v_cur = p_enabled THEN RETURN p_enabled; END IF;
    INSERT INTO {s}.routine_master_switches (org_id, enabled) VALUES (p_org_id, p_enabled)
    ON CONFLICT (org_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = now();
    INSERT INTO {s}.routine_events (org_id, routine_id, scope, kind, actor_id, reason)
    VALUES (p_org_id, NULL, 'master', CASE WHEN p_enabled THEN 'enabled' ELSE 'disabled' END,
            p_actor_id, p_reason);
    RETURN p_enabled;
END
$fn$;

REVOKE EXECUTE ON FUNCTION {s}.routines_create(UUID, UUID, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION {s}.routines_update(UUID, UUID, UUID, TEXT, TEXT, JSONB, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION {s}.routines_set_enabled(UUID, UUID, UUID, BOOLEAN, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION {s}.routines_kill(UUID, UUID, UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION {s}.routines_set_master(UUID, UUID, BOOLEAN, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION {s}.routines_create(UUID, UUID, TEXT, TEXT, TEXT, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION {s}.routines_update(UUID, UUID, UUID, TEXT, TEXT, JSONB, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION {s}.routines_set_enabled(UUID, UUID, UUID, BOOLEAN, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION {s}.routines_kill(UUID, UUID, UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION {s}.routines_set_master(UUID, UUID, BOOLEAN, TEXT) TO service_role;
"""


def routines_tables_sql(schema: str) -> str:
    """Emit the routines DDL for ``schema`` (a plain lower-case identifier -- it is interpolated)."""
    if not _SCHEMA_RE.fullmatch(schema or ""):
        raise ValueError(f"invalid schema name {schema!r}")
    return (
        _SQL.replace("__MODES__", _lits(MODES)).replace("__KINDS__", _lits(EVENT_KINDS)).format(s=schema)
    )


__all__ = ["routines_tables_sql"]
