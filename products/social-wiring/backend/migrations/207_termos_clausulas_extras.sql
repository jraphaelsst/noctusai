-- Migration: termos_clausulas_extras
-- Schema: social_wiring

SET search_path = social_wiring, public;

-- ============================================================
-- Deal-specific contract text no card field holds (owner, 2026-10-06:
-- generated contracts must be "similar enough to fulfil the deal's terms",
-- and every field the generator reads must be settable in the card UI).
--
-- Signed contracts carry bespoke text per clause: an extra objeto paragraph, a
-- financing/consórcio paragraph in preço, a posse prazo extendable once, a
-- rewritten irretratabilidade, an extra vistoria sentence. ONE general
-- mechanism, modelled on `obrigacoes_vendedor` (193) but for EVERY clause.
--
-- `clausulas_extras` JSONB — `{ "<clause key>": { "texto": text,
--     "modo": "acrescentar" | "substituir" } }`. The keys are the generator's
--     own clause ids (`contrato_gerador.numeracao.ORDEM_CLAUSULAS`: objeto,
--     preco, posse, onus, irretratabilidade, vistoria, tributos, ...) — the
--     vocabulary is owned by the generator, which refuses an unknown key with
--     a named 400 (write) / bloqueio (read), so it is NOT frozen into a CHECK
--     here (a new clause must not need a migration). "acrescentar" prints the
--     typed paragraphs after the clause's standard ones; "substituir" replaces
--     the clause body, keeping heading and number. Every non-empty entry is a
--     legal-review item. The column is NOT NULL with DEFAULT '{}': "no special
--     conditions" is the empty object, never NULL, and existing rows keep
--     rendering exactly as before.
--
-- `posse_multa_diaria` NUMERIC — per-deal override of the office's daily fine
--     for late delivery of the posse (`org_dados_cadastrais.posse_multa_diaria`,
--     117). NULL = the office default; a value must be > 0 (same shape as the
--     per-contract `prazo_pendencias_dias` override, 114).
--
-- Additive + idempotent (IF NOT EXISTS / guarded constraints).
-- ============================================================
ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD COLUMN IF NOT EXISTS clausulas_extras JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS posse_multa_diaria NUMERIC;

ALTER TABLE social_wiring.atendimento_negociacao_termos
    DROP CONSTRAINT IF EXISTS atendimento_negociacao_termos_clausulas_extras_objeto;
ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD CONSTRAINT atendimento_negociacao_termos_clausulas_extras_objeto
    CHECK (jsonb_typeof(clausulas_extras) = 'object');

ALTER TABLE social_wiring.atendimento_negociacao_termos
    DROP CONSTRAINT IF EXISTS atendimento_negociacao_termos_posse_multa_diaria_positiva;
ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD CONSTRAINT atendimento_negociacao_termos_posse_multa_diaria_positiva
    CHECK (posse_multa_diaria IS NULL OR posse_multa_diaria > 0);

COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.clausulas_extras IS
    'Per-clause special conditions: {<clause key>: {texto, modo}}, modo = '
    'acrescentar | substituir. Keys are contrato_gerador.numeracao.ORDEM_CLAUSULAS '
    '(validated by the service, not a CHECK). Migration 207.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.posse_multa_diaria IS
    'Per-deal override of the office daily fine for a late posse '
    '(org_dados_cadastrais.posse_multa_diaria); NULL = the office default. '
    'Migration 207.';

NOTIFY pgrst, 'reload schema';
