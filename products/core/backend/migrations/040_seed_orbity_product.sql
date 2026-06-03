-- ============================================================
-- 040 — Seed Orbity product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Orbity',
    'orbity',
    NULL,
    'Box',
    'http://localhost:8010',
    '#6366f1',
    true
)
ON CONFLICT (slug) DO NOTHING;
