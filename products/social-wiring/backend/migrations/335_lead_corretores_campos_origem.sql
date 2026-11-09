-- ============================================================================
-- Migration 335 -- social_wiring: where a broker's Vista-sourced fields came from (owner 2026-11-09)
-- ============================================================================
-- `/corretores/listar` returns only Codigo+Nome on this tenant; the richer fields (Equipe, Gerente, Agenciador, Corretor, Email, Fone) come
-- through the PROPERTY detail's `Corretor` relation and fill lead_corretores' EMPTY columns only (never overwriting). `campos_origem` records it.
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible (one nullable column).
-- ============================================================================
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.lead_corretores ADD COLUMN IF NOT EXISTS campos_origem text;
COMMENT ON COLUMN social_wiring.lead_corretores.campos_origem IS
    'imovel_relacao when equipe/gerente/agenciador/eh_corretor/email/celular were filled from a property''s Corretor relation';
