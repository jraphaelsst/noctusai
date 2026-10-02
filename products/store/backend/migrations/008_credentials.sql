-- Migration: credentials — org-scoped, Fernet-encrypted managed API keys
-- (owner directive 2026-10-02: keys live in the DB, not env). VERBATIM output of
-- noctusai_lib.security.api_keys.credentials_table_ddl("store"); backs the seed
-- api-keys router (asaas_api_key / asaas_webhook_token / asaas_environment).
-- Encrypted at rest with ENCRYPTION_KEY (Fernet). Writes + reads run through the
-- admin (service-role) client; `authenticated` may only SELECT its own org's rows
-- (ciphertext only). No anon grant. Forward-only. NOT applied by its author.

SET search_path = store, public;

CREATE TABLE store.credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,
    encrypted_tokens TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, provider)
);

ALTER TABLE store.credentials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "credentials_select_own_org" ON store.credentials FOR SELECT TO authenticated
  USING (org_id = current_org_id());

CREATE POLICY "service_role_bypass" ON store.credentials FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_store_credentials_org ON store.credentials(org_id);
CREATE INDEX idx_store_credentials_provider ON store.credentials(provider);
-- Ciphertext is still ciphertext, but a browser role has no business reading it:
-- the admin UI goes through the backend (masked hint only). Revoke the 001
-- default-privilege grants; keep service_role.
REVOKE ALL ON store.credentials FROM anon, authenticated;
GRANT ALL ON store.credentials TO service_role;
