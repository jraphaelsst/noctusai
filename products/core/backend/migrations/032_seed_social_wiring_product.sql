-- ============================================================
-- 032 — Seed Social Wiring product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Social Wiring',
    'social-wiring',
    'Multi-channel media-wiring CMS — wires WhatsApp/chat conversational AI, Google (Calendar/Maps/Drive), Meta (Facebook/Instagram) and YouTube into one place; consolidates the retired media-scheduling, youtube-crawler, mailing and imobi-scheduling products.',
    'Share2',
    'http://localhost:8160',
    '#a855f7',
    true
)
ON CONFLICT (slug) DO NOTHING;
