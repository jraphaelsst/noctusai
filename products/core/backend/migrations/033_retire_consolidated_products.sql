-- ============================================================
-- 033 — Retire products consolidated into social-wiring
-- ============================================================
-- social-wiring-absorption Wave 4 (2026-05-16). The four products
-- below were consolidated into `social-wiring` (registered by 032):
--   media-scheduling, imobi-scheduling, youtube-crawler, mailing.
-- Their domains were absorbed in Wave 2 (mailing -> email_marketing,
-- imobi -> scheduling) or were stale. The noc dashboard reads
-- public.products dynamically (Dashboard.tsx -> /api/auth/me), so a
-- retired product must be UN-registered by a NEW forward migration —
-- NOT by editing historical seed-row migrations 013/028 (immutable
-- per single-001 + lock-step-additive convention).
--
-- `youtube-crawler` / `mailing` likely never had a core seed-row
-- migration; the IN-list DELETE is an idempotent no-op for any slug
-- whose row is already absent (defensive + documents intent).
--
-- Apply via Supabase MCP apply_migration to mirror onto the live DB
-- ("MCP migrations mirror the file" rule).
-- ============================================================

DELETE FROM public.products
WHERE slug IN (
    'media-scheduling',
    'imobi-scheduling',
    'youtube-crawler',
    'mailing'
);
