-- ============================================================================
-- 355_julia_portal_primeiro_contato.sql -- Lais study S1 (owner "go on" 2026-11-17)
-- ============================================================================
-- Julia speaks first to PORTAL leads (ZAP / VivaReal, ImovelWeb, OLX) -- a normal WAHA first message carrying the AI
-- disclosure + the privacy-notice link -- and never re-opens on a portal re-entry. Per-org switch, OFF by default:
-- `julia_reengajamento_config.portal_primeiro_contato_ativo` (the owner turns it on in Julia > Reengajamento).
--
-- FORWARD-ONLY, IDEMPOTENT. No SECURITY DEFINER. RLS of the table is untouched. The opener's outcome rides the existing
-- append-only `julia_eventos` table (type `primeiro_contato_portal`, token-shaped CHECK only) -- no new table.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.julia_reengajamento_config
    ADD COLUMN IF NOT EXISTS portal_primeiro_contato_ativo boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN social_wiring.julia_reengajamento_config.portal_primeiro_contato_ativo IS
    'Lais study S1 (migration 355): Julia opens the conversation with a new portal lead (OLX / ImovelWeb) only when true. Default false.';
