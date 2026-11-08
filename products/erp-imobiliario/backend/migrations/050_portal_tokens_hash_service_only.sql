-- 050_portal_tokens_hash_service_only.sql
-- Owner decision 2026-11-08 (AT-34022b67, NOC-REMEDIATE[access-tier] catalog:179):
-- erp.portal_tokens must not store the client-portal bearer token in plaintext, and
-- must not be reachable from a browser role. The raw token is shown once at issue
-- (POST /api/portal/gerar-link) and only its SHA-256 hex (noctusai_lib hash_token)
-- is persisted; validation hashes the presented token and looks it up server-side.
--
-- Forward-safe vs N-1: the table has 0 rows in prod (verified 2026-11-08) and no
-- browser grants (049). The previous image's issue/validate paths read/write the
-- dropped `token` column, but portal links are not in use (0 rows); the new image
-- ships in the same deploy.
-- Idempotent. Runner lock_timeout default (5s) applies; tiny table.

SET search_path = erp, public;

ALTER TABLE erp.portal_tokens ADD COLUMN IF NOT EXISTS token_hash text;

-- Carry any pre-existing row over by hashing its plaintext (prod has 0 rows).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = 'erp' AND table_name = 'portal_tokens' AND column_name = 'token') THEN
    UPDATE erp.portal_tokens
       SET token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex')
     WHERE token_hash IS NULL;
  END IF;
END $$;

ALTER TABLE erp.portal_tokens DROP COLUMN IF EXISTS token;
ALTER TABLE erp.portal_tokens ALTER COLUMN token_hash SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_portal_tokens_token_hash ON erp.portal_tokens (token_hash);

-- Service-only: the backend uses the service role (RLS bypass) scoped by org_id.
DROP POLICY IF EXISTS "portal_tokens_delete_policy" ON erp.portal_tokens;
DROP POLICY IF EXISTS "portal_tokens_insert_policy" ON erp.portal_tokens;
DROP POLICY IF EXISTS "portal_tokens_select_policy" ON erp.portal_tokens;
DROP POLICY IF EXISTS "portal_tokens_update_policy" ON erp.portal_tokens;
REVOKE ALL ON erp.portal_tokens FROM anon, authenticated;

COMMENT ON TABLE erp.portal_tokens IS 'tier:service';
