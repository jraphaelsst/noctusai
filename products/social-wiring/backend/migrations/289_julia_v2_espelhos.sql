-- ============================================================================
-- Migration 289 -- social_wiring: julia-v2 mirrors (julia_v2_espelhos)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/agents/projects/julia-v2/CONTRACT.md section 9 (social-wiring `julia_v2_espelhos`), 1.2, Q6.
-- Julia is hosted in agents; SW consumes her through the API only. What SW keeps is a DISPLAY MIRROR of the
-- agents-side state, never a gate:
--
--   whatsapp_chats.agente_thread_id   the agents shared-thread id of the chat (also the "privacy disclosure
--                                     already sent" marker, as agente_conversation_id was).
--   whatsapp_chats.agente_estado      the Julia participant state agents reported last
--                                     (ativo | pausado | concluido | encerrado | transferido). Written ONLY
--                                     from agents responses (turn / thread read / PATCH participantes). SW never
--                                     decides from it: agents decides on every turn, under its turn lock.
--                                     `agente_pausado` is kept as a mirror one release and is no longer read as a
--                                     gate (CONTRACT 6.5 M5).
--   julia_envio_regras.estagio_minimo Q6: ONE qualification rubric. The send to the CRM fires when the stage agents
--                                     COMPUTED reaches this stage. `grupos` (the retired slot-criteria rubric) stays
--                                     one release, ignored.
--                                     NOC-REMEDIATE[drop-envio-grupos]: drop `grupos` once nothing reads it -- 2026-10-19
--   julia_contatos.codigo_imovel_campanha  the listing code of the campaign the lead came from (Meta form), sent to
--                                     agents as data (`contexto.operacional.origem.codigo_imovel_campanha`).
--   julia_textos_padrao               platform-wide default TEXT rows SW seeds an org's notice from. The lead-facing
--                                     default opening message lives HERE as a data row (no text in code); `{agente}`
--                                     resolves from the agents status name at send time.
--
-- Also: nothing is rewritten. FORWARD-ONLY, IDEMPOTENT. NO SECURITY DEFINER function. The tech-lead applies it with
-- noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.whatsapp_chats') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.whatsapp_chats -- apply the earlier migrations first';
  END IF;
  IF to_regclass('social_wiring.julia_envio_regras') IS NULL OR to_regclass('social_wiring.julia_contatos') IS NULL THEN
    RAISE EXCEPTION 'this migration requires the julia_* tables (migrations 267/270/287) -- apply them first';
  END IF;
END
$guard$;

-- -- 1. whatsapp_chats: the agents-side thread + participant state (display mirror) ------------
ALTER TABLE social_wiring.whatsapp_chats ADD COLUMN IF NOT EXISTS agente_thread_id uuid;
ALTER TABLE social_wiring.whatsapp_chats ADD COLUMN IF NOT EXISTS agente_estado text;
ALTER TABLE social_wiring.whatsapp_chats ADD COLUMN IF NOT EXISTS agente_estado_em timestamptz;

DO $c$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'whatsapp_chats_agente_estado_valido' AND conrelid = 'social_wiring.whatsapp_chats'::regclass
  ) THEN
    ALTER TABLE social_wiring.whatsapp_chats
      ADD CONSTRAINT whatsapp_chats_agente_estado_valido
      CHECK (agente_estado IS NULL OR agente_estado IN ('ativo', 'pausado', 'concluido', 'encerrado', 'transferido'));
  END IF;
END
$c$;

COMMENT ON COLUMN social_wiring.whatsapp_chats.agente_thread_id IS
    'agents shared lead thread id (julia-v2). Also the marker that the privacy disclosure bubble was already sent. '
    'Supersedes agente_conversation_id (kept one release).';
COMMENT ON COLUMN social_wiring.whatsapp_chats.agente_estado IS
    'DISPLAY MIRROR of the agent''s participant state in this chat, written only from agents responses. '
    'NEVER a gate: agents decides on every turn (julia-v2 CONTRACT D6).';
COMMENT ON COLUMN social_wiring.whatsapp_chats.agente_pausado IS
    'DISPLAY MIRROR (julia-v2): true while the agent is paused in this chat. No longer read as a gate; agents decides.';

-- -- 2. julia_envio_regras: ONE rubric (Q6) -------------------------------------------------
ALTER TABLE social_wiring.julia_envio_regras ADD COLUMN IF NOT EXISTS estagio_minimo text;

DO $c$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'julia_envio_regras_estagio_minimo_forma' AND conrelid = 'social_wiring.julia_envio_regras'::regclass
  ) THEN
    ALTER TABLE social_wiring.julia_envio_regras
      ADD CONSTRAINT julia_envio_regras_estagio_minimo_forma
      CHECK (estagio_minimo IS NULL OR estagio_minimo ~ '^[a-z][a-z0-9_]{1,63}$');
  END IF;
END
$c$;

COMMENT ON COLUMN social_wiring.julia_envio_regras.estagio_minimo IS
    'Q6: send the lead to the CRM when the stage agents computed is at or beyond this stage. Replaces the slot '
    'criteria `grupos` (kept one release, ignored).';

-- -- 3. julia_contatos: the campaign listing code ---------------------------------------------
ALTER TABLE social_wiring.julia_contatos ADD COLUMN IF NOT EXISTS codigo_imovel_campanha text;

COMMENT ON COLUMN social_wiring.julia_contatos.codigo_imovel_campanha IS
    'Listing code of the campaign the lead came from (Meta form REF); data for the agent, never a prompt.';

-- -- 4. julia_textos_padrao: platform default texts (data, not code) ------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.julia_textos_padrao (
    chave      text        PRIMARY KEY,
    conteudo   text        NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.julia_textos_padrao IS
    'Platform-wide default texts SW seeds an org''s rows from (julia-v2 migration 289). Placeholders: {agente} '
    '(the agents status name), {empresa}, {link}. Edited as DATA; no default text lives in code.';

ALTER TABLE social_wiring.julia_textos_padrao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "julia_textos_padrao_service_role" ON social_wiring.julia_textos_padrao;
CREATE POLICY "julia_textos_padrao_service_role" ON social_wiring.julia_textos_padrao
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- The default opening message (was MENSAGEM_INICIAL_PADRAO in julia_aviso_service.py, which hardcoded the
-- persona name). ON CONFLICT DO NOTHING: re-applying never overwrites an edited row. A blank text is refused where
-- it is READ (`julia_aviso_service.texto_padrao` -> 503), so a bad edit is loud, not a hole in a lead's first message.
INSERT INTO social_wiring.julia_textos_padrao (chave, conteudo)
VALUES (
    'mensagem_inicial',
    'Oi! Eu sou {agente}, assistente virtual da {empresa}. 😊 Como tratamos seus dados: {link}'
)
ON CONFLICT (chave) DO NOTHING;
