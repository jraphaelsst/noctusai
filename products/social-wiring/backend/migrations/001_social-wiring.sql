-- ============================================================
-- Social Wiring — canonical single-file schema (001).
--
-- One 001 builds the FULL schema. Phases edit THIS file in-place;
-- live-DB additive patches go to 002+ in lock-step (per the
-- single-001-migration rule). The reference workspace's 001–008 are
-- folded here: 006 (product_code) + 008 (thumbnail_url) are columns on
-- upload_jobs; the status_pagina seed inserts are consolidated.
--
-- ┌─ MODULE TABLE LAYOUT (for W2.2 / W2.3) ────────────────────────────┐
-- │ W2.1 media_wiring  → status_pagina, invitations, credentials,      │
-- │                       upload_jobs, video_cache,                    │
-- │                       notification_recipients, notification_log,   │
-- │                       conversation_messages                        │
-- │ W2.2 email_marketing → ADD campaign/automation/segment/analytics   │
-- │                        tables under the "W2.2" marker below.       │
-- │ W2.3 scheduling      → ADD appointment/scheduling tables under the │
-- │                        "W2.3" marker below.                        │
-- │ Use schema `social_wiring`; mirror the RLS shape used here         │
-- │ (org-scoped SELECT TO authenticated + service_role write).         │
-- └────────────────────────────────────────────────────────────────────┘
-- ============================================================
SET search_path = social_wiring, public;

CREATE SCHEMA IF NOT EXISTS social_wiring;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA social_wiring TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA social_wiring TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA social_wiring TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA social_wiring GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA social_wiring GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- Page status (feature flags)
-- ============================================================================

CREATE TABLE social_wiring.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE social_wiring.status_pagina ENABLE ROW LEVEL SECURITY;

-- Anonymous-readable policy (anon role too) — intentionally NOT
-- rls_subquery_policy (which always emits TO authenticated).
CREATE POLICY "todos_veem_producao" ON social_wiring.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- Invitations  (002 accepted_* columns folded inline per single-001 rule)
-- ============================================================================

CREATE TABLE social_wiring.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    accepted_at TIMESTAMPTZ,
    accepted_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON social_wiring.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_social_wiring_invitations_org ON social_wiring.invitations(org_id);
CREATE INDEX idx_social_wiring_invitations_token ON social_wiring.invitations(token);


-- ============================================================================
-- Credentials — per-org OAuth tokens, refresh tokens Fernet-encrypted at rest.
-- Plaintext never lives in the DB; the encryption key lives in .env
-- (ENCRYPTION_KEY) so DB compromise alone cannot recover the refresh token.
-- ============================================================================

CREATE TABLE social_wiring.credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    provider TEXT NOT NULL,                    -- e.g. 'youtube', 'google_calendar', 'meta'
    encrypted_tokens TEXT NOT NULL,            -- Fernet-encrypted JSON
    channel_id TEXT,
    channel_title TEXT,
    scopes TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, provider)
);

ALTER TABLE social_wiring.credentials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "credentials_select_own_org" ON social_wiring.credentials
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "credentials_write_service_role" ON social_wiring.credentials
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_social_wiring_credentials_org ON social_wiring.credentials(org_id);
CREATE INDEX idx_social_wiring_credentials_provider ON social_wiring.credentials(provider);


-- ============================================================================
-- Upload jobs — lifecycle of a single video upload.
-- 006 (product_code) + 008 (thumbnail_url) columns folded inline.
-- Status: queued → downloading? → uploading → processing → published
--                                                  → notified ↘ failed
-- ============================================================================

CREATE TABLE social_wiring.upload_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    youtube_video_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    tags TEXT[],
    privacy_status TEXT NOT NULL DEFAULT 'private'
        CHECK (privacy_status IN ('public', 'unlisted', 'private')),
    category_id TEXT NOT NULL DEFAULT '22',
    source_type TEXT NOT NULL CHECK (source_type IN ('browser', 'gdrive')),
    source_url TEXT,
    file_name TEXT NOT NULL,
    file_size_bytes BIGINT,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'downloading', 'uploading', 'processing', 'published', 'notified', 'failed')),
    progress_percent INTEGER NOT NULL DEFAULT 0
        CHECK (progress_percent BETWEEN 0 AND 100),
    error_message TEXT,
    notify_recipients UUID[] NOT NULL DEFAULT '{}',
    product_code TEXT,                            -- folded from 006
    thumbnail_url TEXT,                           -- folded from 008
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.upload_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "upload_jobs_select_own_org" ON social_wiring.upload_jobs
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "upload_jobs_insert_own_org" ON social_wiring.upload_jobs
    FOR INSERT TO authenticated
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "upload_jobs_update_own_org" ON social_wiring.upload_jobs
    FOR UPDATE TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "upload_jobs_service_role" ON social_wiring.upload_jobs
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_sw_upload_jobs_org ON social_wiring.upload_jobs(org_id);
CREATE INDEX idx_sw_upload_jobs_status ON social_wiring.upload_jobs(org_id, status);
CREATE INDEX idx_sw_upload_jobs_created ON social_wiring.upload_jobs(org_id, created_at DESC);
CREATE INDEX idx_sw_upload_jobs_product_code ON social_wiring.upload_jobs(org_id, product_code);


-- ============================================================================
-- Video cache — local mirror of the connected channel's video catalog.
-- ============================================================================

CREATE TABLE social_wiring.video_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    youtube_video_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    thumbnail_url TEXT,
    published_at TIMESTAMPTZ,
    duration TEXT,
    privacy_status TEXT
        CHECK (privacy_status IS NULL OR privacy_status IN ('public', 'unlisted', 'private')),
    view_count BIGINT NOT NULL DEFAULT 0,
    like_count BIGINT NOT NULL DEFAULT 0,
    comment_count BIGINT NOT NULL DEFAULT 0,
    favorite_count BIGINT NOT NULL DEFAULT 0,
    tags TEXT[] NOT NULL DEFAULT '{}',
    category_id TEXT,
    uploaded_via_app BOOLEAN NOT NULL DEFAULT false,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, youtube_video_id)
);

ALTER TABLE social_wiring.video_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "video_cache_select_own_org" ON social_wiring.video_cache
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "video_cache_service_role" ON social_wiring.video_cache
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_sw_video_cache_org ON social_wiring.video_cache(org_id);
CREATE INDEX idx_sw_video_cache_published
    ON social_wiring.video_cache(org_id, published_at DESC);
CREATE INDEX idx_sw_video_cache_uploaded_via_app
    ON social_wiring.video_cache(org_id, uploaded_via_app)
    WHERE uploaded_via_app = true;
CREATE INDEX idx_sw_video_cache_synced
    ON social_wiring.video_cache(org_id, synced_at DESC);


-- ============================================================================
-- Notifications — recipient list (Settings CRUD) + per-dispatch delivery log.
-- ============================================================================

CREATE TABLE social_wiring.notification_recipients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    whatsapp_number TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT recipient_has_at_least_one_channel
        CHECK (email IS NOT NULL OR whatsapp_number IS NOT NULL)
);

ALTER TABLE social_wiring.notification_recipients ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notification_recipients_select_own_org"
    ON social_wiring.notification_recipients
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "notification_recipients_write_own_org"
    ON social_wiring.notification_recipients
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid)
    WITH CHECK (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_sw_notification_recipients_org
    ON social_wiring.notification_recipients(org_id);
CREATE INDEX idx_sw_notification_recipients_active
    ON social_wiring.notification_recipients(org_id, is_active)
    WHERE is_active = true;

CREATE TABLE social_wiring.notification_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    upload_job_id UUID REFERENCES social_wiring.upload_jobs(id) ON DELETE CASCADE,
    recipient_id UUID REFERENCES social_wiring.notification_recipients(id) ON DELETE SET NULL,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'whatsapp')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'failed')),
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.notification_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notification_log_select_own_org"
    ON social_wiring.notification_log
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "notification_log_write_service_role"
    ON social_wiring.notification_log
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_sw_notification_log_org
    ON social_wiring.notification_log(org_id);
CREATE INDEX idx_sw_notification_log_job
    ON social_wiring.notification_log(upload_job_id);
CREATE INDEX idx_sw_notification_log_recipient
    ON social_wiring.notification_log(recipient_id);


-- ============================================================================
-- Conversation messages — one row per WhatsApp / platform-chat message.
-- UNIQUE(provider_message_id) drives WAHA idempotency (WAHA sends
-- `message` + `message.any` for the same inbound; the duplicate INSERT
-- trips the constraint and the handler drops the second event).
-- ============================================================================

CREATE TABLE social_wiring.conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    session_id TEXT NOT NULL,
    raw_sender TEXT,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    provider_message_id TEXT,
    body TEXT NOT NULL,
    authorized BOOLEAN NOT NULL DEFAULT false,
    structured_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_conversation_messages_provider_message_id
        UNIQUE (provider_message_id)
);

ALTER TABLE social_wiring.conversation_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "conversation_messages_select_own_org"
    ON social_wiring.conversation_messages
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE POLICY "conversation_messages_write_service_role"
    ON social_wiring.conversation_messages
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE INDEX idx_sw_conversation_messages_session
    ON social_wiring.conversation_messages(session_id, created_at DESC);
CREATE INDEX idx_sw_conversation_messages_org_session
    ON social_wiring.conversation_messages(org_id, session_id, created_at DESC);
CREATE INDEX idx_sw_conversation_messages_direction
    ON social_wiring.conversation_messages(direction);


-- ─── W2.2 email_marketing tables — ADD BELOW (do not edit above) ─────────────
-- (campaigns / automations / segments / analytics — from `mailing`)


-- ─── W2.3 scheduling tables — ADD BELOW (do not edit above) ──────────────────
-- (appointments / scheduling-lifecycle — from `imobi-scheduling`)


-- ============================================================================
-- Seed pages (status_pagina) — consolidated from reference 001–004
-- ============================================================================

INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('equipe', 'producao'),
    ('configuracoes', 'producao'),
    ('upload', 'producao'),
    ('videos', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
