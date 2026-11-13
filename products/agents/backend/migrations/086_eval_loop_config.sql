-- 086_eval_loop_config.sql -- the eval-loop CONFIG (owner 2026-11-12): "Target 95% · Cap at U$5" and "let me set the number of
-- rounds for requested loops as a config ... so it also stops at max iterations".
--
-- Platform-level (loops run on platform agents): ONE set of values, edited by a platform admin, read when a loop is opened.
--   eval_loop_alvo          target, 0 < x <= 1                (default 0.95; frozen onto each loop at start, like `piso`)
--   eval_loop_orcamento_usd the per-loop budget CAP, > 0      (default 5.00; no loop may exceed it, admin included)
--   eval_loop_rodadas_max   max planned rounds, 1..100        (default 10; omitted rounds => this; given rounds <= this)
-- Defaults live in code (app/studio/eval_loop_config.py) and apply while no row exists; the owner's edit creates the rows.
--
-- REUSES agents.runtime_settings (010; platform-wide key/value, service-role only, edited by platform admins) as the store:
-- three new keys. The change is an EVENT, not a hand-written history table: agents.set_eval_loop_config writes the three
-- rows AND one immutable `loop_config_alterada` event (before/after, actor) in ONE transaction. Events are append-only.
-- Tier: platform (service role only; no grant to anon / authenticated). Forward-only + idempotent.

SET search_path = agents, public;

-- 1 . the three keys, with value bounds as the backstop of the API validation -------------------------------------
ALTER TABLE agents.runtime_settings DROP CONSTRAINT IF EXISTS runtime_settings_key_check;
ALTER TABLE agents.runtime_settings ADD CONSTRAINT runtime_settings_key_check
    CHECK (key IN ('approval_timeout_seconds', 'max_turns', 'messages_rate_limit', 'numero_fallback_atendimento',
                   'eval_loop_alvo', 'eval_loop_orcamento_usd', 'eval_loop_rodadas_max'));

ALTER TABLE agents.runtime_settings DROP CONSTRAINT IF EXISTS runtime_settings_eval_loop_valores;
ALTER TABLE agents.runtime_settings ADD CONSTRAINT runtime_settings_eval_loop_valores
    CHECK (
        (key <> 'eval_loop_alvo'
            OR (jsonb_typeof(value) = 'number' AND (value #>> '{}')::numeric > 0 AND (value #>> '{}')::numeric <= 1))
        AND (key <> 'eval_loop_orcamento_usd'
            OR (jsonb_typeof(value) = 'number' AND (value #>> '{}')::numeric > 0 AND (value #>> '{}')::numeric <= 500))
        AND (key <> 'eval_loop_rodadas_max'
            OR (jsonb_typeof(value) = 'number' AND (value #>> '{}')::numeric >= 1 AND (value #>> '{}')::numeric <= 100
                AND (value #>> '{}')::numeric = trunc((value #>> '{}')::numeric)))
    );

-- 2 . the events (append-only) -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents.eval_loop_config_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento TEXT NOT NULL CHECK (evento IN ('loop_config_alterada')),
    antes JSONB NOT NULL,
    depois JSONB NOT NULL,
    actor_id UUID NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_eval_loop_config_eventos_quando ON agents.eval_loop_config_eventos (occurred_at DESC);

CREATE OR REPLACE FUNCTION agents.guard_eval_loop_config_eventos_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public
AS $$ BEGIN RAISE EXCEPTION 'eval_loop_config_eventos is append-only'; END; $$;
REVOKE ALL ON FUNCTION agents.guard_eval_loop_config_eventos_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_eval_loop_config_eventos_append_only ON agents.eval_loop_config_eventos;
CREATE TRIGGER guard_eval_loop_config_eventos_append_only
    BEFORE UPDATE OR DELETE ON agents.eval_loop_config_eventos
    FOR EACH ROW EXECUTE FUNCTION agents.guard_eval_loop_config_eventos_append_only();

COMMENT ON TABLE agents.eval_loop_config_eventos IS 'tier:platform';
ALTER TABLE agents.eval_loop_config_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.eval_loop_config_eventos;
CREATE POLICY "service_role_bypass" ON agents.eval_loop_config_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.eval_loop_config_eventos FROM anon, authenticated;

-- 3 . the change + its event, one transaction -----------------------------------------------------------------------
-- The caller (the API) has validated the bounds; the CHECKs above are the backstop. Absent keys read as the code defaults
-- (0.95 / 5.00 / 10) in `antes`, so the first edit records what it replaced. An edit that changes nothing writes nothing.
CREATE OR REPLACE FUNCTION agents.set_eval_loop_config(
    p_alvo NUMERIC,
    p_orcamento_usd NUMERIC,
    p_rodadas_max INT,
    p_actor UUID
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = agents, public
AS $$
DECLARE
    v_antes JSONB;
    v_depois JSONB;
BEGIN
    SELECT jsonb_build_object(
        'alvo', COALESCE((SELECT (value #>> '{}')::numeric FROM agents.runtime_settings WHERE key = 'eval_loop_alvo'), 0.95),
        'orcamento_usd', COALESCE((SELECT (value #>> '{}')::numeric FROM agents.runtime_settings WHERE key = 'eval_loop_orcamento_usd'), 5.00),
        'rodadas_max', COALESCE((SELECT (value #>> '{}')::int FROM agents.runtime_settings WHERE key = 'eval_loop_rodadas_max'), 10)
    ) INTO v_antes;
    v_depois := jsonb_build_object('alvo', p_alvo, 'orcamento_usd', p_orcamento_usd, 'rodadas_max', p_rodadas_max);

    INSERT INTO agents.runtime_settings (key, value, updated_by, updated_at) VALUES
        ('eval_loop_alvo', to_jsonb(p_alvo), p_actor, now()),
        ('eval_loop_orcamento_usd', to_jsonb(p_orcamento_usd), p_actor, now()),
        ('eval_loop_rodadas_max', to_jsonb(p_rodadas_max), p_actor, now())
    ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at;

    IF v_antes IS DISTINCT FROM v_depois THEN
        INSERT INTO agents.eval_loop_config_eventos (evento, antes, depois, actor_id)
        VALUES ('loop_config_alterada', v_antes, v_depois, p_actor);
    END IF;
    RETURN v_depois;
END;
$$;

REVOKE ALL ON FUNCTION agents.set_eval_loop_config(NUMERIC, NUMERIC, INT, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION agents.set_eval_loop_config(NUMERIC, NUMERIC, INT, UUID) TO service_role;
