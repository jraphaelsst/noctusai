-- ============================================================================
-- Migration 319 -- social_wiring.credentials: the browser can never read encrypted_tokens (Julia-line S8)
-- ============================================================================
-- WHY: the agents channel token is delivered by the platform and stored Fernet-encrypted as `api_key:agents`
-- (plus every other integration secret in this table). The 001 policy `credentials_select_own_org` lets any
-- AUTHENTICATED org member SELECT whole rows, ciphertext included. The ciphertext is useless without ENCRYPTION_KEY,
-- but a secret must not be reachable from the browser at all (owner 2026-11-04: "hidden from back doors as well").
--
-- WHAT: authenticated / anon keep no table-wide SELECT; authenticated gets a column-level SELECT on the non-secret
-- columns only (the RLS own-org policy still scopes the rows). `encrypted_tokens` is readable by service_role only,
-- i.e. the backend process that decrypts it. Idempotent (REVOKE / GRANT repeat safely).
REVOKE ALL ON TABLE social_wiring.credentials FROM PUBLIC, anon;
REVOKE ALL ON TABLE social_wiring.credentials FROM authenticated;
GRANT SELECT (id, org_id, provider, channel_id, channel_title, scopes, created_at, updated_at)
  ON social_wiring.credentials TO authenticated;
