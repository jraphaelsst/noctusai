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
