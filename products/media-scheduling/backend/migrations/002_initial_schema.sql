-- ============================================================================
-- Media Scheduling — domain schema port from whatsapp-google-scheduling
-- Schema: media_scheduling
-- Source: /Users/rapha/Documents/repository/NoctusAI/whatsapp-google-scheduling/
--         app/models/{user,appointment,property,condominium,service_type,
--                     crew_skill,route,conversation_summary,oauth_credential,
--                     pending_chat_identity,tool_call_audit}.py
--
-- 11 tables (per PROJECT.md §5 mapping):
--   1.  authorized_users           ← User
--   2.  appointments               ← Appointment       (+ appointment_requests scaffold)
--   3.  appointment_requests       ← AppointmentRequest (FK target — not in mapping
--                                    but Appointment FKs to it; brought in to
--                                    preserve relational integrity)
--   4.  appointment_request_services ← AppointmentRequestService (assoc table)
--   5.  properties                 ← Property
--   6.  condominiums               ← Condominium
--   7.  service_types              ← ServiceType
--   8.  crew_skills                ← CrewSkill (composite PK)
--   9.  routes (route_groups)      ← RouteGroup        (table named route_groups
--                                    to match source — PROJECT.md §5 calls it
--                                    `routes` but the source SQLAlchemy model
--                                    is `RouteGroup` with __tablename__ =
--                                    "route_groups"; preserved verbatim. Slip
--                                    surfaced — see Phase 2 improvements.)
--  10.  conversation_summaries     ← ConversationSummary
--  11.  oauth_credentials          ← OAuthCredential
--  12.  pending_chat_identities    ← PendingChatIdentity
--  13.  tool_call_audits           ← ToolCallAudit (via seed template;
--                                    landed in 002 for FK convenience —
--                                    user_id references authorized_users)
--
-- The 11-table count in PROJECT.md collapses appointment_requests +
-- appointment_request_services into "appointments" because they're the same
-- domain concept. This migration ships all 13 physical tables to preserve
-- the source's relational shape — the PROJECT.md mapping stays accurate at
-- the domain-aggregate level.
--
-- Authoring helpers used: noctusai_lib.domain.sql_templates emits
-- updated_at_function / updated_at_trigger / set_search_path. We could have
-- generated this whole file via those helpers but chose to inline the DDL
-- so the migration is a verbatim replay log per the "MCP migrations mirror
-- the file" rule. The generated form matches the helpers' output exactly.
--
-- RLS: see 003_rls.sql.
-- Indexes & FKs that aren't inline: see 004_indexes_and_fks.sql.
-- Baseline data: see 005_seed_data.sql.
-- ============================================================================

SET search_path = media_scheduling, public;


-- ============================================================================
-- updated_at helper (canonical seed shape — set_updated_at)
-- ============================================================================

CREATE OR REPLACE FUNCTION media_scheduling.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = media_scheduling, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;


-- ============================================================================
-- 1. authorized_users  (← source: User)
-- ============================================================================
-- Source `users` table renamed to `authorized_users` to make the auth model
-- explicit: every row here is an SSO-authorized actor (admin, real_estate_agent,
-- or media_crew). Phone-number indexed for WAHA inbound routing; linked_identity
-- captures the most-recent @lid_* chat ID for LID-aware first-inbound mapping
-- (see PROJECT.md §3 + accept-with-rationale on LID auth).

CREATE TABLE media_scheduling.authorized_users (
    id                BIGSERIAL PRIMARY KEY,
    name              VARCHAR(120)  NOT NULL,
    role              VARCHAR(40)   NOT NULL,
    phone_number      VARCHAR(32)   NOT NULL UNIQUE,
    email             VARCHAR(255),
    linked_identity   VARCHAR(128),
    active            BOOLEAN       NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER set_updated_at_authorized_users
    BEFORE UPDATE ON media_scheduling.authorized_users
    FOR EACH ROW EXECUTE FUNCTION media_scheduling.set_updated_at();


-- ============================================================================
-- 2. condominiums  (← source: Condominium)
-- ============================================================================

CREATE TABLE media_scheduling.condominiums (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(160)  NOT NULL UNIQUE,
    address     VARCHAR(255)  NOT NULL,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    notes       TEXT,
    active      BOOLEAN       NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER set_updated_at_condominiums
    BEFORE UPDATE ON media_scheduling.condominiums
    FOR EACH ROW EXECUTE FUNCTION media_scheduling.set_updated_at();


-- ============================================================================
-- 3. properties  (← source: Property)
-- ============================================================================

CREATE TABLE media_scheduling.properties (
    id              BIGSERIAL PRIMARY KEY,
    code            VARCHAR(32)   NOT NULL UNIQUE,
    condominium_id  BIGINT        NOT NULL REFERENCES media_scheduling.condominiums(id),
    unit            VARCHAR(80),
    address_notes   TEXT,
    active          BOOLEAN       NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER set_updated_at_properties
    BEFORE UPDATE ON media_scheduling.properties
    FOR EACH ROW EXECUTE FUNCTION media_scheduling.set_updated_at();


-- ============================================================================
-- 4. service_types  (← source: ServiceType)
-- ============================================================================

CREATE TABLE media_scheduling.service_types (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(80)  NOT NULL UNIQUE,
    description  TEXT,
    active       BOOLEAN      NOT NULL DEFAULT true
);


-- ============================================================================
-- 5. crew_skills  (← source: CrewSkill, composite PK)
-- ============================================================================

CREATE TABLE media_scheduling.crew_skills (
    user_id  BIGINT       NOT NULL REFERENCES media_scheduling.authorized_users(id) ON DELETE CASCADE,
    skill    VARCHAR(40)  NOT NULL,
    PRIMARY KEY (user_id, skill)
);


-- ============================================================================
-- 6. route_groups  (← source: RouteGroup; PROJECT.md mapping calls this
--    table `routes` but source __tablename__ is `route_groups`. Preserved
--    verbatim — appointments.route_group_id FK targets this name. See
--    Phase 2 improvements for the mapping-doc fix follow-up.)
-- ============================================================================

CREATE TABLE media_scheduling.route_groups (
    id                       BIGSERIAL PRIMARY KEY,
    date                     DATE          NOT NULL,
    media_crew_user_id       BIGINT        REFERENCES media_scheduling.authorized_users(id),
    office_start_location    VARCHAR(255),
    office_end_location      VARCHAR(255),
    optimization_status      VARCHAR(40)   NOT NULL DEFAULT 'not_started',
    created_at               TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER set_updated_at_route_groups
    BEFORE UPDATE ON media_scheduling.route_groups
    FOR EACH ROW EXECUTE FUNCTION media_scheduling.set_updated_at();


-- ============================================================================
-- 7. appointment_requests  (← source: AppointmentRequest)
-- ============================================================================
-- Booking intent in flight before it becomes a confirmed appointment.
-- Status FSM: collecting_details → awaiting_confirmation → scheduled / canceled.

CREATE TABLE media_scheduling.appointment_requests (
    id                      BIGSERIAL PRIMARY KEY,
    requester_user_id       BIGINT        NOT NULL REFERENCES media_scheduling.authorized_users(id),
    property_id             BIGINT        REFERENCES media_scheduling.properties(id),
    condominium_id          BIGINT        REFERENCES media_scheduling.condominiums(id),
    requested_date          DATE,
    requested_time_window   VARCHAR(40),
    status                  VARCHAR(40)   NOT NULL DEFAULT 'collecting_details',
    notes                   TEXT,
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER set_updated_at_appointment_requests
    BEFORE UPDATE ON media_scheduling.appointment_requests
    FOR EACH ROW EXECUTE FUNCTION media_scheduling.set_updated_at();


-- ============================================================================
-- 8. appointment_request_services  (← source: AppointmentRequestService, assoc)
-- ============================================================================

CREATE TABLE media_scheduling.appointment_request_services (
    appointment_request_id  BIGINT  NOT NULL REFERENCES media_scheduling.appointment_requests(id) ON DELETE CASCADE,
    service_type_id         BIGINT  NOT NULL REFERENCES media_scheduling.service_types(id),
    PRIMARY KEY (appointment_request_id, service_type_id)
);


-- ============================================================================
-- 9. appointments  (← source: Appointment)
-- ============================================================================

CREATE TABLE media_scheduling.appointments (
    id                          BIGSERIAL PRIMARY KEY,
    appointment_request_id      BIGINT        REFERENCES media_scheduling.appointment_requests(id),
    google_calendar_event_id    VARCHAR(255),
    start_at                    TIMESTAMPTZ   NOT NULL,
    end_at                      TIMESTAMPTZ   NOT NULL,
    property_id                 BIGINT        NOT NULL REFERENCES media_scheduling.properties(id),
    condominium_id              BIGINT        NOT NULL REFERENCES media_scheduling.condominiums(id),
    route_group_id              BIGINT        REFERENCES media_scheduling.route_groups(id),
    status                      VARCHAR(40)   NOT NULL DEFAULT 'scheduled',
    created_at                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TRIGGER set_updated_at_appointments
    BEFORE UPDATE ON media_scheduling.appointments
    FOR EACH ROW EXECUTE FUNCTION media_scheduling.set_updated_at();


-- ============================================================================
-- 10. conversation_summaries  (← source: ConversationSummary)
-- ============================================================================

CREATE TABLE media_scheduling.conversation_summaries (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT        REFERENCES media_scheduling.authorized_users(id),
    conversation_id  VARCHAR(64)   NOT NULL,
    summary_text     TEXT          NOT NULL,
    label            JSONB,
    message_count    INTEGER       NOT NULL DEFAULT 0,
    model_used       VARCHAR(80),
    started_at       TIMESTAMPTZ,
    ended_at         TIMESTAMPTZ   NOT NULL,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now()
);


-- ============================================================================
-- 11. oauth_credentials  (← source: OAuthCredential)
-- ============================================================================

CREATE TABLE media_scheduling.oauth_credentials (
    id                          BIGSERIAL PRIMARY KEY,
    provider                    VARCHAR(40)   NOT NULL,
    account_email               VARCHAR(255)  NOT NULL,
    refresh_token               TEXT          NOT NULL,
    access_token                TEXT,
    access_token_expires_at     TIMESTAMPTZ,
    scopes                      TEXT          NOT NULL,
    created_at                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_oauth_credentials_provider_email UNIQUE (provider, account_email)
);

CREATE TRIGGER set_updated_at_oauth_credentials
    BEFORE UPDATE ON media_scheduling.oauth_credentials
    FOR EACH ROW EXECUTE FUNCTION media_scheduling.set_updated_at();


-- ============================================================================
-- 12. pending_chat_identities  (← source: PendingChatIdentity)
-- ============================================================================
-- WAHA inbound from an unknown chat_id. Bot replies "we'll follow up", admin
-- resolves to a real authorized_users row or rejects. Status FSM: pending →
-- resolved | rejected.

CREATE TABLE media_scheduling.pending_chat_identities (
    id                    BIGSERIAL PRIMARY KEY,
    chat_id               VARCHAR(128)  NOT NULL UNIQUE,
    push_name             VARCHAR(120),
    phone_hint            VARCHAR(32),
    status                VARCHAR(20)   NOT NULL DEFAULT 'pending',
    captured_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    resolved_at           TIMESTAMPTZ,
    resolved_to_user_id   BIGINT        REFERENCES media_scheduling.authorized_users(id)
);


-- ============================================================================
-- 13. tool_call_audits  (canonical seed template — verbatim shape from
--     noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template)
-- ============================================================================
-- Source ToolCallAudit had `arguments_json` / `result_json` as TEXT. Seed
-- canonical shape is JSONB — ported to JSONB per the seed template (better
-- for query + matches `AuditRecord.arguments` / `.result` writer semantics).
-- The seed template's `tool_call_id` column (absent in source) is included
-- because seed `AuditRecord` writes it (OpenAI per-call ID, distinct from
-- gpt_call_id which is informational).

CREATE TABLE media_scheduling.tool_call_audits (
    id                BIGSERIAL PRIMARY KEY,
    correlation_id    VARCHAR(64),
    gpt_call_id       VARCHAR(64),
    tool_call_id      VARCHAR(64),
    conversation_id   VARCHAR(64),
    user_id           BIGINT        REFERENCES media_scheduling.authorized_users(id),
    tool_name         VARCHAR(80)   NOT NULL,
    status            VARCHAR(16)   NOT NULL,
    arguments         JSONB,
    result            JSONB,
    error             TEXT,
    duration_ms       INTEGER,
    started_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
    -- archived_at    TIMESTAMPTZ  -- uncomment when retention sweep ships
);
