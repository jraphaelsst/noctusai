-- ============================================================================
-- Migration 172 · social_wiring: identity-extraction legibilidade (readability)
--
-- Owner decision (2026-09-28, verbatim intent): "when a document's
-- readability is compromised, we'll warn on the human-gate review, so
-- humans are aware the doc is risky and readability is compromised — human
-- check is mandatory."
--
-- Measured failure: a phone SCREENSHOT of the CNH Digital app (card small in
-- frame) had its vision transcription hallucinate a well-formed, PLAUSIBLE
-- wrong reading — a date label with a non-date value, a CEP label with a
-- date-shaped phrase, several fields marked "(ilegível)", and the holder
-- NOME landing on the mother's (FILIAÇÃO) name — and a wrong nome + CPF were
-- auto-applied to the person's record.
--
-- `noctusai_lib.integrations.documents.legibilidade.avaliar_legibilidade`
-- (seed) runs a cross-field pass over the SAME transcription every
-- per-field parser already reads and, when it finds these structural
-- signals, adds `leitura_comprometida` to `IdentityFields.aviso` (the
-- existing "+"-joined code list `real.py` already produces for
-- `titulares_multiplos` / `data_nascimento_implausivel`).
--
-- `cliente_documentos` (057/068) never gained an `extracao_aviso` column —
-- unlike `atendimento_documentos` (171) and `empresa_documentos` (167),
-- identity's own `fields.aviso` was only LOGGED, never persisted. This adds
-- the column pair every other document family already has, so the
-- identity-extraction aviso survives on the document row for a human to
-- see (Anexos / the pessoa checklist / the pre-generation validation
-- modal), exactly like `extracao_erro` already does for a failed read.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead's go-ahead. See
-- `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_aviso           TEXT,
    ADD COLUMN IF NOT EXISTS extracao_aviso_mensagem   TEXT;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_aviso IS
    'A non-fatal advisory alongside a terminal extracao_status — a "+"-joined '
    'list of codes (mirrors IdentityFields.aviso), e.g. '
    '''titulares_multiplos'', ''data_nascimento_implausivel'', or '
    '''leitura_comprometida'' (migration 172 — the transcription itself looks '
    'damaged: a label/value type mismatch, a high ilegível-marker share, or '
    'the holder name matching a FILIAÇÃO/parent name on the same document). '
    'Distinct from extracao_erro, which is a FAILED read. Never blocks the '
    'apply on its own; identidade_extracao_service is the caller that, for '
    '''leitura_comprometida'' specifically, withholds every field from '
    'aplicar_campos_ao_cliente so nothing writes unattended off a reading '
    'flagged this way (owner decision, 2026-09-28).';
COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_aviso_mensagem IS
    'The pt-BR sentence naming every reason in extracao_aviso, " | "-joined — '
    'shown verbatim on the document row/Anexos, the pessoa checklist, and the '
    'pre-generation validation modal so a human sees WHY, not just a code.';
