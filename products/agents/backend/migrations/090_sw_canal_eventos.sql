-- 090_sw_canal_eventos.sql -- the onboarding interviewer's channel to social-wiring is MEASURED (owner 2026-11-18).
--
-- The service token (scope social-wiring:onboarding-settings, issuer noctus-platform) is provisioned and rotated by agents
-- itself; nobody creates or pastes it. Every provisioning, rotation, connection test and apply call is an append-only,
-- intent-named event here, so the Studio card "Conexao com o Social Wiring" can show the last success and the last error
-- (time + reason) without ever holding or returning the secret: NO column of this table can carry a token value.
-- Tier: Platform IP (service role only). Forward-only + idempotent.

SET search_path = agents, public;

-- transition-log-ok: sw_canal_eventos IS the lifecycle log of the channel credential (its state is the stored token + the social-wiring row); there is no separate state row to pair it with
CREATE TABLE IF NOT EXISTS agents.sw_canal_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evento TEXT NOT NULL CHECK (evento IN (
        'sw_canal_provisionado', 'sw_canal_renovado', 'sw_canal_provisionamento_falhou',
        'sw_canal_conexao_testada', 'sw_canal_chamada_concluida')),
    ok BOOLEAN NOT NULL,
    codigo TEXT NULL,
    mensagem TEXT NULL CHECK (mensagem IS NULL OR char_length(mensagem) <= 300),
    ator UUID NULL,
    token_id UUID NULL,
    expira_em TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agents_sw_canal_eventos_recentes ON agents.sw_canal_eventos (ok, created_at DESC);
COMMENT ON TABLE agents.sw_canal_eventos IS 'tier:platform';
ALTER TABLE agents.sw_canal_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.sw_canal_eventos;
CREATE POLICY "service_role_bypass" ON agents.sw_canal_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.sw_canal_eventos FROM anon, authenticated;

CREATE OR REPLACE FUNCTION agents.sw_canal_eventos_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = agents, public
AS $$
BEGIN
    RAISE EXCEPTION 'sw_canal_eventos is append-only';
END;
$$;
REVOKE ALL ON FUNCTION agents.sw_canal_eventos_append_only() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS sw_canal_eventos_no_update ON agents.sw_canal_eventos;
CREATE TRIGGER sw_canal_eventos_no_update BEFORE UPDATE OR DELETE ON agents.sw_canal_eventos
    FOR EACH ROW EXECUTE FUNCTION agents.sw_canal_eventos_append_only();
