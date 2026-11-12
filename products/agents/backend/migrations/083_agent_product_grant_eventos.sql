-- ============================================================================
-- 083_agent_product_grant_eventos.sql -- the platform grant ledger records its lifecycle (EOA E1, measurable by design).
--
-- A grant (060) is one (org, agent, product) with its own personal channel token and its own product tools token.
-- Its `status` (pendente -> ativo | falhou ; ativo -> revogado) and token pair change in place, so the row only answers
-- "where is it now". This migration appends one immutable event per lifecycle change, IN THE SAME TRANSACTION as the
-- change: a trigger on agent_product_grants, so no writer (the Supabase store, a manual fix, a future RPC) can forget
-- it. Interim hand-written shape (scaffold_migration with_eventos) until the EOA E1 transition_log primitive is on dev.
--
--   event_type  grant_criado              INSERT (de NULL, para = the initial status), actor = created_by
--               grant_ativado             status -> ativo
--               grant_falhou              status -> falhou (dados.erro = last_error, never a secret)
--               grant_revogado            status -> revogado, actor = revoked_by
--               grant_tokens_rotacionados status unchanged, channel/product token id changed (a rotation)
--               estado_importado          one row per grant that existed before this migration (backfill; occurred
--                                         now, para = its current status) -- history before 083 is not reconstructed
--   dados       token IDS only (api_tokens.id); a token secret never exists in this database.
--
-- Access tier: both tables are Platform IP (platform-admin control plane): tier:platform, RLS on, service role only,
-- no grant to anon / authenticated. The event table is append-only for everybody (trigger refuses UPDATE / DELETE).
--
-- Backward compatible with the previous image: N-1 never reads the new table; its writes simply gain an event row.
-- Forward-only + idempotent (applies twice on the replay).
-- ============================================================================

SET search_path = agents, public;

SET LOCAL lock_timeout = '5s';

COMMENT ON TABLE agents.agent_product_grants IS 'tier:platform';

CREATE TABLE IF NOT EXISTS agents.agent_product_grant_eventos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq         BIGINT GENERATED ALWAYS AS IDENTITY,
    grant_id    UUID NOT NULL REFERENCES agents.agent_product_grants(id) ON DELETE RESTRICT,
    org_id      UUID NOT NULL,
    agent_key   TEXT NOT NULL,
    product     TEXT NOT NULL,
    event_type  TEXT NOT NULL CHECK (event_type IN (
                    'grant_criado', 'grant_ativado', 'grant_falhou', 'grant_revogado',
                    'grant_tokens_rotacionados', 'estado_importado')),
    de          TEXT NULL,
    para        TEXT NULL,
    dados       JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_id    UUID NULL,
    actor_kind  TEXT NOT NULL DEFAULT 'system' CHECK (actor_kind IN ('user', 'agent', 'system', 'integration')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_product_grant_eventos_grant
    ON agents.agent_product_grant_eventos (grant_id, seq);
CREATE INDEX IF NOT EXISTS idx_agent_product_grant_eventos_org
    ON agents.agent_product_grant_eventos (org_id, occurred_at DESC);

ALTER TABLE agents.agent_product_grant_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_product_grant_eventos;
CREATE POLICY "service_role_bypass" ON agents.agent_product_grant_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.agent_product_grant_eventos FROM anon, authenticated;
COMMENT ON TABLE agents.agent_product_grant_eventos IS 'tier:platform';

-- ----- append-only (function and trigger share one name: the guard name the DB-guard probe proves) -----
CREATE OR REPLACE FUNCTION agents.guard_agent_product_grant_eventos_append_only() RETURNS trigger LANGUAGE plpgsql
SET search_path = agents, public AS $$
BEGIN
    RAISE EXCEPTION 'agent_product_grant_eventos is append-only';
END;
$$;
REVOKE ALL ON FUNCTION agents.guard_agent_product_grant_eventos_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_agent_product_grant_eventos_append_only ON agents.agent_product_grant_eventos;
CREATE TRIGGER guard_agent_product_grant_eventos_append_only
    BEFORE UPDATE OR DELETE ON agents.agent_product_grant_eventos
    FOR EACH ROW EXECUTE FUNCTION agents.guard_agent_product_grant_eventos_append_only();

-- ----- the capture: one event per lifecycle change, same transaction -----
CREATE OR REPLACE FUNCTION agents.agent_product_grants_registrar_evento() RETURNS trigger LANGUAGE plpgsql
SET search_path = agents, public AS $$
DECLARE
    v_tipo  TEXT;
    v_actor UUID;
    v_dados JSONB;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_tipo := 'grant_criado';
        v_actor := NEW.created_by;
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        v_tipo := CASE NEW.status
            WHEN 'ativo' THEN 'grant_ativado'
            WHEN 'falhou' THEN 'grant_falhou'
            WHEN 'revogado' THEN 'grant_revogado'
        END;
        -- Any other transition (e.g. back to pendente) has no event type: event_type NOT NULL refuses the change, so
        -- an unmodelled lifecycle step can never happen silently.
        IF NEW.status = 'revogado' THEN
            v_actor := NEW.revoked_by;
        END IF;
    ELSIF NEW.channel_token_id IS DISTINCT FROM OLD.channel_token_id
       OR NEW.product_token_id IS DISTINCT FROM OLD.product_token_id THEN
        v_tipo := 'grant_tokens_rotacionados';
    ELSE
        RETURN NEW;  -- not a lifecycle change (last_error, last_delivered_at, especificacoes_editor ...)
    END IF;

    v_dados := jsonb_strip_nulls(jsonb_build_object(
        'channel_token_id', NEW.channel_token_id,
        'product_token_id', NEW.product_token_id,
        'expires_at', NEW.expires_at,
        'erro', CASE WHEN NEW.status = 'falhou' THEN NEW.last_error END
    ));

    INSERT INTO agents.agent_product_grant_eventos
        (grant_id, org_id, agent_key, product, event_type, de, para, dados, actor_id, actor_kind)
    VALUES
        (NEW.id, NEW.org_id, NEW.agent_key, NEW.product, v_tipo,
         CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.status END, NEW.status, v_dados,
         v_actor, CASE WHEN v_actor IS NULL THEN 'system' ELSE 'user' END);
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION agents.agent_product_grants_registrar_evento() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS agent_product_grants_eventos ON agents.agent_product_grants;
CREATE TRIGGER agent_product_grants_eventos
    AFTER INSERT OR UPDATE OF status, channel_token_id, product_token_id ON agents.agent_product_grants
    FOR EACH ROW EXECUTE FUNCTION agents.agent_product_grants_registrar_evento();

-- ----- backfill: the current state of every pre-existing grant, once -----
INSERT INTO agents.agent_product_grant_eventos (grant_id, org_id, agent_key, product, event_type, de, para, dados)
SELECT g.id, g.org_id, g.agent_key, g.product, 'estado_importado', NULL, g.status,
       jsonb_build_object('backfill', true, 'grant_created_at', g.created_at)
  FROM agents.agent_product_grants g
 WHERE NOT EXISTS (SELECT 1 FROM agents.agent_product_grant_eventos e WHERE e.grant_id = g.id);
