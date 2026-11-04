-- ============================================================================
-- 057_julia_v3_alertas_documentos.sql -- Julia v3 (CONTRACT §12.3, §12.8).
--
--   * `agents.thread_alertas`: what `sinalizar_alerta` records -- the lead is unhappy, Julia noticed her own
--     mistake, or the conversation drifted. One row per alert; SW turns the turn's `alerta` action into a
--     WhatsApp notice to the report destination. `trecho` is the lead's/Julia's words (capped), `descricao` the
--     agent's reading. Personal data: service-role only, rows go with the thread (FK ON DELETE CASCADE).
--   * `agents.lead_identificacao` gains the document-sent flags (`registrar_documento`): the lead sent a photo /
--     scan of an ID document. Flags + the probable type + the inbound message id only -- never the media or
--     what is in it. The CPF counts as satisfied pending extraction on SW's side.
--
-- Forward-only + idempotent. NOT applied by the slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

CREATE TABLE IF NOT EXISTS agents.thread_alertas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    thread_id UUID NOT NULL REFERENCES agents.conversations(id) ON DELETE CASCADE,
    agent_id UUID NULL REFERENCES agents.agents(id) ON DELETE SET NULL,
    tipo TEXT NOT NULL
        CHECK (tipo IN ('lead_insatisfeito', 'erro_agente', 'desvio', 'outro')),
    descricao TEXT NOT NULL
        CHECK (char_length(btrim(descricao)) BETWEEN 1 AND 500),
    trecho TEXT NULL
        CHECK (trecho IS NULL OR char_length(trecho) <= 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_thread_alertas_thread
    ON agents.thread_alertas (org_id, thread_id, created_at DESC);

ALTER TABLE agents.thread_alertas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.thread_alertas;
CREATE POLICY "service_role_bypass" ON agents.thread_alertas
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.thread_alertas FROM PUBLIC, anon, authenticated;

ALTER TABLE agents.lead_identificacao
    ADD COLUMN IF NOT EXISTS documento_enviado BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS documento_tipo TEXT NULL
        CHECK (documento_tipo IS NULL OR documento_tipo IN ('rg', 'cpf', 'cin', 'cnh', 'outro')),
    ADD COLUMN IF NOT EXISTS documento_provider_message_id TEXT NULL;
