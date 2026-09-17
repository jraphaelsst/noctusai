-- ============================================================
-- Schema lock — pin name resolution to community, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = community, public;

-- ============================================================================
-- Migration 011 — org-scoped managed API keys + WhatsApp (WAHA) connections
--
-- User decision 2026-09-17 ("community uses social-wiring's mechanisms"):
-- community consumes the SAME generic mechanisms social-wiring's Slice A
-- extracted to the seed (Slice C, this migration) —
-- `noctusai_lib.security.api_keys.credentials_table_ddl` +
-- `noctusai_lib.integrations.whatsapp.connection_store.
-- whatsapp_connections_table_ddl`. Both DDL blocks below are the VERBATIM
-- output of those helpers for schema="community" (authoring-time helper —
-- not a live-apply tool; copied here so this migration is the single
-- source of truth, same as every other product's migrations).
--
-- `credentials` backs `noctusai_seed.api_keys_router` — Configurações →
-- Chaves de API (`app/routers/api_keys_router.py`): stripe_secret_key /
-- stripe_webhook_secret / asaas_api_key / asaas_webhook_token /
-- turnstile_secret_key. Encrypted at rest with `ENCRYPTION_KEY`
-- (Fernet) — see `noctusai_lib.security.api_keys.require_fernet`.
--
-- `whatsapp_connections` backs `noctusai_seed.whatsapp_connections_router`
-- — Conexões WhatsApp (`app/routers/whatsapp_connections_router.py`).
-- WhatsApp is NOT paired in this slice (see
-- `NOC-REMEDIATE[community-waha-pairing]` at the router's mount site) —
-- the table + router ship so the mechanism is real, not a stub, per the
-- user's explicit instruction.
--
-- Assumes `public.current_org_id()` already exists on this Supabase
-- project (migration 004 codified it for this schema's own RLS policies).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- credentials — org-scoped, Fernet-encrypted managed API keys
-- ----------------------------------------------------------------------------

CREATE TABLE community.credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,
    encrypted_tokens TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, provider)
);

ALTER TABLE community.credentials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "credentials_select_own_org" ON community.credentials FOR SELECT TO authenticated
  USING (org_id = current_org_id());

CREATE POLICY "credentials_service_role_bypass" ON community.credentials FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_community_credentials_org ON community.credentials(org_id);
CREATE INDEX idx_community_credentials_provider ON community.credentials(provider);

-- ----------------------------------------------------------------------------
-- whatsapp_connections — org-scoped, multi-session WAHA connection lines
-- ----------------------------------------------------------------------------

CREATE TABLE community.whatsapp_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    user_id UUID NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT NOT NULL,
    session_name TEXT NOT NULL DEFAULT 'default',
    encrypted_api_key TEXT NOT NULL,
    webhook_url TEXT,
    webhook_token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, label)
);

ALTER TABLE community.whatsapp_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "whatsapp_connections_select_own_org" ON community.whatsapp_connections FOR SELECT TO authenticated
  USING (org_id = current_org_id());

CREATE POLICY "whatsapp_connections_service_role_bypass" ON community.whatsapp_connections FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX idx_community_whatsapp_connections_org ON community.whatsapp_connections(org_id, created_at DESC);
CREATE UNIQUE INDEX idx_community_whatsapp_connections_webhook_token ON community.whatsapp_connections(webhook_token);

-- No GRANT to anon on either table — both are authenticated + service_role
-- only, matching every other community table's convention (migration 007
-- dropped the anon write policies migration 006 had shipped).
