-- ============================================================================
-- Migration 142 · social_wiring: `cnh` as an uploadable, extractable
-- document type — closing the gap where every CNH on a card was being
-- filed as `rg` because `cnh` had no catalogue row at all.
--
-- 🔴 WHY THIS TYPE EXISTED IN CODE BEFORE IT EXISTED IN DATA
-- ------------------------------------------------------------
-- `identidade_extracao_service.TIPOS_EXTRAIVEIS` has always listed `cnh` —
-- the extractor already classifies and reads one. But
-- `documentos_service._require_tipo_documento` refuses any `tipo_documento`
-- with no `ativo = true` row in `cliente_documento_tipos`, and 057 never
-- seeded one for `cnh` (only `rg`/`cpf`). The practical effect: every CNH
-- upload on a real card was filed under `rg` instead (confirmed against
-- production — `CNH_Rodrigo.pdf`, `CNH_Tauane.pdf`, `Vendedora - CNH
-- Regina.pdf`, `MARCELLY CNH.pdf`, `CAIO CNH Digital.pdf` all carry
-- `tipo_documento = 'rg'`), because the upload UI had nowhere else to put
-- them and the endpoint had no way to refuse a wrong-but-active type.
--
-- This is the data change `TIPOS_EXTRAIVEIS`'s own comment predicted:
-- "adding the type later is then a data change, not a code change." No
-- application code needs to change for this to take effect — see
-- `tests/test_migration_142_cnh_documento_tipo.py` for the same proof
-- migration 119 pinned for `rg`/`cpf`.
--
-- 🔴 THE CATALOGUE ROW ALONE IS NOT ENOUGH — THE RETENTION POLICY NEEDS ITS
-- OWN ROW, MIRRORING `rg`'s REAL VALUE
-- ---------------------------------------------------------------------------
-- Migration 079 moved the EFFECTIVE retention off `cliente_documento_tipos.
-- retencao_dias` (superseded, application code must not read it — see that
-- migration's own comment) onto `documento_retencao_politicas`, whose
-- platform tier (`org_id IS NULL`) IS the allow-list `documento_retencao.
-- dias_para` and `.definir` refuse against. A catalogue row with no matching
-- platform-tier policy row does not error — `dias_para` quietly returns
-- `None` ("keep indefinitely"), which is the SAFE direction for a document
-- nobody expected but the WRONG direction for `cnh`: an identity document
-- carrying the same personal-data category as an RG must not silently get a
-- longer effective retention than the RG that sits right next to it on the
-- same checklist. So this migration seeds BOTH: the catalogue row (mirrors
-- `057`'s `rg` row) and the platform-tier policy row (mirrors what `079`'s
-- backfill copied forward for `rg`, since `cnh` did not exist yet to be
-- copied).
--
-- (`certidao_casamento`, migration 103, never got a matching policy row and
-- still has none — an existing, separate gap this migration does not touch;
-- flagged in the delivery note that shipped this file, not fixed here.)
--
-- FORWARD-ONLY, IDEMPOTENT — both inserts are `ON CONFLICT ... DO
-- UPDATE`/`DO NOTHING`; no DROP / DELETE / TRUNCATE; no schema change.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. The catalogue row — mirrors `057`'s `rg` row exactly (same
--    `categoria_lgpd`, same `retencao_dias`, same `identidade` flag),
--    shipped active from day one: unlike `rg`/`cpf` in 057, there is no
--    LGPD-intake gate pending for this type — it is the SAME data category
--    (`identidade`) that intake already covers.
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    ('cnh', 'identidade', 1825, true, true,
     'CNH — Carteira Nacional de Habilitação (qualificação civil)')
ON CONFLICT (tipo_documento) DO UPDATE
    SET categoria_lgpd = EXCLUDED.categoria_lgpd,
        retencao_dias  = EXCLUDED.retencao_dias,
        identidade     = EXCLUDED.identidade,
        ativo          = true,
        descricao      = EXCLUDED.descricao;

-- ----------------------------------------------------------------------------
-- 2. The retention policy's platform tier — mirrors `rg`'s live
--    `documento_retencao_politicas` row (`superficie = 'cliente'`,
--    `retencao_dias = 1825`), so `cnh`'s EFFECTIVE retention (what
--    `documento_retencao.dias_para` actually returns) matches `rg`'s from
--    the moment this ships, rather than defaulting to "keep indefinitely"
--    for want of a seed row 079 could not have written (the type did not
--    exist yet).
--
--    The partial unique index `uq_sw_doc_retencao_platform` is
--    `(superficie, tipo_documento) WHERE org_id IS NULL` — the `ON
--    CONFLICT` target below matches it exactly, same shape a plain
--    `ON CONFLICT DO NOTHING` cannot express against a partial index.
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'cliente', 'cnh', 1825,
     'Mesma política da RG (identidade, LGPD) — migration 142.')
ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING;
