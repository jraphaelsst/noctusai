-- ============================================================================
-- Migration 190 · social_wiring: `pacto_antenupcial` — the couple's escritura
-- pública de pacto antenupcial (or its Livro 3 registro at the Registro de
-- Imóveis) as an uploadable + extractable `cliente_documentos` type.
--
-- WHY THIS MIGRATION EXISTS
-- -------------------------
-- P4 live run (2026-10-01, deal 858): the signed contract's qualification of
-- a married seller cited the pacto antenupcial — regime, the escritura's
-- date, the Tabelião de Notas, livro and página — and the product had no
-- type to file the document under, so it could not even be uploaded onto
-- the person. See `noctusai_lib.integrations.documents.pacto_antenupcial`
-- (the seed reader) and `app.modules.card_hub.pacto_antenupcial_service`
-- (this product's couple apply) for the rest of the feature.
--
-- CATALOGUE ROW — mirrors `certidao_casamento` (103) / `ficha_cadastral`
-- (176): `categoria_lgpd='identidade'` (names + CPFs of both spouses),
-- `identidade=false` (not itself an identity-class checklist document).
--
-- RETENTION — the same 1825-day identity-adjacent policy `cnh` (142), `cin`
-- (164) and `ficha_cadastral` (176) took; the effective retention lives in
-- `documento_retencao_politicas` (079), so both rows are seeded.
--
-- `cliente_documentos.extracao_pacto_antenupcial` — the WHOLE reading, JSON:
--   regime_bens, regime_bens_confianca, data_escritura (ISO date),
--   tabelionato, livro, folhas,
--   registro {numero, livro, cartorio, data} | null,
--   data_casamento (ISO date) | null,
--   conjuges [{nome, cpf, cliente_id_aplicado}], source.
-- Held on the document, mirroring `extracao_ficha_cadastral` (176) /
-- `extracao_conjuges` (153): the escritura's facts belong to the document
-- (and to the couple), not to either person's `clientes` row. Only
-- `regime_bens` is written onto the matched spouses, through the D1 path.
--
-- FORWARD-ONLY, IDEMPOTENT: two INSERT ... ON CONFLICT + one ALTER TABLE
-- ADD COLUMN IF NOT EXISTS; no DROP / DELETE / TRUNCATE.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change.
-- Apply via `noctus.dev.migrate_product` only after the tech-lead and the
-- user have given an explicit go-ahead. See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    ('pacto_antenupcial', 'identidade', 1825, false, true,
     'Pacto antenupcial — escritura pública ou seu registro no Registro de '
     'Imóveis (regime de bens do casal)')
ON CONFLICT (tipo_documento) DO UPDATE
    SET categoria_lgpd = EXCLUDED.categoria_lgpd,
        retencao_dias  = EXCLUDED.retencao_dias,
        identidade     = EXCLUDED.identidade,
        ativo          = true,
        descricao      = EXCLUDED.descricao;

INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'cliente', 'pacto_antenupcial', 1825,
     'Mesma política de identidade adjacente (RG/CNH/CIN/ficha) — migration 190.')
ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING;

ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_pacto_antenupcial JSONB;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_pacto_antenupcial IS
    'The whole pacto antenupcial reading (PactoAntenupcialLido, JSON): '
    'regime_bens, regime_bens_confianca, data_escritura, tabelionato, livro, '
    'folhas, registro{numero,livro,cartorio,data}, data_casamento, '
    'conjuges[{nome,cpf,cliente_id_aplicado}], source. Held on the document '
    '(mirrors extracao_ficha_cadastral, 176). Migration 190.';
