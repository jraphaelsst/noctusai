-- ============================================================
-- 036 — Reconcile the dashboard product catalog with the tree
-- ============================================================
-- The noc launcher (Dashboard.tsx → GET /api/auth/me → public.products)
-- must list EXACTLY the products that exist as `products/<slug>/` folders
-- — no phantoms, no missing entries. This migration brings the catalog in
-- line with the tree and makes it reproducible on a fresh DB:
--
--   1. Ensure a row for every real product folder (idempotent INSERT). The
--      three absorbed/scaffolded products that never got a live row —
--      adconnect, dev-team, knowledge-extractor — are seeded here; the five
--      already-present rows are untouched (ON CONFLICT DO NOTHING).
--   2. Normalize legacy emoji icons → Lucide icon names. The frontend renders
--      `icone` as a lucide-react component by name (emoji kept as a fallback),
--      so the scaffolder convention (Lucide names, default "Box") is the
--      catalog norm. Older hand-seeded rows used emoji.
--   3. Remove the non-product `seed` row — `products/seed/` is the product
--      TEMPLATE, not a product; it must never appear on the launcher.
--
-- EXCLUDED on purpose: `core` (the launcher host itself, not a tile).
--
-- "Deployed" is NOT a column — it is determined at runtime by the
-- GET /api/products/deployment-status probe (container reachable on
-- noctus-net), so a product can be deployed in dev but not prod with one
-- catalog. A listed-but-not-deployed product shows a "dev" badge.
--
-- url_base stays localhost by design — prod overrides per-product via the
-- PRODUCT_URL_<SLUG> env (resolve_product_url scheme; see
-- KB § PATTERNS/dev-prod-parity.md).
--
-- Mirror to the live DB via Supabase MCP apply_migration ("MCP migrations
-- mirror the file" rule). Idempotent — safe to re-apply.
-- ============================================================

-- ─── 1. Ensure every real product folder has a catalog row ───
INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES
    ('ERP Imobiliário', 'erp-imobiliario',
     'Sistema completo para gestão de imobiliárias: clientes, imóveis, permutas, matching inteligente e metas.',
     'Building2', 'http://localhost:8080', '#10b981', true),
    ('Finanças Pessoais', 'personal-finance',
     'Gestao inteligente de financas pessoais, investimentos e patrimonio',
     'Wallet', 'http://localhost:8090', '#10b981', true),
    ('Plataforma de Terapia', 'therapy-platform',
     'Plataforma online de terapia: video, agendamento, prontuario digital e gestao financeira',
     'Brain', 'http://localhost:8095', '#8b5cf6', true),
    ('Daily Life', 'daily-life',
     'Hub de produtividade pessoal: tarefas, metas, agenda, notas, foco e metricas',
     'CalendarCheck', 'http://localhost:8110', '#10b981', true),
    ('Social Wiring', 'social-wiring',
     'Multi-channel media-wiring CMS — wires WhatsApp/chat conversational AI, Google (Calendar/Maps/Drive), Meta (Facebook/Instagram) and YouTube into one place; consolidates the retired media-scheduling, youtube-crawler, mailing and imobi-scheduling products.',
     'Share2', 'http://localhost:8160', '#a855f7', true),
    ('AdConnect', 'adconnect',
     'Marketplace B2B que conecta marcas à sua rede de distribuidores: catálogo com preços preferenciais, pedidos e cashback por relatórios de sellout.',
     'Store', 'http://localhost:8130', '#f59e0b', true),
    ('Dev Team', 'dev-team',
     'Time de desenvolvimento multi-agente (agno): 11 especialistas e 3 subtimes que planejam, implementam e revisam código via API e interface web.',
     'Bot', 'http://localhost:8123', '#6366f1', true),
    ('Knowledge Extractor', 'knowledge-extractor',
     'Course-methodology RAG: ingests recorded classes from Google Drive, transcribes + summarizes them, and extracts the methodology into a pgvector knowledge base. Backend-only; absorbed from the sibling knowledge-extractor repo 2026-05-23.',
     'BookOpen', 'http://localhost:8012', '#0ea5e9', true)
ON CONFLICT (slug) DO NOTHING;

-- ─── 2. Normalize legacy emoji icons → Lucide names (guarded) ───
UPDATE public.products SET icone = 'Building2' WHERE slug = 'erp-imobiliario'  AND icone = '🏠';
UPDATE public.products SET icone = 'Wallet'    WHERE slug = 'personal-finance' AND icone = '💰';
UPDATE public.products SET icone = 'Brain'     WHERE slug = 'therapy-platform' AND icone = '🧠';

-- ─── 3. Remove the non-product `seed` template row ───
DELETE FROM public.products WHERE slug = 'seed';
