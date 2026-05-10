-- ============================================================
-- 028 — Seed Imobi Scheduling product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Imobi Scheduling',
    'imobi-scheduling',
    'Real-estate media-crew scheduling bot via WhatsApp + Google Calendar (fresh implementation on seed patterns; consumes noctusai_lib chatbot + scheduling + tool-audit + WhatsApp/Calendar/Maps integrations)',
    'CalendarClock',
    'http://localhost:8160',
    '#10b981',
    true
)
ON CONFLICT (slug) DO NOTHING;
