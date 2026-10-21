-- ============================================================================
-- Migration 296 -- social_wiring: filiação (nome_pai) + naturalidade on
-- clientes, and their readings on cliente_documentos
--
-- Owner decision 2026-10-21. `nome_mae` already exists (167, Serasa Crednet,
-- same D1 quintet). This adds the two other facts a RG/CIN/CNH, a certidão
-- de nascimento and a certidão de casamento (per spouse) print:
--
--   clientes.nome_pai      father's name as printed
--   clientes.naturalidade  place of birth, "Cidade/UF"
--
-- Each with the standard provenance columns every identity field carries
-- (`_origem`, `_documento_id`, `_em`, `_confirmado_por`, `_confirmado_em`:
-- machine-pending iff origem <> manual AND confirmado_em IS NULL -- the
-- 068/137/167 D1 contract), and the document-row reading triple
-- (`extracao_<campo>` / `_confianca` / `_rotulo`) the generic apply path reads.
-- `nome_mae`'s `extracao_nome_mae*` columns exist since 167.
--
-- Not required for the contract (the generator does not print them): nothing
-- here changes the contract-completeness gate.
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS nome_pai                 TEXT,
    ADD COLUMN IF NOT EXISTS nome_pai_origem          TEXT,
    ADD COLUMN IF NOT EXISTS nome_pai_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS nome_pai_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nome_pai_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS nome_pai_confirmado_em   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS naturalidade                 TEXT,
    ADD COLUMN IF NOT EXISTS naturalidade_origem          TEXT,
    ADD COLUMN IF NOT EXISTS naturalidade_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS naturalidade_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS naturalidade_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS naturalidade_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.nome_pai_origem IS
    'manual | rg | cnh | cin | certidao_nascimento | certidao_casamento — who '
    'wrote nome_pai. Machine-pending iff origem <> manual AND '
    'nome_pai_confirmado_em IS NULL (migration 296, D1 as 167).';
COMMENT ON COLUMN social_wiring.clientes.naturalidade_origem IS
    'manual | rg | cin | certidao_nascimento | certidao_casamento — who wrote '
    'naturalidade ("Cidade/UF"). Machine-pending iff origem <> manual AND '
    'naturalidade_confirmado_em IS NULL (migration 296, D1 as 167).';

ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_nome_pai                TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nome_pai_confianca      TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nome_pai_rotulo         TEXT,
    ADD COLUMN IF NOT EXISTS extracao_naturalidade            TEXT,
    ADD COLUMN IF NOT EXISTS extracao_naturalidade_confianca  TEXT,
    ADD COLUMN IF NOT EXISTS extracao_naturalidade_rotulo     TEXT;
