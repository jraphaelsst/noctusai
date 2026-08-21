-- ============================================================================
-- Migration 063 -- social_wiring: imovel_registry, our permanent imóvel identity
--
-- THE PROBLEM
-- -----------
-- `social_wiring.imoveis` is a MIRROR of the Vista catalog. Vista's
-- `/imoveis/listar` returns only ACTIVE listings, so the mirror shrinks when
-- an imóvel is sold, rented or delisted — while every record of ours that
-- referenced it (leads, vendas, and soon campanhas) keeps pointing at it
-- forever.
--
-- Measured on the live tenant 2026-08-21, AFTER migration 062 fixed the
-- case-folding:
--
--   leads with a código        11375
--   resolve against the mirror  4198  (36.9%)
--   do NOT resolve              7177  (63.1%)
--
-- Of the non-resolving codes, 1019 of 1021 distinct values are perfectly
-- well-formed (`ONE4770`, `CA5180`) — real imóveis that have left the
-- catalog, not typos. Only 2 are malformed.
--
-- CONSEQUENCE: no FK from `leads` to `imoveis` is possible, now or ever. It
-- would reject 63% of history. This is the single fact the whole campaign
-- model turns on.
--
-- THE SHAPE: mirror is disposable, registry is ours
-- -------------------------------------------------
-- `imoveis`         — cache of what Vista says TODAY. Overwritten nightly.
--                     Delete it entirely and the next sync rebuilds it.
-- `imovel_registry` — one row per código we have EVER seen, from any source.
--                     APPEND-ONLY: nothing is ever deleted. Everything of
--                     ours joins HERE, never to the mirror.
--
-- WHY THE SNAPSHOT COLUMNS (user-ratified 2026-08-20, decision D1)
-- ----------------------------------------------------------------
-- `snap_*` duplicates a handful of fields that also live in the mirror. That
-- is deliberate and it is the only duplication in this design.
--
-- Without it, "how many leads did ONE4770 generate" renders a row with no
-- title, no neighbourhood and no photo, because the imóvel sold in 2024 and
-- left the mirror. With it, the history stays legible forever.
--
-- The snapshot is written ONLY at delist time — while an imóvel is active the
-- UI reads the mirror, so there is no live duplicate to drift. `snap_em`
-- records when the copy was taken, so a stale-looking value is explainable
-- rather than mysterious.
--
-- PREREQUISITE: 040_imoveis.sql, 025_leads.sql, 043_lead_campanhas_vendas.sql,
--               062_codigo_imovel_canonical.sql (supplies `codigo_norm` /
--               `codigo_imovel_norm`, which the backfill joins on).
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ── The registry ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.imovel_registry (
    id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID        NOT NULL,

    -- The canonical código: `upper(btrim(...))`, the same expression
    -- migration 062 uses everywhere. This is the join key.
    codigo_canonical          TEXT        NOT NULL,
    -- The spelling we first saw, kept for display and for tracing where a
    -- row came from. Never used for matching.
    codigo_display            TEXT,

    -- Lifecycle.
    primeiro_visto_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_visto_no_vista_em  TIMESTAMPTZ,
    -- Default FALSE, not TRUE: a row created from a LEAD has never been seen
    -- in the catalog, and claiming otherwise would make the delist sweep
    -- immediately "delist" something it never listed.
    ativo_no_vista            BOOLEAN     NOT NULL DEFAULT FALSE,
    delistado_em              TIMESTAMPTZ,

    -- How we learned this código exists. Not a provenance flag on the imóvel
    -- (Vista is the source of truth for imóveis) — it answers "why does this
    -- row exist at all", which matters when 1019 of them describe imóveis the
    -- catalog has never shown us.
    origem_descoberta         TEXT        NOT NULL DEFAULT 'desconhecida',
    CONSTRAINT imovel_registry_origem_descoberta_valida CHECK (
        origem_descoberta IN ('vista_sync', 'lead', 'venda', 'intake', 'manual', 'desconhecida')
    ),

    -- Last-known state, copied from the mirror at delist time. See the header.
    snap_titulo               TEXT,
    snap_categoria            TEXT,
    snap_status               TEXT,
    snap_bairro               TEXT,
    snap_cidade               TEXT,
    snap_uf                   TEXT,
    snap_valor_venda          NUMERIC(14, 2),
    snap_valor_locacao        NUMERIC(14, 2),
    snap_dormitorios          INTEGER,
    snap_area_total           NUMERIC(12, 2),
    snap_foto_destaque        TEXT,
    snap_em                   TIMESTAMPTZ,

    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Tenant-scoped, exactly like `imoveis`: `codigo` is unique WITHIN a
    -- Vista tenant, never globally.
    CONSTRAINT uq_imovel_registry_org_codigo UNIQUE (org_id, codigo_canonical)
);

ALTER TABLE social_wiring.imovel_registry ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_registry_select_own_org" ON social_wiring.imovel_registry;
CREATE POLICY "imovel_registry_select_own_org" ON social_wiring.imovel_registry
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_registry_service_role" ON social_wiring.imovel_registry;
CREATE POLICY "imovel_registry_service_role" ON social_wiring.imovel_registry
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_registry_org_ativo
    ON social_wiring.imovel_registry (org_id, ativo_no_vista);
CREATE INDEX IF NOT EXISTS idx_sw_imovel_registry_org_delistado
    ON social_wiring.imovel_registry (org_id, delistado_em)
    WHERE delistado_em IS NOT NULL;

CREATE OR REPLACE FUNCTION social_wiring.touch_imovel_registry_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_imovel_registry_updated_at ON social_wiring.imovel_registry;
CREATE TRIGGER trg_imovel_registry_updated_at
    BEFORE UPDATE ON social_wiring.imovel_registry
    FOR EACH ROW EXECUTE FUNCTION social_wiring.touch_imovel_registry_updated_at();

-- ── Backfill A -- everything currently in the mirror ─────────────────────
-- These ARE active by definition: the mirror only holds what the last sync
-- returned.
INSERT INTO social_wiring.imovel_registry (
    org_id, codigo_canonical, codigo_display, primeiro_visto_em,
    ultimo_visto_no_vista_em, ativo_no_vista, origem_descoberta
)
SELECT
    i.org_id,
    i.codigo_norm,
    i.codigo,
    COALESCE(i.created_at, now()),
    i.sincronizado_em,
    TRUE,
    'vista_sync'
FROM social_wiring.imoveis i
ON CONFLICT (org_id, codigo_canonical) DO NOTHING;

-- ── Backfill B -- every código a LEAD ever referenced ────────────────────
-- The 1019 orphans land here. `ativo_no_vista` stays FALSE and
-- `delistado_em` stays NULL: we do not know WHEN they left the catalog, and
-- inventing a timestamp would be worse than admitting we cannot know.
-- `primeiro_visto_em` uses the earliest lead that named the código, which is
-- a real, defensible date.
INSERT INTO social_wiring.imovel_registry (
    org_id, codigo_canonical, codigo_display, primeiro_visto_em,
    ativo_no_vista, origem_descoberta
)
SELECT
    l.org_id,
    l.codigo_imovel_norm,
    (array_agg(l.codigo_imovel ORDER BY l.created_at))[1],
    min(l.created_at),
    FALSE,
    'lead'
FROM social_wiring.leads l
WHERE l.codigo_imovel_norm IS NOT NULL
GROUP BY l.org_id, l.codigo_imovel_norm
ON CONFLICT (org_id, codigo_canonical) DO NOTHING;

-- ── Backfill C -- vendas (empty today, correct tomorrow) ─────────────────
INSERT INTO social_wiring.imovel_registry (
    org_id, codigo_canonical, codigo_display, primeiro_visto_em,
    ativo_no_vista, origem_descoberta
)
SELECT
    v.org_id,
    v.codigo_imovel_norm,
    (array_agg(v.codigo_imovel ORDER BY v.created_at))[1],
    min(v.created_at),
    FALSE,
    'venda'
FROM social_wiring.lead_vendas v
WHERE v.codigo_imovel_norm IS NOT NULL
GROUP BY v.org_id, v.codigo_imovel_norm
ON CONFLICT (org_id, codigo_canonical) DO NOTHING;

-- ── The referencing columns ─────────────────────────────────────────────
-- NULLABLE and ON DELETE RESTRICT. Nullable because a lead legitimately has
-- no código (2037 of them). RESTRICT rather than CASCADE because the registry
-- is append-only — a delete should be impossible, and if one is ever
-- attempted it must fail loudly rather than silently take leads with it.
ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS imovel_ref_id UUID
    REFERENCES social_wiring.imovel_registry (id) ON DELETE RESTRICT;

ALTER TABLE social_wiring.lead_vendas
    ADD COLUMN IF NOT EXISTS imovel_ref_id UUID
    REFERENCES social_wiring.imovel_registry (id) ON DELETE RESTRICT;

UPDATE social_wiring.leads l
   SET imovel_ref_id = r.id
  FROM social_wiring.imovel_registry r
 WHERE r.org_id = l.org_id
   AND r.codigo_canonical = l.codigo_imovel_norm
   AND l.codigo_imovel_norm IS NOT NULL
   AND l.imovel_ref_id IS DISTINCT FROM r.id;

UPDATE social_wiring.lead_vendas v
   SET imovel_ref_id = r.id
  FROM social_wiring.imovel_registry r
 WHERE r.org_id = v.org_id
   AND r.codigo_canonical = v.codigo_imovel_norm
   AND v.codigo_imovel_norm IS NOT NULL
   AND v.imovel_ref_id IS DISTINCT FROM r.id;

CREATE INDEX IF NOT EXISTS idx_sw_leads_imovel_ref
    ON social_wiring.leads (imovel_ref_id)
    WHERE imovel_ref_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_lead_vendas_imovel_ref
    ON social_wiring.lead_vendas (imovel_ref_id)
    WHERE imovel_ref_id IS NOT NULL;

-- ── The delist sweep ────────────────────────────────────────────────────
-- Called by the nightly sync AFTER the catalog upsert, in the same
-- transaction-ish window. Two jobs, in this order:
--
--   1. Mark everything the sync just touched as active + seen.
--   2. Anything active whose código is NO LONGER in the mirror has left the
--      catalog: copy its last-known state, then flip it inactive.
--
-- Step 2 reads `imoveis` BEFORE the row disappears — which works because the
-- sync UPSERTS and never deletes. The mirror therefore accumulates; a row
-- leaves it only when a future cleanup removes it. So "no longer in the
-- mirror" is detected by `sincronizado_em` falling behind the run, not by
-- absence. That is the honest signal and it is why `p_run_at` is a parameter
-- rather than `now()` — the caller passes the timestamp the sync stamped.
CREATE OR REPLACE FUNCTION social_wiring.sweep_imovel_registry(
    p_org_id UUID,
    p_run_at TIMESTAMPTZ
)
RETURNS TABLE (marcados_ativos INTEGER, marcados_delistados INTEGER)
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_ativos INTEGER := 0;
    v_delistados INTEGER := 0;
BEGIN
    -- 1. Present in this run ⇒ active. Also (re)creates nothing: rows are
    --    inserted by the sync's own upsert path before this runs.
    WITH presentes AS (
        SELECT codigo_norm FROM social_wiring.imoveis
         WHERE org_id = p_org_id AND sincronizado_em >= p_run_at
    )
    UPDATE social_wiring.imovel_registry r
       SET ativo_no_vista = TRUE,
           ultimo_visto_no_vista_em = p_run_at,
           delistado_em = NULL
      FROM presentes p
     WHERE r.org_id = p_org_id
       AND r.codigo_canonical = p.codigo_norm;
    GET DIAGNOSTICS v_ativos = ROW_COUNT;

    -- 2. Was active, not present in this run ⇒ delisted. Snapshot FIRST,
    --    from the mirror row that is about to become stale.
    WITH ausentes AS (
        SELECT r.id, r.codigo_canonical
          FROM social_wiring.imovel_registry r
         WHERE r.org_id = p_org_id
           AND r.ativo_no_vista
           AND NOT EXISTS (
               SELECT 1 FROM social_wiring.imoveis i
                WHERE i.org_id = p_org_id
                  AND i.codigo_norm = r.codigo_canonical
                  AND i.sincronizado_em >= p_run_at
           )
    )
    UPDATE social_wiring.imovel_registry r
       SET ativo_no_vista = FALSE,
           delistado_em = p_run_at,
           snap_titulo        = i.titulo,
           snap_categoria     = i.categoria,
           snap_status        = i.status,
           snap_bairro        = i.bairro,
           snap_cidade        = i.cidade,
           snap_uf            = i.uf,
           snap_valor_venda   = i.valor_venda,
           snap_valor_locacao = i.valor_locacao,
           snap_dormitorios   = i.dormitorios,
           snap_area_total    = i.area_total,
           snap_foto_destaque = i.foto_destaque,
           snap_em            = p_run_at
      FROM ausentes a
      LEFT JOIN social_wiring.imoveis i
             ON i.org_id = p_org_id AND i.codigo_norm = a.codigo_canonical
     WHERE r.id = a.id;
    GET DIAGNOSTICS v_delistados = ROW_COUNT;

    RETURN QUERY SELECT v_ativos, v_delistados;
END;
$$;
