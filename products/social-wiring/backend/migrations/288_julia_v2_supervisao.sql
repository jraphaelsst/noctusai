-- ============================================================================
-- Migration 288 -- social_wiring: julia-v2 supervision fixes G1 + G3 (julia_v2_supervisao)
-- ============================================================================
-- WHY
-- ---
-- Contract: products/agents/projects/julia-v2/CONTRACT.md section 7 (G1-G4); metric/API side in
-- products/social-wiring/projects/maya-blocks/CONTRACT.md.
--
--   G1  julia_interacoes.primeira_resposta_at was stamped by Julia AND by any human inbox send on a Julia
--       line, so a human reply counted as Julia's response time in the sdr scorecard. It is split into
--       primeira_resposta_agente_at (Julia's own reply; the ONLY input of the sdr.v2 TPR) and
--       primeira_resposta_humana_at (a person's reply from the inbox; reported separately).
--       primeira_resposta_at is KEPT (still written, first of either) for one release.
--       NOC-REMEDIATE[drop-primeira-resposta-at]: drop it, and the dual write, once nothing reads it — 2026-10-19
--       BACKFILL: primeira_resposta_at is ambiguous, so it is copied into a split column only where PROVABLE:
--       an outbound message of that kind (Julia's rows carry structured_payload.origem = 'julia'; a human's
--       rows do not) on the contato's chat within +-5 s of the stamp. Otherwise the split columns stay NULL
--       (reported as missing, never guessed).
--   G3  atendimento_handoffs.gatilho gains 'aceite_proposta' (T3): an accepted proposal records the
--       funil -> processos handoff even when the accept carries no actor (no pipeline_movimentos row can be
--       written then, responsavel_id is NOT NULL).
--
-- No new table: the supervision-failure alerts (G4) are julia_eventos rows of tipo 'supervisao_falha' (the
-- tipo column only guards the token shape), counted per day by the scorecard engine.
-- NO SECURITY DEFINER function. FORWARD-ONLY, IDEMPOTENT. Applied by the tech-lead with noctus.dev.migrate_product.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.julia_interacoes') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.julia_interacoes (migrations 267/287) -- apply first';
  END IF;
  IF to_regclass('social_wiring.atendimento_handoffs') IS NULL THEN
    RAISE EXCEPTION 'this migration requires social_wiring.atendimento_handoffs (migration 286) -- apply 286 first';
  END IF;
END
$guard$;

-- ── 1. G1: the two first-response columns ────────────────────────────────────
ALTER TABLE social_wiring.julia_interacoes ADD COLUMN IF NOT EXISTS primeira_resposta_agente_at timestamptz;
ALTER TABLE social_wiring.julia_interacoes ADD COLUMN IF NOT EXISTS primeira_resposta_humana_at timestamptz;

COMMENT ON COLUMN social_wiring.julia_interacoes.primeira_resposta_agente_at IS
    'First outbound reply of the episode sent by the AGENT (Julia''s _deliver), written once (migration 288). '
    'primeira_resposta_agente_at - iniciada_at is the first-response time of the Maya sdr.v2 scorecard.';
COMMENT ON COLUMN social_wiring.julia_interacoes.primeira_resposta_humana_at IS
    'First outbound reply of the episode sent by a HUMAN from the inbox on a Julia line, written once '
    '(migration 288). Reported separately (tpr_humano_*); it never counts as Julia''s response time.';
COMMENT ON COLUMN social_wiring.julia_interacoes.primeira_resposta_at IS
    'DEPRECATED (migration 288): first reply of either kind, ambiguous. Read primeira_resposta_agente_at / '
    'primeira_resposta_humana_at. NOC-REMEDIATE[drop-primeira-resposta-at] -- 2026-10-19';

ALTER TABLE social_wiring.julia_interacoes DROP CONSTRAINT IF EXISTS julia_interacoes_primeira_resposta_agente_coerente;
ALTER TABLE social_wiring.julia_interacoes ADD  CONSTRAINT julia_interacoes_primeira_resposta_agente_coerente
    CHECK (primeira_resposta_agente_at IS NULL OR primeira_resposta_agente_at >= iniciada_at);
ALTER TABLE social_wiring.julia_interacoes DROP CONSTRAINT IF EXISTS julia_interacoes_primeira_resposta_humana_coerente;
ALTER TABLE social_wiring.julia_interacoes ADD  CONSTRAINT julia_interacoes_primeira_resposta_humana_coerente
    CHECK (primeira_resposta_humana_at IS NULL OR primeira_resposta_humana_at >= iniciada_at);

-- Backfill (provable only; idempotent -- fills NULLs, never overwrites).
UPDATE social_wiring.julia_interacoes i
   SET primeira_resposta_agente_at = i.primeira_resposta_at
  FROM social_wiring.julia_contatos c
 WHERE i.primeira_resposta_agente_at IS NULL
   AND i.primeira_resposta_at IS NOT NULL
   AND c.id = i.contato_id
   AND EXISTS (
        SELECT 1 FROM social_wiring.conversation_messages m
         WHERE m.org_id = i.org_id AND m.connection_id = c.connection_id AND m.chat_id = c.chat_id
           AND m.direction = 'outbound' AND m.structured_payload ->> 'origem' = 'julia'
           AND m.created_at BETWEEN i.primeira_resposta_at - interval '5 seconds'
                                AND i.primeira_resposta_at + interval '5 seconds');

UPDATE social_wiring.julia_interacoes i
   SET primeira_resposta_humana_at = i.primeira_resposta_at
  FROM social_wiring.julia_contatos c
 WHERE i.primeira_resposta_humana_at IS NULL
   AND i.primeira_resposta_at IS NOT NULL
   AND c.id = i.contato_id
   AND EXISTS (
        SELECT 1 FROM social_wiring.conversation_messages m
         WHERE m.org_id = i.org_id AND m.connection_id = c.connection_id AND m.chat_id = c.chat_id
           AND m.direction = 'outbound' AND COALESCE(m.structured_payload ->> 'origem', '') <> 'julia'
           AND m.created_at BETWEEN i.primeira_resposta_at - interval '5 seconds'
                                AND i.primeira_resposta_at + interval '5 seconds');

-- ── 2. G3: the accept trigger ────────────────────────────────────────────────
ALTER TABLE social_wiring.atendimento_handoffs DROP CONSTRAINT IF EXISTS atendimento_handoffs_gatilho_valido;
ALTER TABLE social_wiring.atendimento_handoffs ADD  CONSTRAINT atendimento_handoffs_gatilho_valido
    CHECK (gatilho IN ('novo_lead', 'movimento_etapa', 'aceite_proposta'));

COMMENT ON TABLE social_wiring.atendimento_handoffs IS
    'Block-to-block handoffs (migration 286, maya-blocks): references only, no copied PII. origem_evento = '
    'julia_eventos.id (gatilho novo_lead), pipeline_movimentos.id (movimento_etapa) or processos_venda.id '
    '(aceite_proposta, migration 288 -- recorded even when the accept had no actor); the unique key makes a '
    'replayed event a no-op. Status emitido -> assumido | expirado (both terminal).';
