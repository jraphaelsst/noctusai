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
