-- 019_mailchimp_connection_client.sql — make Mailchimp connections per-cliente
--
-- Adds a nullable FK from mailchimp_connections → social_wiring.clients so a
-- cliente can own their own Mailchimp connection. Mirrors migration 017
-- (whatsapp_connections.client_id) and migration 008 (integration_accounts).
--
-- Scope change: migration 013 declared a single connection per org
-- (``org_id UUID NOT NULL UNIQUE`` → the auto-named constraint
-- ``mailchimp_connections_org_id_key``). This migration relaxes that to
-- at-most-one-per-SCOPE, where scope = (org_id, client_id):
--   - exactly one org-level default row (client_id IS NULL), and
--   - at most one row per cliente (client_id IS NOT NULL).
-- Enforced by TWO partial unique indexes (a plain UNIQUE(org_id, client_id)
-- would allow multiple client_id-NULL rows, since NULLs are distinct).
--
-- Design decisions:
--   - Nullable (no DEFAULT): existing rows have no cliente → org-level default.
--     Backward-compatible — downstream features (contacts/segments/campaigns)
--     that call get_connection(org_id) keep resolving the org-default row.
--   - ON DELETE SET NULL: archiving a cliente does not cascade-delete its
--     connection; the link is cleared, the row demotes to org-level.
--   - Code reads defensively (row.get("client_id")) so an un-migrated DB row
--     (column absent) degrades gracefully.
--
-- Forward-only + idempotent (DROP CONSTRAINT IF EXISTS / ADD COLUMN IF NOT
-- EXISTS / CREATE ... IF NOT EXISTS). Apply after 018. The tech-lead applies
-- this via noctus.dev.migrate_product with explicit consent — DO NOT apply
-- directly to the live DB from this file.
--
-- NOTE: the dropped constraint name assumes the Postgres default for the
-- inline column ``UNIQUE`` in migration 013 (``<table>_<column>_key``). If a
-- prior manual migration renamed it, confirm via ``\d
-- social_wiring.mailchimp_connections`` before applying.

SET search_path = social_wiring, public;

-- 1. Relax the one-connection-per-org constraint (migration 013).
ALTER TABLE social_wiring.mailchimp_connections
    DROP CONSTRAINT IF EXISTS mailchimp_connections_org_id_key;

-- 2. Add the nullable cliente link.
ALTER TABLE social_wiring.mailchimp_connections
    ADD COLUMN IF NOT EXISTS client_id UUID
        REFERENCES social_wiring.clients(id) ON DELETE SET NULL;

-- 3. Re-establish at-most-one-per-scope via two partial unique indexes.
--    (a) one org-level default connection.
CREATE UNIQUE INDEX IF NOT EXISTS ux_sw_mailchimp_connections_org_default
    ON social_wiring.mailchimp_connections (org_id)
    WHERE client_id IS NULL;

--    (b) one connection per cliente.
CREATE UNIQUE INDEX IF NOT EXISTS ux_sw_mailchimp_connections_org_client
    ON social_wiring.mailchimp_connections (org_id, client_id)
    WHERE client_id IS NOT NULL;

-- 4. Plain composite index to power the "a cliente's connection" lookup.
CREATE INDEX IF NOT EXISTS idx_sw_mailchimp_connections_org_client
    ON social_wiring.mailchimp_connections (org_id, client_id);
