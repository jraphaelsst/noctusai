-- ============================================================================
-- Media Scheduling — secondary indexes (FKs already inline in 002).
--
-- The source SQLAlchemy models declare:
--   • User.role            index=True
--   • User.phone_number    unique=True, index=True   (UNIQUE in 002)
--   • User.linked_identity index=True
--   • Property.code        unique=True, index=True   (UNIQUE in 002)
--   • Appointment.start_at index=True
--   • Appointment.end_at   index=True
--   • RouteGroup.date      index=True
--   • ConversationSummary.user_id          index=True
--   • ConversationSummary.conversation_id  index=True
--   • PendingChatIdentity.status           index=True
--   • ToolCallAudit.correlation_id         index=True
--   • ToolCallAudit.tool_name              index=True
--
-- UNIQUE constraints are already declared inline in 002 (Postgres
-- auto-creates the backing unique index). This file adds the non-unique
-- indexes the source models marked `index=True`, plus the canonical
-- tool_call_audits indexes from the seed template (see
-- noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template).
--
-- FK constraints: declared inline in 002 (NOT REPEATED HERE — adding them
-- a second time would error). This file is INDEXES ONLY despite the name
-- "indexes_and_fks" — the FKs land naturally with the table DDL because
-- splitting them out would force two-pass resolution and break local
-- replay. Filename kept per PROJECT.md §6 to match the spec.
-- ============================================================================

SET search_path = media_scheduling, public;


-- ----------------------------------------------------------------------------
-- authorized_users
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_authorized_users_role
    ON media_scheduling.authorized_users (role);

CREATE INDEX IF NOT EXISTS ix_authorized_users_linked_identity
    ON media_scheduling.authorized_users (linked_identity)
    WHERE linked_identity IS NOT NULL;


-- ----------------------------------------------------------------------------
-- appointments — start_at / end_at scans drive the calendar conflict checks
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_appointments_start_at
    ON media_scheduling.appointments (start_at);

CREATE INDEX IF NOT EXISTS ix_appointments_end_at
    ON media_scheduling.appointments (end_at);

-- Useful for "find appointments for crew X in window Y" queries the
-- scheduling engine will run via the seed Conflict Protocol.
CREATE INDEX IF NOT EXISTS ix_appointments_route_group_id
    ON media_scheduling.appointments (route_group_id)
    WHERE route_group_id IS NOT NULL;


-- ----------------------------------------------------------------------------
-- route_groups — date-window scans
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_route_groups_date
    ON media_scheduling.route_groups (date);


-- ----------------------------------------------------------------------------
-- conversation_summaries — per-user / per-conversation reads
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_conversation_summaries_user_id
    ON media_scheduling.conversation_summaries (user_id)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_conversation_summaries_conversation_id
    ON media_scheduling.conversation_summaries (conversation_id);


-- ----------------------------------------------------------------------------
-- pending_chat_identities — admin "show me pending" filter
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_pending_chat_identities_status
    ON media_scheduling.pending_chat_identities (status);


-- ----------------------------------------------------------------------------
-- tool_call_audits — canonical seed template indexes (verbatim shape)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_tool_call_audits_correlation_id
    ON media_scheduling.tool_call_audits (correlation_id);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_user_started
    ON media_scheduling.tool_call_audits (user_id, started_at);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_tool_name
    ON media_scheduling.tool_call_audits (tool_name);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_status
    ON media_scheduling.tool_call_audits (status);

CREATE INDEX IF NOT EXISTS ix_tool_call_audits_conversation
    ON media_scheduling.tool_call_audits (conversation_id, started_at);
