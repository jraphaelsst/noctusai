-- ============================================================
-- 034 — Seed Knowledge Extractor product row
-- ============================================================
-- Registers the absorbed knowledge-extractor product on the noc
-- dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Mirror to the live DB via Supabase MCP
-- apply_migration ("MCP migrations mirror the file" rule).
--
-- url_base stays localhost by design — prod overrides via the
-- PRODUCT_URL_KNOWLEDGE_EXTRACTOR env (resolve_product_url scheme;
-- see KB § PATTERNS/dev-prod-parity.md). Backend-only product:
-- the single container serves on 8012.
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Knowledge Extractor',
    'knowledge-extractor',
    'Course-methodology RAG: ingests recorded classes from Google Drive, transcribes + summarizes them, and extracts the methodology into a pgvector knowledge base. Backend-only; absorbed from the sibling knowledge-extractor repo 2026-05-23.',
    'BookOpen',
    'http://localhost:8012',
    '#0ea5e9',
    true
)
ON CONFLICT (slug) DO NOTHING;
