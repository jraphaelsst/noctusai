-- ============================================================================
-- Migration 017 -- WhatsApp per-app switch + borrowed sessions + lead edit marker
--
-- * monica.whatsapp_connections.app_enabled  -- the app's on/off switch for a line (off => this app ignores its
--   traffic; other apps on the same WAHA session are unaffected).
-- * monica.whatsapp_connections.session_role -- 'owner' | 'borrower' (a borrower shares another app's session and
--   never drives its lifecycle). Output of the seed helper `app_switch_alter_ddl("monica")`.
-- * monica.leads.edited_at -- set by a HUMAN edit / stage move only; the testing-phase purge keeps such leads.
-- Forward-only + idempotent (re-apply safe). NOT applied by the slice that authored it.
-- ============================================================================

SET search_path = monica, public;

ALTER TABLE monica.whatsapp_connections
    ADD COLUMN IF NOT EXISTS app_enabled BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS session_role TEXT NOT NULL DEFAULT 'owner';
ALTER TABLE monica.whatsapp_connections DROP CONSTRAINT IF EXISTS whatsapp_connections_session_role_check;
ALTER TABLE monica.whatsapp_connections ADD CONSTRAINT whatsapp_connections_session_role_check CHECK (session_role IN ('owner', 'borrower'));

ALTER TABLE monica.leads ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;
