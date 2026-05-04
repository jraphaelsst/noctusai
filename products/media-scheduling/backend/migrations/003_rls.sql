-- ============================================================================
-- Media Scheduling — RLS policies for the 13 domain tables.
-- Source design notes: PROJECT.md §3 (Two-surface auth) + §6 Phase 2.
--
-- Two write paths:
--   1. Admin SSO  — authenticated users with the seed SSO `noctus_role`
--      `platform_admin` OR an explicit JWT claim (here: `media_scheduling_admin`).
--      Reads + writes on admin tables (authorized_users, condominiums,
--      properties, service_types, crew_skills, oauth_credentials,
--      pending_chat_identities, route_groups, appointments,
--      appointment_requests).
--   2. Service role — worker / webhook bypass. service_role bypasses RLS
--      automatically in PostgREST (no policies needed); we explicitly note
--      this rather than authoring redundant `TO service_role` policies. The
--      worker writes via service_role; the WAHA webhook writes via
--      service_role; the SSO admin frontend writes via authenticated.
--
-- Read-only-from-frontend tables for non-admin authenticated users:
--   None in v1 — everything is admin-only or service-role. Future when
--   real_estate_agent / media_crew get user-facing pages, add
--   role-scoped SELECT policies (recommendation: add to a future
--   `004_<n>_user_role_policies.sql` to keep the audit log linear).
--
-- Policy shape: all policies use the canonical
-- `(SELECT auth.jwt())` subquery shape per `KB § PATTERNS/database-rls.md`.
-- The platform's SSO claim layout is documented at
-- `KB § PATTERNS/database-rls.md § SSO claims` — `noctus_role` is the
-- platform-wide claim (admin path) and `media_scheduling_admin = true`
-- is the per-product opt-in (set by the SSO bootstrap when a user is
-- granted admin access to this product).
--
-- LGPD: tool_call_audits.arguments / .result may carry PII per the seed
-- template; admin-only SELECT enforces that the LGPD scope is the same
-- as the rest of the product schema (KB § PATTERNS/llm-tool-audit.md
-- § LGPD).
-- ============================================================================

SET search_path = media_scheduling, public;


-- ----------------------------------------------------------------------------
-- Helper: admin predicate
-- ----------------------------------------------------------------------------
-- A user is a media-scheduling admin when EITHER:
--   - their JWT carries `noctus_role = 'platform_admin'`, OR
--   - their JWT carries `media_scheduling_admin = true`.
-- Inlined as a subquery in every policy; no function wrapper because the
-- platform's RLS pattern keeps predicates inline (KB § PATTERNS/database-rls.md
-- § Subquery shape — easier for the planner to optimize than a SECURITY DEFINER
-- function call).


-- ============================================================================
-- 1. authorized_users
-- ============================================================================

ALTER TABLE media_scheduling.authorized_users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authorized_users_admin_all" ON media_scheduling.authorized_users
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 2. condominiums
-- ============================================================================

ALTER TABLE media_scheduling.condominiums ENABLE ROW LEVEL SECURITY;

CREATE POLICY "condominiums_admin_all" ON media_scheduling.condominiums
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 3. properties
-- ============================================================================

ALTER TABLE media_scheduling.properties ENABLE ROW LEVEL SECURITY;

CREATE POLICY "properties_admin_all" ON media_scheduling.properties
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 4. service_types
-- ============================================================================

ALTER TABLE media_scheduling.service_types ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_types_admin_all" ON media_scheduling.service_types
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 5. crew_skills
-- ============================================================================

ALTER TABLE media_scheduling.crew_skills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "crew_skills_admin_all" ON media_scheduling.crew_skills
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 6. route_groups
-- ============================================================================

ALTER TABLE media_scheduling.route_groups ENABLE ROW LEVEL SECURITY;

CREATE POLICY "route_groups_admin_all" ON media_scheduling.route_groups
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 7. appointment_requests
-- ============================================================================

ALTER TABLE media_scheduling.appointment_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "appointment_requests_admin_all" ON media_scheduling.appointment_requests
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 8. appointment_request_services
-- ============================================================================

ALTER TABLE media_scheduling.appointment_request_services ENABLE ROW LEVEL SECURITY;

-- Authorize via parent appointment_request (same admin gate, expressed as a
-- subquery so the policy survives FK-chain joins cleanly).
CREATE POLICY "appointment_request_services_admin_all"
    ON media_scheduling.appointment_request_services
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 9. appointments
-- ============================================================================

ALTER TABLE media_scheduling.appointments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "appointments_admin_all" ON media_scheduling.appointments
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 10. conversation_summaries
-- ============================================================================

ALTER TABLE media_scheduling.conversation_summaries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "conversation_summaries_admin_all"
    ON media_scheduling.conversation_summaries
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 11. oauth_credentials
-- ============================================================================
-- Refresh tokens are sensitive — admin-only read AND write. Worker reads via
-- service_role (bypasses RLS).

ALTER TABLE media_scheduling.oauth_credentials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "oauth_credentials_admin_all" ON media_scheduling.oauth_credentials
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 12. pending_chat_identities
-- ============================================================================

ALTER TABLE media_scheduling.pending_chat_identities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "pending_chat_identities_admin_all"
    ON media_scheduling.pending_chat_identities
    FOR ALL TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    )
    WITH CHECK (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );


-- ============================================================================
-- 13. tool_call_audits
-- ============================================================================
-- Admin-only read (LGPD-flagged content possible). Worker writes via
-- service_role.

ALTER TABLE media_scheduling.tool_call_audits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tool_call_audits_admin_select" ON media_scheduling.tool_call_audits
    FOR SELECT TO authenticated
    USING (
        ((SELECT auth.jwt()) ->> 'noctus_role') = 'platform_admin'
        OR ((SELECT auth.jwt()) -> 'media_scheduling_admin')::boolean = true
    );

-- No INSERT/UPDATE/DELETE policies for `authenticated` — writes are
-- service_role-only (worker dispatch path).
