-- ============================================================================
-- 064_agent_product_grants_especificacoes_editor.sql -- WHO edits the org's agent specs, decided ON THE GRANT.
--
-- A grant is one (agent, product, org) with its OWN personal token (a token never reaches another agent). The same
-- grant now also says who may fill that org's agent specs (agent_org_specs: nome_imobiliaria, creci_j, ...):
--
--   'plataforma'  (default) NoctusAI staff fill them from Agentes Studio
--                 (PUT /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs; platform admin
--                 login + a LIVE grant: status 'ativo', not expired). The product (social-wiring) stays read-only.
--   'org'         RESERVED. Switching a grant to 'org' will let the org's own admins edit through the product.
--                 Nothing reads this value as 'org' yet: that path is not built and the staff route refuses it
--                 (409 editor_nao_plataforma) so the switch cannot silently open or close an edit surface.
--
-- Additive + backward compatible with the previous image (N-1 never selects the column; the DEFAULT fills every
-- existing row). Forward-only + idempotent. NOT VALID is unnecessary: the table is tiny and the CHECK is on a
-- constant-default NOT NULL column (ADD COLUMN ... DEFAULT <constant> is metadata-only on PG11+).
-- ============================================================================

SET search_path = agents, public;

SET LOCAL lock_timeout = '5s';

ALTER TABLE agents.agent_product_grants
    ADD COLUMN IF NOT EXISTS especificacoes_editor TEXT NOT NULL DEFAULT 'plataforma';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'agent_product_grants_especificacoes_editor_check'
          AND conrelid = 'agents.agent_product_grants'::regclass
    ) THEN
        ALTER TABLE agents.agent_product_grants
            ADD CONSTRAINT agent_product_grants_especificacoes_editor_check
            CHECK (especificacoes_editor IN ('plataforma', 'org'));
    END IF;
END $$;

COMMENT ON COLUMN agents.agent_product_grants.especificacoes_editor IS
    'Who fills the org specs of this grant: plataforma (NoctusAI staff, Studio) | org (RESERVED, not built).';
