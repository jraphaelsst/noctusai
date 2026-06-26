-- 017_whatsapp_connection_client.sql — link WhatsApp connections to clients
--
-- Adds a nullable FK from whatsapp_connections → social_wiring.clients so
-- that a WAHA connection can be owned by a cliente (0..N connections per
-- cliente).  Mirrors the integration_accounts.client_id column added by
-- migration 008.
--
-- Design decisions:
--   - Nullable (no DEFAULT): an existing connection has no cliente; new
--     connections may be created with or without one.
--   - ON DELETE SET NULL: archiving a cliente does not cascade-delete its
--     connections; the link is cleared instead.
--   - Composite index on (org_id, client_id) powers the FE "list a
--     cliente's WA connections" query (GET /api/whatsapp/connections?client_id=).
--   - Code reads defensively (row.get("client_id")) so an un-migrated DB
--     row (column absent) degrades gracefully, never crashes.
--
-- Forward-only + idempotent (ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).
-- Apply after 016.  The tech-lead applies this via noctus.dev.migrate_product
-- with explicit consent — DO NOT apply directly to the live DB from this file.

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS client_id uuid REFERENCES social_wiring.clients(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_whatsapp_connections_org_client
    ON social_wiring.whatsapp_connections (org_id, client_id);
