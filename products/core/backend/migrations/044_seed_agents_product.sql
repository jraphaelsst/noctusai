-- ============================================================
-- 044 — Seed Agentes product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Agentes',
    'agents',
    'Casa dos agentes da NoctusAI — converse com a Julia, aprove o que ela faz e ligue ou desligue cada agente',
    'Bot',
    'http://localhost:8016',
    '#7c3aed',
    true
)
ON CONFLICT (slug) DO NOTHING;
