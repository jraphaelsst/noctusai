-- ============================================================================
-- Migration 148 -- social_wiring: a manual "certidão de estado civil --
--                  data de emissão" per person
--
-- WHAT THIS IS
-- ------------
-- Contract F6 / migration 117 built ONE reader of the office's 90-day
-- freshness rule: `identidade_extracao_service.certidao_estado_civil_mais
-- _recente`, which answers ONLY off `cliente_documentos.extracao_data_emissao`
-- -- a document must have been UPLOADED (and read) for the rule to have
-- anything to check. There was, until now, no human path: an operator who
-- already knows the emission date (told over the phone, read off a scanned
-- copy nobody uploaded yet) had nowhere to type it, so [Q11] stayed
-- permanently unanswerable for that party.
--
-- This adds exactly that path -- a nullable pair on `clientes`, on the same
-- provenance-stamping terms every other hand-typed identity field gets
-- (`data_nascimento_origem` / `genero_origem` / .../`nacionalidade_origem`):
-- `_origem` records HOW the value arrived, stamped by the SERVER, never
-- accepted from the request body (`clientes_router.ClientePatchBody` /
-- `clientes_service.update_cliente`).
--
-- 🔴 WHY NO `_documento_id` / `_confirmado_por` / `_confirmado_em` COLUMNS,
-- UNLIKE data_nascimento/genero/cpf/rg/estado_civil/regime_bens/
-- data_casamento/nacionalidade/nome_oficial
-- --------------------------------------------------------------------------
-- Every one of those NINE columns is a `CAMPOS` entry
-- (`identidade_extracao_service.CAMPOS` / `CAMPOS_QUALIFICACAO`) -- a
-- document extractor writes to the SAME column a human can also type into,
-- so the quintet exists to tell the two apart and to let a human "vouch for"
-- a low-confidence machine read (`confirmar_sugestao`).
--
-- `certidao_estado_civil_emitida_em` is NOT a `CAMPOS` entry and never will
-- be: the document's OWN emission date lives on `cliente_documentos
-- .extracao_data_emissao` (117's `_COLUNAS_DATA_EMISSAO`), a DIFFERENT row
-- entirely -- see that migration's comment on why `data_emissao` is
-- deliberately excluded from `CAMPOS` ("a fact about the certidão, not
-- about the holder"). No extractor has ever written, or will ever write,
-- to THIS column, so `_origem` can only ever hold `'manual'` once set --
-- there is no document-vs-human disagreement possible on this column, and
-- therefore no admin-adjudication (migration 138) surface for it either.
-- `_em` records WHEN, for the same audit reason every other provenance pair
-- keeps one.
--
-- HOW THE TWO SOURCES COMBINE AT SIGNING
-- ---------------------------------------
-- `certidao_estado_civil_mais_recente` (code, not this migration) now reads
-- BOTH this column and every qualifying `cliente_documentos` row and reports
-- whichever emission date is MORE RECENT -- exactly the same "freshest
-- reading wins" comparison it already runs across multiple uploaded
-- certidões, just extended to include a manually-typed one. The 90-day /
-- EMITIDA_APOS_ASSINATURA rules in `contrato_gerador.derivacao` are
-- unchanged: they consume whatever `completude_contratual` hands them and do
-- not know or care which source won.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS certidao_estado_civil_emitida_em         DATE,
    ADD COLUMN IF NOT EXISTS certidao_estado_civil_emitida_em_origem  TEXT,
    ADD COLUMN IF NOT EXISTS certidao_estado_civil_emitida_em_em      TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.certidao_estado_civil_emitida_em IS
    'A HUMAN-typed emission date for this person''s certidão de estado '
    'civil (contract F6, [Q11]) -- never written by extraction. Compared '
    'against every uploaded certidão''s OWN extracao_data_emissao by '
    'certidao_estado_civil_mais_recente(), which reports whichever date is '
    'more recent. See migration 148''s header for why this has no '
    'documento_id/confirmado_por/confirmado_em (unlike a CAMPOS field).';
COMMENT ON COLUMN social_wiring.clientes.certidao_estado_civil_emitida_em_origem IS
    'Always ''manual'' once set -- no extractor writes this column. Kept for '
    'the same provenance-audit reason every other identity field''s '
    '_origem is kept, and stamped by the SERVER (clientes_service'
    '.update_cliente), never accepted from the request body.';
