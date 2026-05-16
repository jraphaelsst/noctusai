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

-- ─── W2.2 email_marketing tables (absorbed from the retired `mailing` product) ───
-- Splice verbatim under the `-- ─── W2.2 email_marketing tables — ADD BELOW` marker
-- in products/social-wiring/backend/migrations/001_social-wiring.sql.
-- Schema social_wiring; org-scoped-SELECT + service_role-write RLS.

CREATE TABLE social_wiring.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    nome TEXT, telefone TEXT, empresa TEXT,
    tags TEXT[] DEFAULT '{}',
    custom_fields JSONB DEFAULT '{}',
    source TEXT DEFAULT 'manual' CHECK (source IN ('manual','import','sync:erp','form','api')),
    source_ref TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','unsubscribed','bounced','complained')),
    unsubscribed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, email)
);
ALTER TABLE social_wiring.contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_contacts_select_own_org" ON social_wiring.contacts
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_contacts_write_service_role" ON social_wiring.contacts
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_contacts_org_email ON social_wiring.contacts(org_id, email);
CREATE INDEX idx_sw_contacts_org_status ON social_wiring.contacts(org_id, status);
CREATE INDEX idx_sw_contacts_tags ON social_wiring.contacts USING GIN(tags);

CREATE TABLE social_wiring.contact_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL, descricao TEXT,
    tipo TEXT NOT NULL DEFAULT 'static' CHECK (tipo IN ('static','dynamic')),
    filtros JSONB DEFAULT '{}',
    contact_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.contact_lists ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_lists_select_own_org" ON social_wiring.contact_lists
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_lists_write_service_role" ON social_wiring.contact_lists
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.contact_list_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id UUID NOT NULL REFERENCES social_wiring.contact_lists(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES social_wiring.contacts(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(list_id, contact_id)
);
ALTER TABLE social_wiring.contact_list_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_list_members_select_via_list" ON social_wiring.contact_list_members
    FOR SELECT TO authenticated USING (list_id IN (
        SELECT id FROM social_wiring.contact_lists
        WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid));
CREATE POLICY "em_list_members_write_service_role" ON social_wiring.contact_list_members
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL, assunto TEXT NOT NULL,
    corpo_html TEXT NOT NULL, corpo_text TEXT,
    variaveis TEXT[] DEFAULT '{}',
    categoria TEXT DEFAULT 'marketing' CHECK (categoria IN ('marketing','transactional','follow_up','newsletter')),
    ativo BOOLEAN DEFAULT true, thumbnail_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_templates_select_own_org" ON social_wiring.templates
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_templates_write_service_role" ON social_wiring.templates
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    template_id UUID REFERENCES social_wiring.templates(id),
    list_id UUID REFERENCES social_wiring.contact_lists(id),
    assunto_override TEXT, remetente_nome TEXT, remetente_email TEXT,
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho','agendada','enviando','enviada','pausada','cancelada')),
    scheduled_at TIMESTAMPTZ, started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
    total_recipients INT DEFAULT 0, total_sent INT DEFAULT 0, total_failed INT DEFAULT 0,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.campaigns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_campaigns_select_own_org" ON social_wiring.campaigns
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_campaigns_write_service_role" ON social_wiring.campaigns
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.automations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL, descricao TEXT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('contact_added','tag_added','list_joined','form_submitted','manual','webhook')),
    trigger_config JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho','ativa','pausada')),
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.automations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_automations_select_own_org" ON social_wiring.automations
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_automations_write_service_role" ON social_wiring.automations
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.automation_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    automation_id UUID NOT NULL REFERENCES social_wiring.automations(id) ON DELETE CASCADE,
    posicao INT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('send_email','wait','condition','add_tag','remove_tag','move_to_list','webhook')),
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.automation_steps ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_steps_select_via_automation" ON social_wiring.automation_steps
    FOR SELECT TO authenticated USING (automation_id IN (
        SELECT id FROM social_wiring.automations
        WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid));
CREATE POLICY "em_steps_write_service_role" ON social_wiring.automation_steps
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.automation_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    automation_id UUID NOT NULL REFERENCES social_wiring.automations(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES social_wiring.contacts(id) ON DELETE CASCADE,
    current_step_id UUID REFERENCES social_wiring.automation_steps(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','paused','exited')),
    next_action_at TIMESTAMPTZ,
    enrolled_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE(automation_id, contact_id)
);
ALTER TABLE social_wiring.automation_enrollments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_enrollments_select_via_automation" ON social_wiring.automation_enrollments
    FOR SELECT TO authenticated USING (automation_id IN (
        SELECT id FROM social_wiring.automations
        WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid));
CREATE POLICY "em_enrollments_write_service_role" ON social_wiring.automation_enrollments
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_enrollments_next ON social_wiring.automation_enrollments(next_action_at) WHERE status = 'active';

CREATE TABLE social_wiring.send_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    contact_id UUID NOT NULL REFERENCES social_wiring.contacts(id),
    email TEXT NOT NULL,
    campaign_id UUID REFERENCES social_wiring.campaigns(id),
    automation_id UUID REFERENCES social_wiring.automations(id),
    automation_step_id UUID REFERENCES social_wiring.automation_steps(id),
    resend_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','delivered','opened','clicked','bounced','complained','failed')),
    sent_at TIMESTAMPTZ, delivered_at TIMESTAMPTZ, opened_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ, bounced_at TIMESTAMPTZ, error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.send_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_send_logs_select_own_org" ON social_wiring.send_logs
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_send_logs_write_service_role" ON social_wiring.send_logs
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_send_logs_campaign ON social_wiring.send_logs(campaign_id);
CREATE INDEX idx_sw_send_logs_resend_id ON social_wiring.send_logs(resend_message_id);
CREATE INDEX idx_sw_send_logs_status ON social_wiring.send_logs(status) WHERE status = 'queued';

CREATE TABLE social_wiring.link_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    send_log_id UUID NOT NULL REFERENCES social_wiring.send_logs(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    clicked_at TIMESTAMPTZ DEFAULT now(),
    user_agent TEXT, ip_address INET
);
ALTER TABLE social_wiring.link_clicks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_clicks_select_via_send_log" ON social_wiring.link_clicks
    FOR SELECT TO authenticated USING (send_log_id IN (
        SELECT id FROM social_wiring.send_logs
        WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid));
CREATE POLICY "em_clicks_write_service_role" ON social_wiring.link_clicks
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.unsubscribes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    contact_id UUID NOT NULL REFERENCES social_wiring.contacts(id),
    email TEXT NOT NULL,
    reason TEXT DEFAULT 'link_click' CHECK (reason IN ('manual','link_click','complaint','admin')),
    campaign_id UUID REFERENCES social_wiring.campaigns(id),
    unsubscribed_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.unsubscribes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_unsubscribes_select_own_org" ON social_wiring.unsubscribes
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_unsubscribes_write_service_role" ON social_wiring.unsubscribes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE social_wiring.sender_domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    domain TEXT NOT NULL,
    resend_domain_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','verified','failed')),
    dns_records JSONB, verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE social_wiring.sender_domains ENABLE ROW LEVEL SECURITY;
CREATE POLICY "em_domains_select_own_org" ON social_wiring.sender_domains
    FOR SELECT TO authenticated USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "em_domains_write_service_role" ON social_wiring.sender_domains
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS social_wiring.tool_call_audits (
    id BIGSERIAL PRIMARY KEY,
    correlation_id VARCHAR(64), gpt_call_id VARCHAR(64), tool_call_id VARCHAR(64),
    conversation_id VARCHAR(64), user_id BIGINT,
    tool_name VARCHAR(80) NOT NULL, status VARCHAR(16) NOT NULL,
    arguments JSONB, result JSONB, error TEXT, duration_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sw_tca_correlation_id ON social_wiring.tool_call_audits (correlation_id);
CREATE INDEX IF NOT EXISTS ix_sw_tca_user_started ON social_wiring.tool_call_audits (user_id, started_at);
CREATE INDEX IF NOT EXISTS ix_sw_tca_tool_name ON social_wiring.tool_call_audits (tool_name);
CREATE INDEX IF NOT EXISTS ix_sw_tca_status ON social_wiring.tool_call_audits (status);
CREATE INDEX IF NOT EXISTS ix_sw_tca_conversation ON social_wiring.tool_call_audits (conversation_id, started_at);
-- ─── end W2.2 ───

-- ─── W2.3 scheduling tables — ADD BELOW (do not edit above) ──────────────────
-- (appointments / scheduling-lifecycle — from `imobi-scheduling`)

-- ─── W2.3 scheduling tables (absorbed from imobi-scheduling) ─────────────────
-- Splice verbatim under the `-- ─── W2.3 scheduling tables — ADD BELOW` marker
-- in products/social-wiring/backend/migrations/001_social-wiring.sql.
-- Schema social_wiring; sched_-prefixed; org-scoped-SELECT + service_role-write RLS.

CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_scheduling()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = social_wiring, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE TABLE social_wiring.sched_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('real_estate_agent','media_crew','admin')),
    phone_number TEXT NOT NULL,
    email TEXT,
    linked_identity TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, phone_number)
);
ALTER TABLE social_wiring.sched_users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_users_select_own_org" ON social_wiring.sched_users
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_users_write_service_role" ON social_wiring.sched_users
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_users_org ON social_wiring.sched_users(org_id);
CREATE INDEX idx_sw_sched_users_phone ON social_wiring.sched_users(phone_number);
CREATE INDEX idx_sw_sched_users_lid ON social_wiring.sched_users(linked_identity);
CREATE OR REPLACE TRIGGER set_updated_at_sched_users
    BEFORE UPDATE ON social_wiring.sched_users
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_condominiums (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, name)
);
ALTER TABLE social_wiring.sched_condominiums ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_condominiums_select_own_org" ON social_wiring.sched_condominiums
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_condominiums_write_service_role" ON social_wiring.sched_condominiums
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_condominiums_org ON social_wiring.sched_condominiums(org_id);
CREATE OR REPLACE TRIGGER set_updated_at_sched_condominiums
    BEFORE UPDATE ON social_wiring.sched_condominiums
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_properties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    condominium_id UUID NOT NULL REFERENCES social_wiring.sched_condominiums(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    unit TEXT,
    address_notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, code)
);
ALTER TABLE social_wiring.sched_properties ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_properties_select_own_org" ON social_wiring.sched_properties
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_properties_write_service_role" ON social_wiring.sched_properties
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_properties_org ON social_wiring.sched_properties(org_id);
CREATE INDEX idx_sw_sched_properties_condo ON social_wiring.sched_properties(condominium_id);
CREATE INDEX idx_sw_sched_properties_code ON social_wiring.sched_properties(code);
CREATE OR REPLACE TRIGGER set_updated_at_sched_properties
    BEFORE UPDATE ON social_wiring.sched_properties
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    default_duration_minutes INTEGER NOT NULL DEFAULT 30 CHECK (default_duration_minutes > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, name)
);
ALTER TABLE social_wiring.sched_services ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_services_select_own_org" ON social_wiring.sched_services
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_services_write_service_role" ON social_wiring.sched_services
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_services_org ON social_wiring.sched_services(org_id);
CREATE OR REPLACE TRIGGER set_updated_at_sched_services
    BEFORE UPDATE ON social_wiring.sched_services
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_crew_skills (
    user_id UUID NOT NULL REFERENCES social_wiring.sched_users(id) ON DELETE CASCADE,
    service_id UUID NOT NULL REFERENCES social_wiring.sched_services(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, service_id)
);
ALTER TABLE social_wiring.sched_crew_skills ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_crew_skills_select_own_org" ON social_wiring.sched_crew_skills
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_crew_skills_write_service_role" ON social_wiring.sched_crew_skills
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_crew_skills_user ON social_wiring.sched_crew_skills(user_id);
CREATE INDEX idx_sw_sched_crew_skills_service ON social_wiring.sched_crew_skills(service_id);
CREATE INDEX idx_sw_sched_crew_skills_org ON social_wiring.sched_crew_skills(org_id);

CREATE TABLE social_wiring.sched_appointment_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    requester_user_id UUID NOT NULL REFERENCES social_wiring.sched_users(id) ON DELETE RESTRICT,
    property_id UUID REFERENCES social_wiring.sched_properties(id) ON DELETE SET NULL,
    condominium_id UUID REFERENCES social_wiring.sched_condominiums(id) ON DELETE SET NULL,
    requested_date DATE,
    requested_time_window TEXT,
    status TEXT NOT NULL DEFAULT 'collecting_details' CHECK (status IN (
        'collecting_details','pending_confirmation','confirmed','cancelled','expired')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE social_wiring.sched_appointment_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_appt_requests_select_own_org" ON social_wiring.sched_appointment_requests
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_appt_requests_write_service_role" ON social_wiring.sched_appointment_requests
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_appt_req_org ON social_wiring.sched_appointment_requests(org_id);
CREATE INDEX idx_sw_sched_appt_req_status ON social_wiring.sched_appointment_requests(status);
CREATE OR REPLACE TRIGGER set_updated_at_sched_appt_requests
    BEFORE UPDATE ON social_wiring.sched_appointment_requests
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_appointment_request_services (
    appointment_request_id UUID NOT NULL
        REFERENCES social_wiring.sched_appointment_requests(id) ON DELETE CASCADE,
    service_id UUID NOT NULL REFERENCES social_wiring.sched_services(id) ON DELETE RESTRICT,
    org_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (appointment_request_id, service_id)
);
ALTER TABLE social_wiring.sched_appointment_request_services ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_appt_req_svc_select_own_org" ON social_wiring.sched_appointment_request_services
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_appt_req_svc_write_service_role" ON social_wiring.sched_appointment_request_services
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_appt_req_svc_req
    ON social_wiring.sched_appointment_request_services(appointment_request_id);

CREATE TABLE social_wiring.sched_route_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    date DATE NOT NULL,
    media_crew_user_id UUID REFERENCES social_wiring.sched_users(id) ON DELETE SET NULL,
    office_start_location TEXT,
    office_end_location TEXT,
    optimization_status TEXT NOT NULL DEFAULT 'not_started' CHECK (optimization_status IN (
        'not_started','pending','optimized','failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, date, media_crew_user_id)
);
ALTER TABLE social_wiring.sched_route_groups ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_route_groups_select_own_org" ON social_wiring.sched_route_groups
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_route_groups_write_service_role" ON social_wiring.sched_route_groups
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_route_groups_org ON social_wiring.sched_route_groups(org_id);
CREATE OR REPLACE TRIGGER set_updated_at_sched_route_groups
    BEFORE UPDATE ON social_wiring.sched_route_groups
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    appointment_request_id UUID
        REFERENCES social_wiring.sched_appointment_requests(id) ON DELETE SET NULL,
    google_calendar_event_id TEXT,
    property_id UUID NOT NULL REFERENCES social_wiring.sched_properties(id) ON DELETE RESTRICT,
    condominium_id UUID NOT NULL REFERENCES social_wiring.sched_condominiums(id) ON DELETE RESTRICT,
    media_crew_user_id UUID REFERENCES social_wiring.sched_users(id) ON DELETE SET NULL,
    route_group_id UUID REFERENCES social_wiring.sched_route_groups(id) ON DELETE SET NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN (
        'scheduled','completed','cancelled','no_show','rescheduled')),
    cancellation_reason TEXT,
    cancelled_at TIMESTAMPTZ,
    cancelled_by UUID REFERENCES social_wiring.sched_users(id) ON DELETE SET NULL,
    rescheduled_at TIMESTAMPTZ,
    rescheduled_by UUID REFERENCES social_wiring.sched_users(id) ON DELETE SET NULL,
    previous_start_at TIMESTAMPTZ,
    previous_end_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_at > start_at)
);
ALTER TABLE social_wiring.sched_appointments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_appointments_select_own_org" ON social_wiring.sched_appointments
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_appointments_write_service_role" ON social_wiring.sched_appointments
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_appointments_org ON social_wiring.sched_appointments(org_id);
CREATE INDEX idx_sw_sched_appointments_start ON social_wiring.sched_appointments(start_at);
CREATE INDEX idx_sw_sched_appointments_status ON social_wiring.sched_appointments(status);
CREATE INDEX idx_sw_sched_appointments_condo ON social_wiring.sched_appointments(condominium_id);
CREATE OR REPLACE TRIGGER set_updated_at_sched_appointments
    BEFORE UPDATE ON social_wiring.sched_appointments
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_pending_chat_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    chat_id TEXT NOT NULL,
    push_name TEXT,
    phone_hint TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','resolved','rejected')),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_to_user_id UUID REFERENCES social_wiring.sched_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, chat_id)
);
ALTER TABLE social_wiring.sched_pending_chat_identities ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_pending_chat_select_own_org" ON social_wiring.sched_pending_chat_identities
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_pending_chat_write_service_role" ON social_wiring.sched_pending_chat_identities
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX idx_sw_sched_pending_chat_org ON social_wiring.sched_pending_chat_identities(org_id);
CREATE INDEX idx_sw_sched_pending_chat_status ON social_wiring.sched_pending_chat_identities(status);
CREATE OR REPLACE TRIGGER set_updated_at_sched_pending_chat
    BEFORE UPDATE ON social_wiring.sched_pending_chat_identities
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_scheduling();

CREATE TABLE social_wiring.sched_tool_call_audits (
    id BIGSERIAL PRIMARY KEY,
    org_id UUID NOT NULL,
    correlation_id VARCHAR(64),
    gpt_call_id VARCHAR(64),
    tool_call_id VARCHAR(64),
    conversation_id VARCHAR(64),
    user_id UUID REFERENCES social_wiring.sched_users(id) ON DELETE SET NULL,
    tool_name VARCHAR(80) NOT NULL,
    status VARCHAR(16) NOT NULL,
    arguments JSONB,
    result JSONB,
    error TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE social_wiring.sched_tool_call_audits ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sched_tool_call_audits_select_own_org" ON social_wiring.sched_tool_call_audits
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);
CREATE POLICY "sched_tool_call_audits_write_service_role" ON social_wiring.sched_tool_call_audits
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE INDEX ix_sw_sched_tca_org ON social_wiring.sched_tool_call_audits(org_id);
CREATE INDEX ix_sw_sched_tca_tool ON social_wiring.sched_tool_call_audits(tool_name);
CREATE INDEX ix_sw_sched_tca_conv ON social_wiring.sched_tool_call_audits(conversation_id, started_at);
-- ─── end W2.3 ───


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
