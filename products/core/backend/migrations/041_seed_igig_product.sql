-- ============================================================
-- 041 — Seed IgIg product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'IgIg',
    'igig',
    'ERP para agência de comunicação: produção criativa, marca, publicação e financeiro.',
    'Palette',
    'http://localhost:8013',
    '#f97316',
    true
)
ON CONFLICT (slug) DO NOTHING;
