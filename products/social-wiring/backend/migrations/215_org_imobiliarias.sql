-- ============================================================================
-- Migration 215 · social_wiring: `org_imobiliarias` — the org registers N
-- signing companies; a contract CHOOSES which one signs it
-- ============================================================================
-- WHY
-- ---
-- `org_dados_cadastrais` holds ONE company per org (PK org_id). Deal 876's
-- signed contract qualifies a different company (which is also the commission
-- PIX payee) than the one on file. Owner decisions 2026-10-09
-- (projects/signing-companies/CONTRACT.md):
--   D1  identity is per company; ops (plataforma_assinatura_*, posse_multa_
--       diaria, prazo_pendencias_padrao_dias, suporte_*) stay org-wide on
--       org_dados_cadastrais.
--   D2  backfill: every existing contract of an org points at that org's
--       migrated company, so they regenerate exactly as today.
--   D3  CRECI região is two separate fields (company CRECI-PJ, responsável
--       CRECI), each printed independently.
--
-- Same mechanism family as witnesses (migration 168): a soft-deleted registry
-- (`excluida_em`, never hard-deleted) + a per-contract selection. A contract
-- holds exactly ONE company, so the selection is a nullable FK on
-- atendimento_contratos, not a join table. ON DELETE RESTRICT holds "never
-- delete what is linked" by construction.
--
-- FORWARD-ONLY, IDEMPOTENT. The superseded identity columns on
-- org_dados_cadastrais are NOT dropped; they are commented as superseded and
-- the API stops reading/writing them.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'migration 215 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'migration 215 requires public.attach_acting_audit_triggers (core migration 072) -- apply core first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. The registry
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.org_imobiliarias (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID NOT NULL
        REFERENCES public.organizations (id) ON DELETE CASCADE,
    razao_social              TEXT,
    nome_fantasia             TEXT,
    cnpj                      TEXT,
    creci_pj                  TEXT,
    creci_pj_regiao           TEXT,
    responsavel_nome          TEXT,
    responsavel_creci         TEXT,
    responsavel_creci_regiao  TEXT,
    telefone                  TEXT,
    email                     TEXT,
    endereco_cep              TEXT,
    endereco_logradouro       TEXT,
    endereco_numero           TEXT,
    endereco_complemento      TEXT,
    endereco_bairro           TEXT,
    endereco_cidade           TEXT,
    endereco_uf               TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por               UUID,
    updated_at                TIMESTAMPTZ,
    updated_por               UUID,
    excluida_em               TIMESTAMPTZ
);

COMMENT ON TABLE social_wiring.org_imobiliarias IS
    'Migration 215 — per-org REGISTRY of the signing companies (imobiliárias). '
    'A contract CHOOSES one (atendimento_contratos.imobiliaria_id); exactly one '
    'active company in the org is auto-selected at read time. Soft-deleted via '
    'excluida_em, never hard-deleted: contracts that chose it keep it.';

COMMENT ON COLUMN social_wiring.org_imobiliarias.excluida_em IS
    'Migration 215 — soft delete. The row leaves the registry list and cannot '
    'be newly chosen, but every contract that already chose it keeps it.';

CREATE INDEX IF NOT EXISTS idx_sw_org_imobiliarias_org
    ON social_wiring.org_imobiliarias (org_id);

-- One ACTIVE company per CNPJ (digits only) per org.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_org_imobiliarias_org_cnpj_ativa
    ON social_wiring.org_imobiliarias (org_id, regexp_replace(cnpj, '\D', '', 'g'))
    WHERE excluida_em IS NULL AND cnpj IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. The per-contract choice
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_contratos
    ADD COLUMN IF NOT EXISTS imobiliaria_id UUID NULL
        REFERENCES social_wiring.org_imobiliarias (id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_contratos_imobiliaria
    ON social_wiring.atendimento_contratos (imobiliaria_id);

COMMENT ON COLUMN social_wiring.atendimento_contratos.imobiliaria_id IS
    'Migration 215 — the signing company chosen for THIS contract. NULL = not '
    'chosen: resolved at read time (the org''s only active company, else none).';

-- ----------------------------------------------------------------------------
-- 3. Backfill (idempotent): the org's current company becomes registry entry
--    #1 and every existing contract of that org records it (D2). Regiões
--    stay NULL, so the printed text is unchanged.
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.org_imobiliarias (
    org_id, razao_social, nome_fantasia, cnpj, creci_pj,
    responsavel_nome, responsavel_creci, telefone, email,
    endereco_cep, endereco_logradouro, endereco_numero, endereco_complemento,
    endereco_bairro, endereco_cidade, endereco_uf
)
SELECT d.org_id, d.razao_social, d.nome_fantasia, d.cnpj, d.creci_pj,
       d.responsavel_nome, d.responsavel_creci, d.telefone, d.email,
       d.endereco_cep, d.endereco_logradouro, d.endereco_numero, d.endereco_complemento,
       d.endereco_bairro, d.endereco_cidade, d.endereco_uf
  FROM social_wiring.org_dados_cadastrais d
 WHERE NOT EXISTS (
        SELECT 1 FROM social_wiring.org_imobiliarias i WHERE i.org_id = d.org_id
       );

UPDATE social_wiring.atendimento_contratos c
   SET imobiliaria_id = (
        SELECT i.id FROM social_wiring.org_imobiliarias i
         WHERE i.org_id = c.org_id
         ORDER BY i.created_at ASC, i.id ASC
         LIMIT 1
       )
 WHERE c.imobiliaria_id IS NULL
   AND EXISTS (
        SELECT 1 FROM social_wiring.org_imobiliarias i WHERE i.org_id = c.org_id
       );

-- ----------------------------------------------------------------------------
-- 4. The superseded identity columns on org_dados_cadastrais
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.razao_social IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.nome_fantasia IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.cnpj IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.creci_pj IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.responsavel_nome IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.responsavel_creci IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.telefone IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.email IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.endereco_cep IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.endereco_logradouro IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.endereco_numero IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.endereco_complemento IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.endereco_bairro IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.endereco_cidade IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.endereco_uf IS 'superseded by org_imobiliarias (migration 215) — no longer read or written';

-- ----------------------------------------------------------------------------
-- 5. RLS — org-picker shape (migration 211)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.org_imobiliarias ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "org_imobiliarias_select_own_org" ON social_wiring.org_imobiliarias;
CREATE POLICY "org_imobiliarias_select_own_org"
    ON social_wiring.org_imobiliarias
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "org_imobiliarias_write_own_org" ON social_wiring.org_imobiliarias;
CREATE POLICY "org_imobiliarias_write_own_org"
    ON social_wiring.org_imobiliarias
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "org_imobiliarias_service_role" ON social_wiring.org_imobiliarias;
CREATE POLICY "org_imobiliarias_service_role"
    ON social_wiring.org_imobiliarias
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Acting-audit trigger for the new table (migration 214, idempotent).
SELECT public.attach_acting_audit_triggers('social_wiring');

-- ----------------------------------------------------------------------------
-- 6. Nav gating for the new "Imobiliárias" settings page
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('imobiliarias', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
