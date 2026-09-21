-- 145_custos_nav_route.sql — register /custos in status_pagina
--
-- `GET /api/custos` (Custos page, this slice) ships alongside
-- `products/social-wiring/frontend/src/pages/Custos.tsx`, declared in
-- App.tsx NAV_GROUPS as `route: "custos"`. Without a matching
-- `status_pagina` row the seed `filterNavByPageStatus` gate hides the nav
-- item silently — same shape 018/021/023/039/084 exist to close.
--
-- Seeded 'producao': the page ships complete (four states, real
-- org-scoped data from `llm_usage` + `cost_ledger`) — see
-- `projects/`-level report for the two integrations (D4Sign, Google Maps)
-- deliberately left uninstrumented rather than shipped with an invented
-- price.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY — not applied to any database by this
-- change (per dispatch brief: report the migration, do not apply it).
-- Idempotent: ON CONFLICT DO NOTHING.

SET search_path = social_wiring, public;

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('custos', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Backfill: InfoSimples calls made BEFORE cost booking existed.
--
-- Every consulta's latest raw response is kept in
-- `certidao_resultados.api_response`, and its `header.price` (BRL string) /
-- `header.billable` are the provider's own charge record — verified on the
-- 215 rows present on 2026-09-21. One ledger row per resultado that has a
-- billable price and no booking yet, so re-running this is a no-op.
-- Limitation (stated, not hidden): only the LATEST response per resultado is
-- stored, so a resultado retried before this migration is booked once.
-- ---------------------------------------------------------------------------
INSERT INTO public.cost_ledger (
    org_id, category, step, reference_type, reference_id,
    amount_native, currency, fx_pending, amount_brl, created_at
)
SELECT
    r.org_id,
    'infosimples',
    'certidoes.' || r.tipo,
    'certidao_consulta',
    r.id::text,
    (r.api_response->'header'->>'price')::numeric,
    'BRL',
    false,
    (r.api_response->'header'->>'price')::numeric,
    r.created_at
FROM social_wiring.certidao_resultados r
WHERE r.org_id IS NOT NULL
  AND (r.api_response->'header'->>'billable')::boolean IS TRUE
  AND (r.api_response->'header'->>'price') ~ '^[0-9]+(\.[0-9]+)?$'
  AND NOT EXISTS (
      SELECT 1 FROM public.cost_ledger c
      WHERE c.reference_type = 'certidao_consulta'
        AND c.reference_id = r.id::text
  );
