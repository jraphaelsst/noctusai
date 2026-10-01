-- ============================================================================
-- 179 — atendimento_partes gains a PJ party (empresa_id); certidões become
--       readable per PARTY (cliente | empresa), newest-emissão first.
-- ============================================================================
-- Project `atendimento-partes-imoveis`, Wave A (spec: PROJECT.md §3.1/§3.2).
--
-- A. `atendimento_partes.cliente_id` was NOT NULL (073): a party was always a
--    PF `clientes` row. A PJ (empresa) can now be comprador or vendedor, so the
--    party is exactly ONE of (cliente_id, empresa_id) — a CHECK, not a service
--    convention, because "both" and "neither" are both meaningless rows.
--    The existing unique (atendimento_id, cliente_id) (073) already tolerates
--    NULL cliente_id (NULLs are distinct); a twin partial unique covers empresa.
--    FK is ON DELETE CASCADE for the same reason 073 gave for cliente_id.
--
-- B. Certidões are read by party across deals. `certidao_consultas` already
--    carries cliente_id (107) and empresa_id (167); what was missing is an index
--    ordered the way the matriz reads ("newest consulta per party") and one on
--    resultados for "newest emitida_em per (consulta, tipo)". Both partial on
--    `excluida_em IS NULL` (161 soft-delete).
--
-- (Custom matriz rows, 170, stay keyed by the CARD's cliente_id — they are a
--  fact about one card, which is always a PF; PJ party columns share them.
--  No schema change needed there.)
--
-- Forward-only, idempotent. Touches no existing row. NOT applied to prod here —
-- applying is the tech-lead's decision.
-- ============================================================================

SET search_path = social_wiring, public;

-- A. atendimento_partes: PJ party -------------------------------------------
ALTER TABLE social_wiring.atendimento_partes
    ADD COLUMN IF NOT EXISTS empresa_id UUID
        REFERENCES social_wiring.empresas (id) ON DELETE CASCADE;

ALTER TABLE social_wiring.atendimento_partes
    ALTER COLUMN cliente_id DROP NOT NULL;

ALTER TABLE social_wiring.atendimento_partes
    DROP CONSTRAINT IF EXISTS atendimento_partes_pessoa_xor_empresa;
ALTER TABLE social_wiring.atendimento_partes
    ADD CONSTRAINT atendimento_partes_pessoa_xor_empresa
    CHECK (num_nonnulls(cliente_id, empresa_id) = 1);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_atendimento_partes_empresa
    ON social_wiring.atendimento_partes (atendimento_id, empresa_id)
    WHERE empresa_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_partes_empresa
    ON social_wiring.atendimento_partes (org_id, empresa_id)
    WHERE empresa_id IS NOT NULL;

COMMENT ON COLUMN social_wiring.atendimento_partes.empresa_id IS
    'The empresa (PJ) this party IS, when the party is a company. Exactly one '
    'of cliente_id / empresa_id is set (CHECK atendimento_partes_pessoa_xor_'
    'empresa). Migration 179.';

-- B. certidões read per party -----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_cliente_recentes
    ON social_wiring.certidao_consultas (org_id, cliente_id, created_at DESC)
    WHERE cliente_id IS NOT NULL AND excluida_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_empresa_recentes
    ON social_wiring.certidao_consultas (org_id, empresa_id, created_at DESC)
    WHERE empresa_id IS NOT NULL AND excluida_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_consulta_tipo_emissao
    ON social_wiring.certidao_resultados (consulta_id, tipo, emitida_em DESC NULLS LAST, created_at DESC)
    WHERE excluida_em IS NULL;

NOTIFY pgrst, 'reload schema';
