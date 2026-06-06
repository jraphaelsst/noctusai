-- 005_whatsapp_connection_webhook_token.sql — per-connection opaque webhook token
--
-- Adds a unique, server-generated ``webhook_token`` column to
-- ``social_wiring.whatsapp_connections``. This token is the stable, opaque
-- routing key for the per-connection webhook URL:
--
--   POST /api/whatsapp/webhook/{token}
--
-- WAHA is pointed at a URL built around this token on create so every
-- connection has its own isolated inbound path. Deriving the URL from
-- ``resolve_product_url('social-wiring') + /api/whatsapp/webhook/{token}``
-- means the URL survives a domain change (the token is persisted; the URL
-- is re-derived on each read). The column is NOT NULL after backfill.
--
-- Forward-only + idempotent within the apply window. Apply to the
-- noctusai Supabase (social_wiring schema) AFTER 004 is applied.

-- `extensions` is on the search_path because pgcrypto's gen_random_bytes lives
-- in the `extensions` schema on Supabase (NOT public) — without it the backfill
-- errors 42883 "function gen_random_bytes(integer) does not exist".
SET search_path = social_wiring, public, extensions;

-- Step 1: add column nullable first (required before backfill).
ALTER TABLE social_wiring.whatsapp_connections
    ADD COLUMN IF NOT EXISTS webhook_token TEXT;

-- Step 2: backfill existing rows with a fresh random hex token
--   encode(gen_random_bytes(18), 'hex') produces 36 hex chars — same entropy
--   as secrets.token_hex(18) on the Python side, URL-safe, WAHA-safe.
--   Schema-qualified so it resolves regardless of search_path quirks.
UPDATE social_wiring.whatsapp_connections
    SET webhook_token = encode(extensions.gen_random_bytes(18), 'hex')
    WHERE webhook_token IS NULL;

-- Step 3: enforce NOT NULL.
ALTER TABLE social_wiring.whatsapp_connections
    ALTER COLUMN webhook_token SET NOT NULL;

-- Step 4: unique index — token lookup (get_by_webhook_token) + uniqueness guarantee.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_whatsapp_connections_webhook_token
    ON social_wiring.whatsapp_connections (webhook_token);
