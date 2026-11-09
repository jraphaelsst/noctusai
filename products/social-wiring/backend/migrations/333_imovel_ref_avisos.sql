-- ============================================================================
-- Migration 333 -- social_wiring: ref-divergence notices (the Vista sync never erases OUR data; it WARNS) (owner 2026-11-09)
-- ============================================================================
-- Owner: "the sync doesnt erase our generated data, the sync warn us about divergences. 'daily updates' are okay, but not when
-- refs diverge: we have something they dont, or vice-versa. We only create on our side, never delete; I get warned and investigate."
--   ref_sumiu_no_vista : a ref we have that Vista no longer has. Every datum is kept; the imóvel is PAUSED (imoveis.exibir_no_site=false,
--                        which the site, Julia and the campaign cards already honour) until a human restores it or confirms it gone.
--   ref_nova_no_vista  : a ref Vista has that we did not (discovery / intake): created on our side, recorded here (informational).
-- A SIBLING of lead_corretor_divergencias (not one generalised table): different subject (an imóvel, no lead), different resolutions
-- (restaurar / confirmar_sumiu / ciente vs resolvida / ignorada), different open-uniqueness key.
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible with the previous image (a new table only). Backend-only: RLS on, service role only.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.imovel_ref_avisos (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            uuid        NOT NULL,
    codigo_canonical  text        NOT NULL,
    tipo              text        NOT NULL CHECK (tipo IN ('ref_sumiu_no_vista', 'ref_nova_no_vista')),
    status            text        NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'restaurada', 'confirmada_sumiu', 'ciente')),
    exibir_antes      boolean,
    notas             jsonb       NOT NULL DEFAULT '[]'::jsonb,
    notificado_em     timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    resolvido_em      timestamptz,
    resolvido_por     uuid
);

-- one OPEN notice per (imóvel, tipo): no spam, and the sync reads this to keep a paused imóvel paused
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_imovel_ref_avisos_aberto
    ON social_wiring.imovel_ref_avisos (org_id, codigo_canonical, tipo) WHERE status = 'pendente';
CREATE INDEX IF NOT EXISTS idx_sw_imovel_ref_avisos_lista
    ON social_wiring.imovel_ref_avisos (org_id, tipo, status, created_at DESC);

ALTER TABLE social_wiring.imovel_ref_avisos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS imovel_ref_avisos_service_role ON social_wiring.imovel_ref_avisos;
CREATE POLICY imovel_ref_avisos_service_role ON social_wiring.imovel_ref_avisos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.imovel_ref_avisos FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.imovel_ref_avisos TO service_role;

COMMENT ON TABLE social_wiring.imovel_ref_avisos IS 'tier:org';
