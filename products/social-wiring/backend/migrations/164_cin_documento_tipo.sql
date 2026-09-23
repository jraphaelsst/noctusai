-- ============================================================================
-- Migration 164 · social_wiring: `cin` (Carteira de Identidade Nacional) as
-- an UPLOADABLE document type — upload only, never extracted.
--
-- WHAT THIS IS
-- ------------
-- [Owner directive, 2026-09-23] "make rg/cpf 1 single checklist item. then i
-- need the CIN field and the CNH field. only one of those fields need to be
-- filled, if they are able to extract rg and cpf from it, otherwise the
-- mechanism shall block generation missing one of those fields (rg/cpf)."
--
-- The two separate `rg` / `cpf` checklist items collapsed into ONE item,
-- "Documento de identidade (RG e CPF)" (`documento_checklist_service.ITENS`,
-- key `identidade`), with two upload slots: CIN and CNH. `cnh` already has a
-- catalogue row (migration 142); `cin` did not, and
-- `documentos_service._require_tipo_documento` refuses any `tipo_documento`
-- with no `ativo = true` row — so without this row the CIN slot could not
-- accept a file at all.
--
-- 🔴 NO EXTRACTION, BY DESIGN
-- ---------------------------
-- No real CIN has been seen yet, so there is no extractor for one and none
-- is built: `cin` is deliberately ABSENT from `proveniencia.fontes.FONTES`,
-- which makes `identidade_extracao_service.deve_extrair('cin')` false. A CIN
-- upload is stored and listed; its RG/CPF are typed and validated by the
-- operator. The checklist item is satisfied by the RG and CPF VALUES on the
-- record, never by the file alone — so an unread CIN keeps the item (and the
-- contract gate) naming exactly which of RG/CPF is still missing.
--
-- A CIN prints the CPF number as the identity number (órgão "IIGDR"), so
-- RG == CPF is its VALID state. Nothing in this product refuses or flags it
-- for a CIN holder (see `identidade_extracao_service.sugestoes_pendentes`).
--
-- THE CATALOGUE ROW ALONE IS NOT ENOUGH — same reasoning as migration 142:
-- the effective retention lives in `documento_retencao_politicas` (079), and
-- an identity document must not silently get a longer effective retention
-- than the RG/CNH beside it on the same checklist item. So both rows are
-- seeded, mirroring `cnh`'s exactly.
--
-- Existing rows are NOT touched: no document is retyped (a CNH filed as
-- `rg` stays `rg`; the checklist item reads it as a legacy identity document
-- and is satisfied by the values read off it).
--
-- FORWARD-ONLY, IDEMPOTENT: two INSERT ... ON CONFLICT, no schema change,
-- no DROP / DELETE / TRUNCATE. Re-running it changes nothing.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change.
-- Apply via `noctus.dev.migrate_product` only after the tech-lead and the
-- user have given an explicit go-ahead. See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    ('cin', 'identidade', 1825, true, true,
     'CIN — Carteira de Identidade Nacional')
ON CONFLICT (tipo_documento) DO UPDATE
    SET categoria_lgpd = EXCLUDED.categoria_lgpd,
        retencao_dias  = EXCLUDED.retencao_dias,
        identidade     = EXCLUDED.identidade,
        ativo          = true,
        descricao      = EXCLUDED.descricao;

INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'cliente', 'cin', 1825,
     'Mesma política da RG/CNH (identidade, LGPD) — migration 164.')
ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING;
