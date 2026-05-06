-- ============================================================
-- 013 — Seed Media Scheduling product row
-- ============================================================
-- Auto-registers the media-scheduling product so it appears on the
-- noc dashboard (Dashboard.tsx reads /api/auth/me which joins the
-- public.products table).
--
-- Authored alongside the new "scaffold auto-registers products"
-- methodology rule — every newly-scaffolded product ships a
-- companion seed-row migration so the dashboard never lags the
-- filesystem. See KB § GUIDES/new-product.md.
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Media Scheduling',
    'media-scheduling',
    'Agendamento e publicação de conteúdo em redes sociais.',
    'CalendarDays',
    'http://localhost:8140',
    '#3b82f6',
    true
)
ON CONFLICT (slug) DO NOTHING;
