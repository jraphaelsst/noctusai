-- ============================================================================
-- Mailing Product schema
-- Schema: mailing
-- Description: Email Marketing & Automation platform — contacts, campaigns,
--              automations, templates, send tracking, analytics.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mailing;

-- Grant usage to authenticated users (required for PostgREST)
GRANT USAGE ON SCHEMA mailing TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA mailing TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA mailing TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA mailing GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA mailing GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;


-- ============================================================================
-- 1. Page status (feature flags) — standard platform table
-- ============================================================================

CREATE TABLE mailing.status_pagina (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_pagina TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'producao' CHECK (status IN ('producao', 'desenvolvimento', 'desativado')),
    descricao TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.status_pagina ENABLE ROW LEVEL SECURITY;

CREATE POLICY "todos_veem_producao" ON mailing.status_pagina
    FOR SELECT USING (status = 'producao');


-- ============================================================================
-- 2. Invitations — standard platform table
-- ============================================================================

CREATE TABLE mailing.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    invited_by UUID NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE mailing.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "invitations_select_own_org" ON mailing.invitations
    FOR SELECT TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_mailing_invitations_org ON mailing.invitations(org_id);
CREATE INDEX idx_mailing_invitations_token ON mailing.invitations(token);


-- ============================================================================
-- 3. Contacts — email recipients managed by the org
-- ============================================================================

CREATE TABLE mailing.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    email TEXT NOT NULL,
    nome TEXT,
    telefone TEXT,
    empresa TEXT,
    tags TEXT[] DEFAULT '{}',
    custom_fields JSONB DEFAULT '{}',
    source TEXT DEFAULT 'manual' CHECK (source IN ('manual', 'import', 'sync:erp', 'form', 'api')),
    source_ref TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'unsubscribed', 'bounced', 'complained')),
    unsubscribed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, email)
);

ALTER TABLE mailing.contacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "contacts_own_org" ON mailing.contacts
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_mailing_contacts_org_email ON mailing.contacts(org_id, email);
CREATE INDEX idx_mailing_contacts_org_status ON mailing.contacts(org_id, status);
CREATE INDEX idx_mailing_contacts_tags ON mailing.contacts USING GIN(tags);


-- ============================================================================
-- 4. Contact Lists — static lists and dynamic segments
-- ============================================================================

CREATE TABLE mailing.contact_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    tipo TEXT NOT NULL DEFAULT 'static' CHECK (tipo IN ('static', 'dynamic')),
    filtros JSONB DEFAULT '{}',
    contact_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.contact_lists ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lists_own_org" ON mailing.contact_lists
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 5. Contact List Members — join table for static lists
-- ============================================================================

CREATE TABLE mailing.contact_list_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id UUID NOT NULL REFERENCES mailing.contact_lists(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(list_id, contact_id)
);

ALTER TABLE mailing.contact_list_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "list_members_via_list" ON mailing.contact_list_members
    FOR ALL TO authenticated
    USING (
        list_id IN (
            SELECT id FROM mailing.contact_lists
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );


-- ============================================================================
-- 6. Templates — email templates with variable interpolation
-- ============================================================================

CREATE TABLE mailing.templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    assunto TEXT NOT NULL,
    corpo_html TEXT NOT NULL,
    corpo_text TEXT,
    variaveis TEXT[] DEFAULT '{}',
    categoria TEXT DEFAULT 'marketing' CHECK (categoria IN ('marketing', 'transactional', 'follow_up', 'newsletter')),
    ativo BOOLEAN DEFAULT true,
    thumbnail_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "templates_own_org" ON mailing.templates
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 7. Campaigns — one-time email blasts
-- ============================================================================

CREATE TABLE mailing.campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    template_id UUID REFERENCES mailing.templates(id),
    list_id UUID REFERENCES mailing.contact_lists(id),
    assunto_override TEXT,
    remetente_nome TEXT,
    remetente_email TEXT,
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'agendada', 'enviando', 'enviada', 'pausada', 'cancelada')),
    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    total_recipients INT DEFAULT 0,
    total_sent INT DEFAULT 0,
    total_failed INT DEFAULT 0,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.campaigns ENABLE ROW LEVEL SECURITY;

CREATE POLICY "campaigns_own_org" ON mailing.campaigns
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 8. Automations — multi-step sequences
-- ============================================================================

CREATE TABLE mailing.automations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('contact_added', 'tag_added', 'list_joined', 'form_submitted', 'manual', 'webhook')),
    trigger_config JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'ativa', 'pausada')),
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.automations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "automations_own_org" ON mailing.automations
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 9. Automation Steps — individual steps in a sequence
-- ============================================================================

CREATE TABLE mailing.automation_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    automation_id UUID NOT NULL REFERENCES mailing.automations(id) ON DELETE CASCADE,
    posicao INT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('send_email', 'wait', 'condition', 'add_tag', 'remove_tag', 'move_to_list', 'webhook')),
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.automation_steps ENABLE ROW LEVEL SECURITY;

CREATE POLICY "steps_via_automation" ON mailing.automation_steps
    FOR ALL TO authenticated
    USING (
        automation_id IN (
            SELECT id FROM mailing.automations
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );


-- ============================================================================
-- 10. Automation Enrollments — contacts currently in an automation
-- ============================================================================

CREATE TABLE mailing.automation_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    automation_id UUID NOT NULL REFERENCES mailing.automations(id) ON DELETE CASCADE,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id) ON DELETE CASCADE,
    current_step_id UUID REFERENCES mailing.automation_steps(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'paused', 'exited')),
    next_action_at TIMESTAMPTZ,
    enrolled_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE(automation_id, contact_id)
);

ALTER TABLE mailing.automation_enrollments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "enrollments_via_automation" ON mailing.automation_enrollments
    FOR ALL TO authenticated
    USING (
        automation_id IN (
            SELECT id FROM mailing.automations
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );

CREATE INDEX idx_mailing_enrollments_next ON mailing.automation_enrollments(next_action_at)
    WHERE status = 'active';


-- ============================================================================
-- 11. Send Logs — per-recipient send tracking (campaigns + automations)
-- ============================================================================

CREATE TABLE mailing.send_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id),
    email TEXT NOT NULL,
    campaign_id UUID REFERENCES mailing.campaigns(id),
    automation_id UUID REFERENCES mailing.automations(id),
    automation_step_id UUID REFERENCES mailing.automation_steps(id),
    resend_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'complained', 'failed')),
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ,
    bounced_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.send_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "send_logs_own_org" ON mailing.send_logs
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);

CREATE INDEX idx_mailing_send_logs_campaign ON mailing.send_logs(campaign_id);
CREATE INDEX idx_mailing_send_logs_resend_id ON mailing.send_logs(resend_message_id);
CREATE INDEX idx_mailing_send_logs_status ON mailing.send_logs(status) WHERE status = 'queued';


-- ============================================================================
-- 12. Link Clicks — individual link click tracking
-- ============================================================================

CREATE TABLE mailing.link_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    send_log_id UUID NOT NULL REFERENCES mailing.send_logs(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    clicked_at TIMESTAMPTZ DEFAULT now(),
    user_agent TEXT,
    ip_address INET
);

ALTER TABLE mailing.link_clicks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "clicks_via_send_log" ON mailing.link_clicks
    FOR ALL TO authenticated
    USING (
        send_log_id IN (
            SELECT id FROM mailing.send_logs
            WHERE org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
        )
    );


-- ============================================================================
-- 13. Unsubscribes — compliance audit trail (LGPD)
-- ============================================================================

CREATE TABLE mailing.unsubscribes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    contact_id UUID NOT NULL REFERENCES mailing.contacts(id),
    email TEXT NOT NULL,
    reason TEXT DEFAULT 'link_click' CHECK (reason IN ('manual', 'link_click', 'complaint', 'admin')),
    campaign_id UUID REFERENCES mailing.campaigns(id),
    unsubscribed_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.unsubscribes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "unsubscribes_own_org" ON mailing.unsubscribes
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- 14. Sender Domains — domain verification tracking
-- ============================================================================

CREATE TABLE mailing.sender_domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    domain TEXT NOT NULL,
    resend_domain_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'failed')),
    dns_records JSONB,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mailing.sender_domains ENABLE ROW LEVEL SECURITY;

CREATE POLICY "domains_own_org" ON mailing.sender_domains
    FOR ALL TO authenticated
    USING (org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid);


-- ============================================================================
-- Seed data — page status for mailing features
-- ============================================================================

INSERT INTO mailing.status_pagina (nome_pagina, status) VALUES
    ('dashboard', 'producao'),
    ('contacts', 'producao'),
    ('lists', 'producao'),
    ('templates', 'producao'),
    ('campaigns', 'producao'),
    ('automations', 'producao'),
    ('analytics', 'producao'),
    ('settings', 'producao'),
    ('equipe', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
