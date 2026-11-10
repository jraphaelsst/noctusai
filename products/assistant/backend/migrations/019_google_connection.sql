-- ============================================================================
-- Migration 019 -- Assistant: the Google connection (D50) -- per-org OAuth grant + the single-use consent state
--
-- * `oauth_credentials` -- the seed `SupabaseCredentialStore` shape verbatim: one row per (org_id, provider), the token
--   bundle Fernet-encrypted into `encrypted_tokens` (ENCRYPTION_KEY), `metadata` = non-secret facts only (granted
--   scopes, connected account email, who connected, needs_reconnection). Integration keys live HERE per org, never .env.
-- * `oauth_states` -- the seed `SupabaseOAuthStateStore` shape: the consent `state` is stored as its SHA-256 only, the
--   PKCE verifier Fernet-encrypted, 10 minute expiry, consumed by a single DELETE ... RETURNING (single-use).
--
-- Access: service role only (no browser grant, no browser policy); every route is admin-gated or state-gated in the
-- backend. Forward-only + idempotent (re-apply safe). NOT applied by the slice that authored it -- the tech-lead applies it.
-- ============================================================================

SET search_path = assistant, public;

CREATE TABLE IF NOT EXISTS assistant.oauth_credentials (
    org_id           text NOT NULL,
    provider         text NOT NULL,
    encrypted_tokens text NOT NULL,                       -- Fernet(JSON(bundle)); never plaintext
    metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- non-secret: scopes, account_email, connected_by, needs_reconnection
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, provider)
);

ALTER TABLE assistant.oauth_credentials ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.oauth_credentials;
CREATE POLICY "service_role_bypass" ON assistant.oauth_credentials FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.oauth_credentials IS 'tier:org';
REVOKE ALL ON assistant.oauth_credentials FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.oauth_credentials TO service_role;

CREATE TABLE IF NOT EXISTS assistant.oauth_states (
    state_hash              text PRIMARY KEY,              -- sha256(state), hex: the raw state is never stored
    provider                text NOT NULL,
    org_id                  text NOT NULL,
    user_id                 text NOT NULL,
    redirect_uri            text NOT NULL,
    encrypted_code_verifier text NOT NULL,                 -- Fernet(PKCE code_verifier)
    expires_at              timestamptz NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assistant_oauth_states_expires ON assistant.oauth_states (expires_at);

ALTER TABLE assistant.oauth_states ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON assistant.oauth_states;
CREATE POLICY "service_role_bypass" ON assistant.oauth_states FOR ALL TO service_role USING (true) WITH CHECK (true);
COMMENT ON TABLE assistant.oauth_states IS 'tier:org';
REVOKE ALL ON assistant.oauth_states FROM PUBLIC, anon, authenticated;
GRANT ALL ON assistant.oauth_states TO service_role;
