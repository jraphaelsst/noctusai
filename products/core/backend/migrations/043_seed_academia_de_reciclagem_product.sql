-- ============================================================
-- 043 — Seed Academia de Reciclagem product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Academia de Reciclagem',
    'academia-de-reciclagem',
    'Julia, assistente virtual da Academia de Reciclagem — chat web e WhatsApp sobre uma base de conhecimento viva',
    'Recycle',
    'http://localhost:8015',
    '#16a34a',
    true
)
ON CONFLICT (slug) DO NOTHING;
