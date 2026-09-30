-- ============================================================================
-- Migration 176 · social_wiring: `ficha_cadastral` — the bank's own
-- registration form (FORMULÁRIO COMPRADOR/VENDEDOR/FGTS ITAÚ) as an
-- uploadable + extractable `cliente_documentos` type.
--
-- WHY THIS MIGRATION EXISTS
-- -------------------------
-- Live prod test (5 historical deals re-run, 2026-09-30): the contract's
-- party ADDRESS (and sometimes profissão/estado civil) came from these
-- forms for every party that had one — the contract's CEP matched the
-- form's own CEP for 16/16 parties measured, the street for ~12/16. Today
-- `social_wiring.cliente_documento_tipos` has no row for this type at all,
-- so it cannot even be uploaded — see `noctusai_lib.integrations.documents
-- .ficha_cadastral_extractor` (the seed reader) and `app.modules.card_hub
-- .ficha_cadastral_service` (this product's multi-person apply) for the
-- rest of this feature.
--
-- CATALOGUE ROW — mirrors `certidao_casamento`'s own shape (migration 103):
-- `categoria_lgpd='identidade'` (the form carries CPF/RG/data de nascimento
-- per person), `identidade=false` (it is not ITSELF an RG/CPF-class
-- checklist item — a supplementary/corroboration source, same posture
-- `certidao_casamento`/`certidao_nascimento` already take).
--
-- RETENTION — same 1825-day identity-adjacent policy `cin` (migration 164)
-- and `cnh` (migration 142) took: the effective retention lives in
-- `documento_retencao_politicas` (079), never only on the catalogue row —
-- see either of those migrations' own header for why both are seeded.
--
-- `cliente_documentos.extracao_ficha_cadastral` — the WHOLE multi-person
-- reading, JSON-serialized, mirroring `extracao_crednet` (migration 167)
-- and `extracao_conjuges` (153:120): held on the document because the
-- document IS the provenance for every person it named, not only the one
-- whose card it was uploaded onto.
--
-- FORWARD-ONLY, IDEMPOTENT: two INSERT ... ON CONFLICT + one ALTER TABLE
-- ADD COLUMN IF NOT EXISTS, no DROP / DELETE / TRUNCATE. Re-running it
-- changes nothing already applied.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change.
-- Apply via `noctus.dev.migrate_product` only after the tech-lead and the
-- user have given an explicit go-ahead. See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, retencao_dias, identidade, ativo, descricao)
VALUES
    ('ficha_cadastral', 'identidade', 1825, false, true,
     'Ficha cadastral / formulário do banco (comprador, vendedor ou FGTS) — '
     'endereço, profissão e estado civil por pessoa')
ON CONFLICT (tipo_documento) DO UPDATE
    SET categoria_lgpd = EXCLUDED.categoria_lgpd,
        retencao_dias  = EXCLUDED.retencao_dias,
        identidade     = EXCLUDED.identidade,
        ativo          = true,
        descricao      = EXCLUDED.descricao;

INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'cliente', 'ficha_cadastral', 1825,
     'Mesma política de identidade adjacente (RG/CNH/CIN) — migration 176.')
ON CONFLICT (superficie, tipo_documento) WHERE org_id IS NULL DO NOTHING;

ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_ficha_cadastral JSONB;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_ficha_cadastral IS
    'The whole ficha cadastral reading (FichaCadastralLida, JSON-serialized) '
    '-- every person the form named, their own fields, and which atendimento '
    'party (if any) each was matched to by CPF. Mirrors extracao_crednet '
    '(167) / extracao_conjuges (153:120) -- held on the document because the '
    'document IS the provenance for every person it named. Migration 176.';
