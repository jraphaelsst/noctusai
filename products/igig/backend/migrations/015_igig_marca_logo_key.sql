-- ============================================================================
-- 015_igig_marca_logo_key.sql — store the logo's STORAGE KEY, not a signed URL
--
-- THE BUG. `marca_router.enviar_logo` persisted the result of
-- `storage.signed_url(...)` into `marca.logo_url`. That helper defaults to
-- `expires_in_seconds=3600`, so the column held a credential with a one-hour
-- TTL being used as if it were a durable address: every brand logo rendered
-- for an hour and then 404'd forever. Confirmed in production 2026-09-01 —
-- a logo uploaded 90 minutes earlier came back with `naturalWidth: 0`.
--
-- It was latent until now only because the upload endpoint had no consumer;
-- the moment a logo could actually be uploaded from the UI, the expiry became
-- user-visible. A complete lower stack is not a shipped feature.
--
-- THE FIX. Keep the immutable key here and mint a fresh signed URL on every
-- READ. This is the pattern the same product already uses for pauta peças
-- (`peca.storage_key`) — the correct shape existed two files away.
--
-- `logo_url` is KEPT (not dropped): it still carries the freshly-signed URL on
-- responses, so no consumer changes, and dropping a column that a running
-- prod image still selects would be a breaking deploy ordering problem.
--
-- BACKFILL. A Supabase signed URL is
-- `…/storage/v1/object/sign/<bucket>/<key>?token=…`, so the key is recoverable
-- from the existing (now-expired) value. Recovering it means the brand that
-- already has a logo starts working again on deploy rather than needing a
-- re-upload — the data was never lost, only the address expired.
-- ============================================================================
SET search_path = igig, public;

ALTER TABLE igig.marca ADD COLUMN IF NOT EXISTS logo_key TEXT;

COMMENT ON COLUMN igig.marca.logo_key IS
    'Immutable storage key for the logo. The signed URL is minted per-response '
    'and must NEVER be persisted — it expires (default 1h).';

-- Recover the key from any already-stored signed URL: everything between
-- `/object/sign/<bucket>/` and the query string.
UPDATE igig.marca
   SET logo_key = substring(logo_url from '/object/sign/[^/]+/([^?]+)')
 WHERE logo_key IS NULL
   AND logo_url IS NOT NULL
   AND logo_url LIKE '%/object/sign/%';
