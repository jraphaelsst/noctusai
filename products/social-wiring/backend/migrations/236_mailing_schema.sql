-- ============================================================================
-- Migration 236 — the `mailing` schema, declared in code at last.
--
-- WHY: `mailing` is the legacy email-marketing schema social-wiring absorbed
-- (001 notes "email_marketing tables absorbed from `mailing`"). It exists in
-- prod — 16 tables, 2 policies each, 11 acting-audit triggers — and SW code
-- still WRITES it (email_marketing/routers/ai.py → persist_output(db,
-- schema="mailing") → mailing.ai_outputs), yet NO migration ever created it:
-- prod-only drift. SW 012/212/214 alter it, so a fresh chain (migration_replay,
-- a restored or new environment) had no mailing at all and the email-marketing
-- AI persist path would fail there. Destination NOC-REMEDIATE[mailing-schema-
-- migration] in migration_replay.REMEDIATE_CLASSES.
--
-- WHAT: generated 2026-10-10 from the PROD catalog (pg_attribute / pg_constraint
-- / pg_indexes / pg_policies / role_table_grants), read-only. In prod every
-- statement is a no-op: CREATE ... IF NOT EXISTS, policies created only when
-- absent, audit triggers attached only when a table lacks one, the
-- status_pagina rows ON CONFLICT DO NOTHING, grants identical to prod's.
-- Deliberately NOT reproduced: prod's grants to anon (ALL on every table + anon
-- default privileges) — 237 revokes those in prod; a fresh chain never gets them.
--
-- Retiring `mailing` (re-pointing email_marketing at social_wiring) is an open
-- OWNER question, not this migration's call: NOC-REMEDIATE[mailing-schema-keep-
-- or-retire] at its live writer, email_marketing/routers/ai.py.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mailing;
GRANT USAGE ON SCHEMA mailing TO anon, authenticated, service_role;
SET search_path = mailing, public;

CREATE TABLE IF NOT EXISTS mailing.ai_feedback (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid DEFAULT current_org_id() NOT NULL,
    user_id uuid NOT NULL,
    output_ref text NOT NULL,
    rating integer NOT NULL,
    notes text,
    prompt_version text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ai_feedback_pkey PRIMARY KEY (id),
    CONSTRAINT ai_feedback_user_ref_unique UNIQUE (user_id, output_ref),
    CONSTRAINT ai_feedback_rating_check CHECK ((rating = ANY (ARRAY['-1'::integer, 1])))
);
CREATE TABLE IF NOT EXISTS mailing.ai_outputs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid DEFAULT current_org_id() NOT NULL,
    ref_type text NOT NULL,
    ref_id uuid NOT NULL,
    kind text NOT NULL,
    label text NOT NULL,
    score numeric,
    chip text,
    explanation text,
    confidence numeric,
    model_version text,
    prompt_version text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ai_outputs_pkey PRIMARY KEY (id),
    CONSTRAINT ai_outputs_confidence_range CHECK (((confidence IS NULL) OR ((confidence >= (0)::numeric) AND (confidence <= (1)::numeric)))),
    CONSTRAINT ai_outputs_kind_check CHECK ((kind = ANY (ARRAY['classification'::text, 'score'::text, 'flag'::text, 'extraction'::text, 'narrative'::text])))
);
CREATE TABLE IF NOT EXISTS mailing.automations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    nome text NOT NULL,
    descricao text,
    trigger_type text NOT NULL,
    trigger_config jsonb DEFAULT '{}'::jsonb,
    status text DEFAULT 'rascunho'::text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT automations_pkey PRIMARY KEY (id),
    CONSTRAINT automations_status_check CHECK ((status = ANY (ARRAY['rascunho'::text, 'ativa'::text, 'pausada'::text]))),
    CONSTRAINT automations_trigger_type_check CHECK ((trigger_type = ANY (ARRAY['contact_added'::text, 'tag_added'::text, 'list_joined'::text, 'form_submitted'::text, 'manual'::text, 'webhook'::text])))
);
CREATE TABLE IF NOT EXISTS mailing.contact_lists (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    nome text NOT NULL,
    descricao text,
    tipo text DEFAULT 'static'::text NOT NULL,
    filtros jsonb DEFAULT '{}'::jsonb,
    contact_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT contact_lists_pkey PRIMARY KEY (id),
    CONSTRAINT contact_lists_tipo_check CHECK ((tipo = ANY (ARRAY['static'::text, 'dynamic'::text])))
);
CREATE TABLE IF NOT EXISTS mailing.contacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    email text NOT NULL,
    nome text,
    telefone text,
    empresa text,
    tags text[] DEFAULT '{}'::text[],
    custom_fields jsonb DEFAULT '{}'::jsonb,
    source text DEFAULT 'manual'::text,
    source_ref text,
    status text DEFAULT 'active'::text NOT NULL,
    unsubscribed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT contacts_pkey PRIMARY KEY (id),
    CONSTRAINT contacts_org_id_email_key UNIQUE (org_id, email),
    CONSTRAINT contacts_source_check CHECK ((source = ANY (ARRAY['manual'::text, 'import'::text, 'sync:erp'::text, 'form'::text, 'api'::text]))),
    CONSTRAINT contacts_status_check CHECK ((status = ANY (ARRAY['active'::text, 'unsubscribed'::text, 'bounced'::text, 'complained'::text])))
);
CREATE TABLE IF NOT EXISTS mailing.invitations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    email text NOT NULL,
    role text DEFAULT 'member'::text NOT NULL,
    invited_by uuid NOT NULL,
    token text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    expires_at timestamp with time zone DEFAULT (now() + '7 days'::interval) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    accepted_at timestamp with time zone,
    accepted_by uuid,
    CONSTRAINT invitations_pkey PRIMARY KEY (id),
    CONSTRAINT invitations_token_key UNIQUE (token),
    CONSTRAINT invitations_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'accepted'::text, 'expired'::text, 'canceled'::text]))),
    CONSTRAINT invitations_accepted_by_fkey FOREIGN KEY (accepted_by) REFERENCES auth.users(id)
);
CREATE TABLE IF NOT EXISTS mailing.sender_domains (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    domain text NOT NULL,
    resend_domain_id text,
    status text DEFAULT 'pending'::text NOT NULL,
    dns_records jsonb,
    verified_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sender_domains_pkey PRIMARY KEY (id),
    CONSTRAINT sender_domains_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'verified'::text, 'failed'::text])))
);
CREATE TABLE IF NOT EXISTS mailing.status_pagina (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    nome_pagina text NOT NULL,
    status text DEFAULT 'producao'::text NOT NULL,
    descricao text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT status_pagina_pkey PRIMARY KEY (id),
    CONSTRAINT status_pagina_nome_pagina_key UNIQUE (nome_pagina),
    CONSTRAINT status_pagina_status_check CHECK ((status = ANY (ARRAY['producao'::text, 'desenvolvimento'::text, 'desativado'::text])))
);
CREATE TABLE IF NOT EXISTS mailing.templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    nome text NOT NULL,
    assunto text NOT NULL,
    corpo_html text NOT NULL,
    corpo_text text,
    variaveis text[] DEFAULT '{}'::text[],
    categoria text DEFAULT 'marketing'::text,
    ativo boolean DEFAULT true,
    thumbnail_url text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT templates_pkey PRIMARY KEY (id),
    CONSTRAINT templates_categoria_check CHECK ((categoria = ANY (ARRAY['marketing'::text, 'transactional'::text, 'follow_up'::text, 'newsletter'::text])))
);
CREATE TABLE IF NOT EXISTS mailing.automation_steps (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    automation_id uuid NOT NULL,
    posicao integer NOT NULL,
    tipo text NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT automation_steps_pkey PRIMARY KEY (id),
    CONSTRAINT automation_steps_tipo_check CHECK ((tipo = ANY (ARRAY['send_email'::text, 'wait'::text, 'condition'::text, 'add_tag'::text, 'remove_tag'::text, 'move_to_list'::text, 'webhook'::text]))),
    CONSTRAINT automation_steps_automation_id_fkey FOREIGN KEY (automation_id) REFERENCES mailing.automations(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mailing.campaigns (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    nome text NOT NULL,
    template_id uuid,
    list_id uuid,
    assunto_override text,
    remetente_nome text,
    remetente_email text,
    status text DEFAULT 'rascunho'::text NOT NULL,
    scheduled_at timestamp with time zone,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    total_recipients integer DEFAULT 0,
    total_sent integer DEFAULT 0,
    total_failed integer DEFAULT 0,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT campaigns_pkey PRIMARY KEY (id),
    CONSTRAINT campaigns_status_check CHECK ((status = ANY (ARRAY['rascunho'::text, 'agendada'::text, 'enviando'::text, 'enviada'::text, 'pausada'::text, 'cancelada'::text]))),
    CONSTRAINT campaigns_list_id_fkey FOREIGN KEY (list_id) REFERENCES mailing.contact_lists(id),
    CONSTRAINT campaigns_template_id_fkey FOREIGN KEY (template_id) REFERENCES mailing.templates(id)
);
CREATE TABLE IF NOT EXISTS mailing.contact_list_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    list_id uuid NOT NULL,
    contact_id uuid NOT NULL,
    added_at timestamp with time zone DEFAULT now(),
    CONSTRAINT contact_list_members_pkey PRIMARY KEY (id),
    CONSTRAINT contact_list_members_list_id_contact_id_key UNIQUE (list_id, contact_id),
    CONSTRAINT contact_list_members_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES mailing.contacts(id) ON DELETE CASCADE,
    CONSTRAINT contact_list_members_list_id_fkey FOREIGN KEY (list_id) REFERENCES mailing.contact_lists(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mailing.send_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    contact_id uuid NOT NULL,
    email text NOT NULL,
    campaign_id uuid,
    automation_id uuid,
    automation_step_id uuid,
    resend_message_id text,
    status text DEFAULT 'queued'::text NOT NULL,
    sent_at timestamp with time zone,
    delivered_at timestamp with time zone,
    opened_at timestamp with time zone,
    clicked_at timestamp with time zone,
    bounced_at timestamp with time zone,
    error_message text,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT send_logs_pkey PRIMARY KEY (id),
    CONSTRAINT send_logs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'sent'::text, 'delivered'::text, 'opened'::text, 'clicked'::text, 'bounced'::text, 'complained'::text, 'failed'::text]))),
    CONSTRAINT send_logs_automation_id_fkey FOREIGN KEY (automation_id) REFERENCES mailing.automations(id),
    CONSTRAINT send_logs_automation_step_id_fkey FOREIGN KEY (automation_step_id) REFERENCES mailing.automation_steps(id),
    CONSTRAINT send_logs_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES mailing.campaigns(id),
    CONSTRAINT send_logs_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES mailing.contacts(id)
);
CREATE TABLE IF NOT EXISTS mailing.unsubscribes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    contact_id uuid NOT NULL,
    email text NOT NULL,
    reason text DEFAULT 'link_click'::text,
    campaign_id uuid,
    unsubscribed_at timestamp with time zone DEFAULT now(),
    CONSTRAINT unsubscribes_pkey PRIMARY KEY (id),
    CONSTRAINT unsubscribes_reason_check CHECK ((reason = ANY (ARRAY['manual'::text, 'link_click'::text, 'complaint'::text, 'admin'::text]))),
    CONSTRAINT unsubscribes_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES mailing.campaigns(id),
    CONSTRAINT unsubscribes_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES mailing.contacts(id)
);
CREATE TABLE IF NOT EXISTS mailing.automation_enrollments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    automation_id uuid NOT NULL,
    contact_id uuid NOT NULL,
    current_step_id uuid,
    status text DEFAULT 'active'::text NOT NULL,
    next_action_at timestamp with time zone,
    enrolled_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    CONSTRAINT automation_enrollments_pkey PRIMARY KEY (id),
    CONSTRAINT automation_enrollments_automation_id_contact_id_key UNIQUE (automation_id, contact_id),
    CONSTRAINT automation_enrollments_status_check CHECK ((status = ANY (ARRAY['active'::text, 'completed'::text, 'paused'::text, 'exited'::text]))),
    CONSTRAINT automation_enrollments_automation_id_fkey FOREIGN KEY (automation_id) REFERENCES mailing.automations(id) ON DELETE CASCADE,
    CONSTRAINT automation_enrollments_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES mailing.contacts(id) ON DELETE CASCADE,
    CONSTRAINT automation_enrollments_current_step_id_fkey FOREIGN KEY (current_step_id) REFERENCES mailing.automation_steps(id)
);
CREATE TABLE IF NOT EXISTS mailing.link_clicks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    send_log_id uuid NOT NULL,
    url text NOT NULL,
    clicked_at timestamp with time zone DEFAULT now(),
    user_agent text,
    ip_address inet,
    CONSTRAINT link_clicks_pkey PRIMARY KEY (id),
    CONSTRAINT link_clicks_send_log_id_fkey FOREIGN KEY (send_log_id) REFERENCES mailing.send_logs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ai_feedback_org_idx ON mailing.ai_feedback USING btree (org_id);
CREATE INDEX IF NOT EXISTS ai_feedback_output_ref_idx ON mailing.ai_feedback USING btree (output_ref);
CREATE INDEX IF NOT EXISTS ai_outputs_created_idx ON mailing.ai_outputs USING btree (created_at DESC);
CREATE INDEX IF NOT EXISTS ai_outputs_org_idx ON mailing.ai_outputs USING btree (org_id);
CREATE INDEX IF NOT EXISTS ai_outputs_ref_idx ON mailing.ai_outputs USING btree (ref_type, ref_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mailing_enrollments_next ON mailing.automation_enrollments USING btree (next_action_at) WHERE (status = 'active'::text);
CREATE INDEX IF NOT EXISTS idx_mailing_contacts_org_email ON mailing.contacts USING btree (org_id, email);
CREATE INDEX IF NOT EXISTS idx_mailing_contacts_org_status ON mailing.contacts USING btree (org_id, status);
CREATE INDEX IF NOT EXISTS idx_mailing_contacts_tags ON mailing.contacts USING gin (tags);
CREATE INDEX IF NOT EXISTS idx_mailing_invitations_org ON mailing.invitations USING btree (org_id);
CREATE INDEX IF NOT EXISTS idx_mailing_invitations_token ON mailing.invitations USING btree (token);
CREATE INDEX IF NOT EXISTS idx_mailing_send_logs_campaign ON mailing.send_logs USING btree (campaign_id);
CREATE INDEX IF NOT EXISTS idx_mailing_send_logs_resend_id ON mailing.send_logs USING btree (resend_message_id);
CREATE INDEX IF NOT EXISTS idx_mailing_send_logs_status ON mailing.send_logs USING btree (status) WHERE (status = 'queued'::text);

ALTER TABLE mailing.ai_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.ai_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.automation_enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.automation_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.automations ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.contact_list_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.contact_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.link_clicks ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.send_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.sender_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.status_pagina ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailing.unsubscribes ENABLE ROW LEVEL SECURITY;

DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'ai_feedback' AND policyname = 'ai_feedback_own_org') THEN
    CREATE POLICY ai_feedback_own_org ON mailing.ai_feedback AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for))) WITH CHECK (((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)) AND (user_id = ( SELECT auth.uid() AS uid))));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'ai_feedback' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.ai_feedback AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'ai_outputs' AND policyname = 'ai_outputs_own_org') THEN
    CREATE POLICY ai_outputs_own_org ON mailing.ai_outputs AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for))) WITH CHECK ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'ai_outputs' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.ai_outputs AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'automation_enrollments' AND policyname = 'enrollments_via_automation') THEN
    CREATE POLICY enrollments_via_automation ON mailing.automation_enrollments AS PERMISSIVE FOR ALL TO authenticated USING ((automation_id IN ( SELECT automations.id
   FROM mailing.automations
  WHERE (automations.org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)))));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'automation_enrollments' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.automation_enrollments AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'automation_steps' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.automation_steps AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'automation_steps' AND policyname = 'steps_via_automation') THEN
    CREATE POLICY steps_via_automation ON mailing.automation_steps AS PERMISSIVE FOR ALL TO authenticated USING ((automation_id IN ( SELECT automations.id
   FROM mailing.automations
  WHERE (automations.org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)))));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'automations' AND policyname = 'automations_own_org') THEN
    CREATE POLICY automations_own_org ON mailing.automations AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'automations' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.automations AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'campaigns' AND policyname = 'campaigns_own_org') THEN
    CREATE POLICY campaigns_own_org ON mailing.campaigns AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'campaigns' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.campaigns AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'contact_list_members' AND policyname = 'list_members_via_list') THEN
    CREATE POLICY list_members_via_list ON mailing.contact_list_members AS PERMISSIVE FOR ALL TO authenticated USING ((list_id IN ( SELECT contact_lists.id
   FROM mailing.contact_lists
  WHERE (contact_lists.org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)))));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'contact_list_members' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.contact_list_members AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'contact_lists' AND policyname = 'lists_own_org') THEN
    CREATE POLICY lists_own_org ON mailing.contact_lists AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'contact_lists' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.contact_lists AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'contacts' AND policyname = 'contacts_own_org') THEN
    CREATE POLICY contacts_own_org ON mailing.contacts AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'contacts' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.contacts AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'invitations' AND policyname = 'invitations_select_own_org') THEN
    CREATE POLICY invitations_select_own_org ON mailing.invitations AS PERMISSIVE FOR SELECT TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'invitations' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.invitations AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'link_clicks' AND policyname = 'clicks_via_send_log') THEN
    CREATE POLICY clicks_via_send_log ON mailing.link_clicks AS PERMISSIVE FOR ALL TO authenticated USING ((send_log_id IN ( SELECT send_logs.id
   FROM mailing.send_logs
  WHERE (send_logs.org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)))));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'link_clicks' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.link_clicks AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'send_logs' AND policyname = 'send_logs_own_org') THEN
    CREATE POLICY send_logs_own_org ON mailing.send_logs AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'send_logs' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.send_logs AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'sender_domains' AND policyname = 'domains_own_org') THEN
    CREATE POLICY domains_own_org ON mailing.sender_domains AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'sender_domains' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.sender_domains AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'status_pagina' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.status_pagina AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'status_pagina' AND policyname = 'todos_veem_producao') THEN
    CREATE POLICY todos_veem_producao ON mailing.status_pagina AS PERMISSIVE FOR SELECT TO public USING ((status = 'producao'::text));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'templates' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.templates AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'templates' AND policyname = 'templates_own_org') THEN
    CREATE POLICY templates_own_org ON mailing.templates AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'unsubscribes' AND policyname = 'service_role_bypass') THEN
    CREATE POLICY service_role_bypass ON mailing.unsubscribes AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
  END IF;
END $pol$;
DO $pol$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'mailing' AND tablename = 'unsubscribes' AND policyname = 'unsubscribes_own_org') THEN
    CREATE POLICY unsubscribes_own_org ON mailing.unsubscribes AS PERMISSIVE FOR ALL TO authenticated USING ((org_id = ( SELECT current_org_id_for('social_wiring'::text) AS current_org_id_for)));
  END IF;
END $pol$;

GRANT DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON mailing.ai_feedback, mailing.ai_outputs, mailing.automation_enrollments, mailing.automation_steps, mailing.automations, mailing.campaigns, mailing.contact_list_members, mailing.contact_lists, mailing.contacts, mailing.link_clicks, mailing.send_logs, mailing.sender_domains, mailing.status_pagina, mailing.templates, mailing.unsubscribes TO authenticated;
GRANT DELETE, INSERT, REFERENCES, TRIGGER, TRUNCATE, UPDATE ON mailing.invitations TO authenticated;
GRANT DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON mailing.ai_feedback, mailing.ai_outputs, mailing.automation_enrollments, mailing.automation_steps, mailing.automations, mailing.campaigns, mailing.contact_list_members, mailing.contact_lists, mailing.contacts, mailing.invitations, mailing.link_clicks, mailing.send_logs, mailing.sender_domains, mailing.status_pagina, mailing.templates, mailing.unsubscribes TO service_role;

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

-- Acting-audit triggers (as 214 attached them), only where a table lacks one —
-- attach_acting_audit_triggers drops/recreates, so calling it in prod would not
-- be a no-op.
DO $audit$
BEGIN
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE NOTICE 'core 072 not applied — mailing acting-audit triggers not attached';
    RETURN;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'mailing' AND c.relkind = 'r'
       AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'org_id' AND NOT a.attisdropped)
       AND NOT EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid = c.oid AND t.tgname = 'audit_acting_write')
  ) THEN
    PERFORM public.attach_acting_audit_triggers('mailing', 'social_wiring');
  END IF;
END
$audit$;

ALTER DEFAULT PRIVILEGES IN SCHEMA mailing GRANT ALL ON TABLES TO authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA mailing GRANT ALL ON SEQUENCES TO authenticated, service_role;
