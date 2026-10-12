-- ============================================================================
-- Migration 250 — cs_roteiros.estrutura: the roteiro's beat order.
--
-- WHY: owner decision 2026-10-11 ("both structures"). The creator picks the
-- beat order when generating a roteiro (Roteiro Avançado):
--
--   corestudio — the order observed on CoreStudio roteiros 41428 / 41429:
--                capa -> CTA de salvar -> ... -> CTA de compartilhar/comentar
--                -> Apresentação Magnética (prompt `roteiro-v1-draft`)
--   metodo     — the Método Audience rule "capa primeiro, CTA por último":
--                capa -> ... -> Apresentação Magnética -> ONE closing CTA
--                (prompt `roteiro-metodo-v1-draft`)
--
-- "Reprocessar" reuses the stored value, so a regenerated roteiro keeps its
-- structure. `prompt_versao` (migration 229) already records which prompt ran.
--
-- Every existing row was generated with the CoreStudio order, so the default
-- 'corestudio' is the truthful backfill, not a guess.
--
-- Additive (a new NOT NULL column with a default), idempotent (ADD COLUMN IF
-- NOT EXISTS + DROP CONSTRAINT IF EXISTS / ADD), replay-safe. Requires 229.
--
-- GuardProbe: `social_wiring.cs_roteiros_estrutura_check` in
-- mcp/noctusai/tools/noctus/dev/verify_db_guards.py (_SW_250_ESTRUTURA_PROBE).
-- ============================================================================

ALTER TABLE social_wiring.cs_roteiros
    ADD COLUMN IF NOT EXISTS estrutura TEXT NOT NULL DEFAULT 'corestudio';

ALTER TABLE social_wiring.cs_roteiros
    DROP CONSTRAINT IF EXISTS cs_roteiros_estrutura_check;
ALTER TABLE social_wiring.cs_roteiros
    ADD CONSTRAINT cs_roteiros_estrutura_check
    CHECK (estrutura IN ('corestudio', 'metodo'));

COMMENT ON COLUMN social_wiring.cs_roteiros.estrutura IS
    'Beat order of the roteiro (migration 250): corestudio (CTA de salvar right '
    'after the capa) | metodo (capa first, one merged CTA last). Reprocessar '
    'reuses it.';
