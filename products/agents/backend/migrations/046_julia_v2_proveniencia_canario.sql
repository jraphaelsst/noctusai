-- ============================================================================
-- 046_julia_v2_proveniencia_canario.sql -- who said it, structurally (B2) and the prompt stays in the prompt (B7).
--
--   * `messages.meta` (JSONB object, <= 8000 chars): structural facts about the line that are NOT its text -- the
--     media a lead message carried (`midia`: tipo / texto_extraido / legenda) and the staff identity of a `humano`
--     line (`autor`: nome / papel). Written only by the routes that own that fact; read back into the history as
--     JSON literals (never as a prefix typed into the text).
--   * `evento` rows carry a CODE, never prose. Before this file the corrective re-run of a blocked reply stored the
--     correction WORDING as an `evento` row -- DB prompt text that reached the front end and re-entered the next
--     turn's history. Existing rows are redacted and a CHECK keeps new ones to the code shape
--     (`conformidade:<regra>[,<regra>]`).
--   * `agent_version_marcadores`: the per-version honeytoken. A random marker generated once, stored here and
--     NOWHERE else readable: service-role only, no Studio API selects it. It rides at the end of the model's system
--     prompt; any appearance in a reply, an inbound lead message or a tool argument is a prompt-leak hit.
--
-- Forward-only + idempotent. NOT applied by the slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. messages.meta ───────────────────────────────────────────────────────

ALTER TABLE agents.messages
    ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE agents.messages DROP CONSTRAINT IF EXISTS messages_meta_check;
ALTER TABLE agents.messages ADD CONSTRAINT messages_meta_check
    CHECK (jsonb_typeof(meta) = 'object' AND octet_length(meta::text) <= 8000);

-- ── 2. evento rows: code only ──────────────────────────────────────────────

UPDATE agents.messages
   SET texto = 'conformidade:redigido'
 WHERE role = 'evento'
   AND texto !~ '^[a-z][a-z0-9_]*:[a-z0-9_]+(,[a-z0-9_]+)*$';

ALTER TABLE agents.messages DROP CONSTRAINT IF EXISTS messages_evento_codigo_check;
ALTER TABLE agents.messages ADD CONSTRAINT messages_evento_codigo_check
    CHECK (role <> 'evento' OR texto ~ '^[a-z][a-z0-9_]*:[a-z0-9_]+(,[a-z0-9_]+)*$');

-- ── 3. the honeytoken ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agents.agent_version_marcadores (
    version_id UUID PRIMARY KEY REFERENCES agents.agent_versions(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    marcador TEXT NOT NULL CHECK (marcador ~ '^[a-f0-9]{16,64}$'),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agents.agent_version_marcadores ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON agents.agent_version_marcadores;
CREATE POLICY "service_role_bypass" ON agents.agent_version_marcadores
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON agents.agent_version_marcadores FROM PUBLIC, anon, authenticated;
