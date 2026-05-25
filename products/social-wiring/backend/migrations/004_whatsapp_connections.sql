-- 004_whatsapp_connections.sql — per-user, multi-session WAHA connection "lines".
--
-- Project: social-wiring-waha-youtube (2026-05-25). Lets an operator manage
-- MULTIPLE WAHA sessions straight from the product UI (the "Conexão" page)
-- instead of the WAHA dashboard: each row = one connection "line" carrying its
-- own WAHA server URL + session name + API key. The API key is the only secret
-- and is Fernet-encrypted at rest with the SAME ENCRYPTION_KEY the
-- `credentials` table uses (via the product `credential_vault` seam over the
-- seed Fernet primitive). Rows are ISOLATED PER USER (`user_id` owner) within
-- an org — a user only ever sees/manages their own lines.
--
-- Forward-only + idempotent (001/002/003 already in prod). RLS org-scoped AND
-- user-scoped, mirroring the shape used across this schema. Apply to the
-- noctusai Supabase (social_wiring schema) at deploy.

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.whatsapp_connections (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    user_id           UUID NOT NULL,                  -- owner; per-user isolation
    label             TEXT NOT NULL,
    base_url          TEXT NOT NULL,                  -- WAHA server URL
    session_name      TEXT NOT NULL DEFAULT 'default',
    encrypted_api_key TEXT NOT NULL,                  -- Fernet(api_key) — never plaintext
    webhook_url       TEXT,                           -- last-wired inbound webhook (optional)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, user_id, label)
);

ALTER TABLE social_wiring.whatsapp_connections ENABLE ROW LEVEL SECURITY;

-- Per-user isolation: a user reads only their OWN lines within their own org.
-- (The backend writes through the service-role/admin client and filters
-- org_id + user_id explicitly on every query — defense in depth.)
DROP POLICY IF EXISTS "whatsapp_connections_select_own" ON social_wiring.whatsapp_connections;
CREATE POLICY "whatsapp_connections_select_own" ON social_wiring.whatsapp_connections
    FOR SELECT TO authenticated
    USING (
        org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        AND user_id = (SELECT auth.uid())
    );

DROP POLICY IF EXISTS "whatsapp_connections_service_role" ON social_wiring.whatsapp_connections;
CREATE POLICY "whatsapp_connections_service_role" ON social_wiring.whatsapp_connections
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_whatsapp_connections_owner
    ON social_wiring.whatsapp_connections(org_id, user_id, created_at DESC);
