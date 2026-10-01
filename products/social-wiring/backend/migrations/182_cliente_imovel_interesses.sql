-- ============================================================================
-- 182 — cliente_imovel_interesses: every imóvel a person has ever shown
--       interest in (source of the person page "Interesses" AND the imóvel
--       page "Interessados"), backfilled from the FULL lead history.
-- ============================================================================
-- origem: lead | manual | campanha | roteiro | permuta.
-- lead_id / meta_ads_lead_id keep the originating lead for the "last
-- interaction" / "lead created_at" reads (D5). At most one LIVE row per
-- (cliente, código): a second lead for the same imóvel does not duplicate.
--
-- BACKFILL: every `cliente_touches` row (the single lead→cliente map, 048)
-- whose lead carries a código (`leads.codigo_imovel_norm` /
-- `meta_ads_leads.codigo_imovel_norm`, 180). Códigos not yet in the registry
-- are registered first (as `registrar_imovel` would, origem 'lead').
-- When one cliente has several leads for one código the EARLIEST wins.
--
-- Forward-only, idempotent. NOT applied to prod here.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.cliente_imovel_interesses (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    cliente_id       UUID NOT NULL
        REFERENCES social_wiring.clientes (id) ON DELETE CASCADE,
    codigo           TEXT NOT NULL,
    origem           TEXT NOT NULL DEFAULT 'manual'
        CONSTRAINT cliente_imovel_interesses_origem_valida
        CHECK (origem IN ('lead', 'manual', 'campanha', 'roteiro', 'permuta')),
    lead_id          UUID REFERENCES social_wiring.leads (id) ON DELETE SET NULL,
    meta_ads_lead_id TEXT REFERENCES social_wiring.meta_ads_leads (id) ON DELETE SET NULL,
    created_by       UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ,
    CONSTRAINT cliente_imovel_interesses_registry_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
        ON DELETE RESTRICT,
    CONSTRAINT cliente_imovel_interesses_lead_unico
        CHECK (num_nonnulls(lead_id, meta_ads_lead_id) <= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_imovel_interesses_vivo
    ON social_wiring.cliente_imovel_interesses (cliente_id, codigo)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_cliente_imovel_interesses_codigo
    ON social_wiring.cliente_imovel_interesses (org_id, codigo, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_cliente_imovel_interesses_cliente
    ON social_wiring.cliente_imovel_interesses (org_id, cliente_id, created_at DESC)
    WHERE deleted_at IS NULL;

ALTER TABLE social_wiring.cliente_imovel_interesses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_imovel_interesses_select_own_org"
    ON social_wiring.cliente_imovel_interesses;
CREATE POLICY "cliente_imovel_interesses_select_own_org"
    ON social_wiring.cliente_imovel_interesses
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_imovel_interesses_service_role"
    ON social_wiring.cliente_imovel_interesses;
CREATE POLICY "cliente_imovel_interesses_service_role"
    ON social_wiring.cliente_imovel_interesses
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.cliente_imovel_interesses IS
    'Imóveis a cliente is/was interested in. One live row per (cliente, '
    'código). Source of the person page "Interesses" and the imóvel page '
    '"Interessados". Migration 182.';

-- ── Backfill: register unseen códigos, then insert one row per (cliente, código)
INSERT INTO social_wiring.imovel_registry (
    org_id, codigo_canonical, codigo_display, primeiro_visto_em,
    ativo_no_vista, origem_descoberta
)
SELECT l.org_id, l.codigo_imovel_norm,
       (array_agg(l.codigo_imovel ORDER BY l.created_at))[1],
       min(l.created_at), FALSE, 'lead'
  FROM social_wiring.leads l
 WHERE l.codigo_imovel_norm IS NOT NULL
 GROUP BY l.org_id, l.codigo_imovel_norm
ON CONFLICT (org_id, codigo_canonical) DO NOTHING;

WITH fonte AS (
    SELECT t.org_id, t.cliente_id, l.codigo_imovel_norm AS codigo,
           l.id AS lead_id, NULL::text AS meta_ads_lead_id,
           l.created_at AS ocorreu_em
      FROM social_wiring.cliente_touches t
      JOIN social_wiring.leads l
        ON t.origem_tabela = 'leads' AND t.origem_id = l.id::text
     WHERE l.codigo_imovel_norm IS NOT NULL
    UNION ALL
    SELECT t.org_id, t.cliente_id, m.codigo_imovel_norm,
           NULL::uuid, m.id,
           COALESCE(m.created_time, m.created_at)
      FROM social_wiring.cliente_touches t
      JOIN social_wiring.meta_ads_leads m
        ON t.origem_tabela = 'meta_ads_leads' AND t.origem_id = m.id
     WHERE m.codigo_imovel_norm IS NOT NULL
), primeiro AS (
    SELECT DISTINCT ON (cliente_id, codigo) *
      FROM fonte
     ORDER BY cliente_id, codigo, ocorreu_em
)
INSERT INTO social_wiring.cliente_imovel_interesses
    (org_id, cliente_id, codigo, origem, lead_id, meta_ads_lead_id, created_at)
SELECT p.org_id, p.cliente_id, r.codigo_canonical, 'lead',
       p.lead_id, p.meta_ads_lead_id, p.ocorreu_em
  FROM primeiro p
  JOIN social_wiring.imovel_registry r
    ON r.org_id = p.org_id AND r.codigo_canonical = p.codigo
ON CONFLICT DO NOTHING;

NOTIFY pgrst, 'reload schema';
