-- ============================================================================
-- 089_onboarding_sessoes.sql -- the onboarding interviewer's session + its append-only event ledger (EOA, measurable).
--
-- A STAFF member chooses a client org (one with a live grant) and starts an interview: one agents.conversations row of
-- the `onboarding-imob` agent in the staff's own org, bound here to the TARGET org + the client agent definition whose
-- org specs the interview fills. The model never names an org: the tools read the target from this row by conversation.
--
-- onboarding_eventos is the interview's memory: one immutable, intent-named row per answer / refusal / pending mark /
-- import proposal / summary / apply. The per-item state the Onboarding tab polls is a FOLD of these rows (latest per
-- item), never a mutable column. Values are the client's business data: kept in `dados`, never logged.
--
-- conversation_id carries no FK on purpose: the ledger is append-only, so a conversation purge must not cascade into it.
-- Access tier: both tables Platform IP (platform-admin control plane): tier:platform, RLS on, service role only.
-- Forward-only + idempotent; N-1 never reads them.
-- ============================================================================

SET search_path = agents, public;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS agents.onboarding_sessoes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,                       -- the STAFF org that owns the conversation
    conversation_id UUID NOT NULL,
    alvo_org_id     UUID NOT NULL,                       -- the CLIENT org being onboarded
    agent_key       TEXT NOT NULL,                       -- the client agent definition whose org specs are filled
    product         TEXT NOT NULL,
    grant_id        UUID NOT NULL,
    created_by      UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id)
);
CREATE INDEX IF NOT EXISTS idx_onboarding_sessoes_alvo
    ON agents.onboarding_sessoes (alvo_org_id, agent_key, created_at DESC);

-- transition-log-ok: onboarding_eventos intent-named interview ledger (answers/refusals/imports/summary/apply) with a per-item fold, not a single state row + from/to transition pair
CREATE TABLE IF NOT EXISTS agents.onboarding_eventos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq         BIGINT GENERATED ALWAYS AS IDENTITY,
    sessao_id   UUID NOT NULL REFERENCES agents.onboarding_sessoes(id) ON DELETE RESTRICT,
    event_type  TEXT NOT NULL CHECK (event_type IN (
                    'resposta_registrada', 'resposta_recusada', 'item_marcado_pendente',
                    'importacao_proposta', 'resumo_apresentado', 'aplicacao_executada')),
    item_n      INT NULL CHECK (item_n IS NULL OR item_n BETWEEN 1 AND 99),
    dados       JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor_id    UUID NULL,
    actor_kind  TEXT NOT NULL DEFAULT 'agent' CHECK (actor_kind IN ('user', 'agent', 'system')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_onboarding_eventos_sessao ON agents.onboarding_eventos (sessao_id, seq);

ALTER TABLE agents.onboarding_sessoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents.onboarding_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.onboarding_sessoes;
CREATE POLICY "service_role_bypass" ON agents.onboarding_sessoes FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "service_role_bypass" ON agents.onboarding_eventos;
CREATE POLICY "service_role_bypass" ON agents.onboarding_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.onboarding_sessoes FROM anon, authenticated;
REVOKE ALL ON agents.onboarding_eventos FROM anon, authenticated;
COMMENT ON TABLE agents.onboarding_sessoes IS 'tier:platform';
COMMENT ON TABLE agents.onboarding_eventos IS 'tier:platform';

-- append-only for everybody (function and trigger share one name: the guard name the DB-guard probe proves)
CREATE OR REPLACE FUNCTION agents.guard_onboarding_eventos_append_only() RETURNS trigger LANGUAGE plpgsql
SET search_path = agents, public AS $$
BEGIN
    RAISE EXCEPTION 'onboarding_eventos is append-only';
END;
$$;
REVOKE ALL ON FUNCTION agents.guard_onboarding_eventos_append_only() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS guard_onboarding_eventos_append_only ON agents.onboarding_eventos;
CREATE TRIGGER guard_onboarding_eventos_append_only
    BEFORE UPDATE OR DELETE ON agents.onboarding_eventos
    FOR EACH ROW EXECUTE FUNCTION agents.guard_onboarding_eventos_append_only();
