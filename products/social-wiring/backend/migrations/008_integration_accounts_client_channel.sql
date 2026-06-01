-- 008_integration_accounts_client_channel.sql — per-account channel object.
--
-- Project: social-wiring-multi-account-clients (2026-06-01). Extends
-- integration_accounts with:
--   • client_id FK → social_wiring.clients
--   • status (lifecycle: wiring → validating → validated | error | disconnected)
--   • channel_info JSONB (provider-specific channel metadata)
--   • last_synced_at TIMESTAMPTZ
--
-- Existing rows default to status='validated' and channel_info='{}'.
-- Existing UNIQUE(org_id, provider, account_label) and the is_default
-- partial-unique index are preserved unchanged.
--
-- Forward-only + idempotent. Apply to the noctusai Supabase
-- (social_wiring schema) at deploy.

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.integration_accounts
    ADD COLUMN IF NOT EXISTS client_id UUID
        REFERENCES social_wiring.clients(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'validated'
        CHECK (status IN ('wiring', 'validating', 'validated', 'error', 'disconnected')),
    ADD COLUMN IF NOT EXISTS channel_info JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;

-- Composite index supporting the common query pattern:
-- org + provider (existing) extended with client_id for per-client filtering.
CREATE INDEX IF NOT EXISTS idx_sw_integration_accounts_org_provider_client
    ON social_wiring.integration_accounts (org_id, provider, client_id);

-- Backfill channel_info for existing YouTube rows that already have
-- channel_id / channel_title in metadata.
UPDATE social_wiring.integration_accounts
    SET channel_info = jsonb_build_object(
        'channel_id',    metadata ->> 'channel_id',
        'title',         metadata ->> 'channel_title'
    )
    WHERE provider = 'youtube'
      AND channel_info = '{}'::jsonb
      AND metadata ? 'channel_id';
