-- ============================================================================
-- Migration 332 -- social_wiring: corretor divergence TYPES + the property's principal corretor (ad-lead intake, owner 2026-11-09)
-- ============================================================================
-- WHY: the owner wants three distinct, queryable warnings (CONTRACT ad-lead-intake § 2.3):
--   fora_dos_corretores : the lead's corretor is none of the property's Vista corretores
--   nao_e_principal     : the lead's corretor is one of them but not the MAIN one (the first Vista lists)
--   lead_sem_corretor   : the lead has no corretor at all
-- One OPEN warning per (lead, imóvel, tipo). `imovel_corretores.principal` persists which Vista corretor is the main one.
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible with the previous image (new columns have defaults; the unique key widens).
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_corretores ADD COLUMN IF NOT EXISTS principal boolean NOT NULL DEFAULT false;
UPDATE social_wiring.imovel_corretores SET principal = true WHERE ordem = 0 AND ativo AND NOT principal;

ALTER TABLE social_wiring.lead_corretor_divergencias
    ADD COLUMN IF NOT EXISTS tipo text NOT NULL DEFAULT 'fora_dos_corretores';
ALTER TABLE social_wiring.lead_corretor_divergencias DROP CONSTRAINT IF EXISTS lead_corretor_divergencias_tipo_check;
ALTER TABLE social_wiring.lead_corretor_divergencias
    ADD CONSTRAINT lead_corretor_divergencias_tipo_check
    CHECK (tipo IN ('fora_dos_corretores', 'nao_e_principal', 'lead_sem_corretor'));

ALTER TABLE social_wiring.lead_corretor_divergencias DROP CONSTRAINT IF EXISTS uq_sw_lead_corretor_divergencias;
ALTER TABLE social_wiring.lead_corretor_divergencias DROP CONSTRAINT IF EXISTS uq_sw_lead_corretor_divergencias_tipo;
ALTER TABLE social_wiring.lead_corretor_divergencias
    ADD CONSTRAINT uq_sw_lead_corretor_divergencias_tipo UNIQUE (org_id, lead_id, codigo_canonical, tipo);

CREATE INDEX IF NOT EXISTS idx_sw_lead_corretor_divergencias_tipo
    ON social_wiring.lead_corretor_divergencias (org_id, tipo, status);
