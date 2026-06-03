-- ============================================================================
-- Migration 011 — Social/Content Studio: campaigns, posts, approvals
--
-- WHY:
--   Implements the agency content pipeline for the orbity product.
--   Three tables: content_campaigns → content_posts → post_approvals.
--   post_approvals carries a public_token (uuid) that drives the
--   unauthenticated client-approval flow — the token IS the authorization
--   for that specific approval row (validated + expiry-checked server-side).
--
--   RLS on all three tables via public.current_org_id() (SECURITY DEFINER,
--   trusted-table-derived). post_approvals is also accessible via a
--   SECURITY DEFINER function for the public token flow (service_role bypass).
--
--   NEVER USING(true), NEVER JWT/user_metadata (per noc memory
--   feedback_rls_never_key_on_user_metadata).
--
-- IDEMPOTENT: CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS.
-- SEARCH PATH: session-pinned to orbity, public (consistent with earlier migrations).
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. content_campaigns — editorial calendar containers per client per month
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.content_campaigns (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    client_id   UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    month       TEXT NOT NULL,   -- ISO "YYYY-MM" e.g. "2026-07"
    status      TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS content_campaigns_org_id_idx
    ON orbity.content_campaigns (org_id);
CREATE INDEX IF NOT EXISTS content_campaigns_org_client_idx
    ON orbity.content_campaigns (org_id, client_id);
CREATE INDEX IF NOT EXISTS content_campaigns_org_month_idx
    ON orbity.content_campaigns (org_id, month);

-- updated_at trigger (reuse orbity.set_updated_at defined in 005_crm_core.sql)
DROP TRIGGER IF EXISTS trg_content_campaigns_updated_at ON orbity.content_campaigns;
CREATE TRIGGER trg_content_campaigns_updated_at
    BEFORE UPDATE ON orbity.content_campaigns
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS
ALTER TABLE orbity.content_campaigns ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "content_campaigns_select_own_org" ON orbity.content_campaigns;
CREATE POLICY "content_campaigns_select_own_org" ON orbity.content_campaigns
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_campaigns_insert_own_org" ON orbity.content_campaigns;
CREATE POLICY "content_campaigns_insert_own_org" ON orbity.content_campaigns
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_campaigns_update_own_org" ON orbity.content_campaigns;
CREATE POLICY "content_campaigns_update_own_org" ON orbity.content_campaigns
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_campaigns_delete_own_org" ON orbity.content_campaigns;
CREATE POLICY "content_campaigns_delete_own_org" ON orbity.content_campaigns
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_campaigns_service_role_all" ON orbity.content_campaigns;
CREATE POLICY "content_campaigns_service_role_all" ON orbity.content_campaigns
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. content_posts — individual scheduled social posts
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.content_posts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    campaign_id      UUID REFERENCES orbity.content_campaigns(id) ON DELETE SET NULL,
    client_id        UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    platform         TEXT NOT NULL
                         CHECK (platform IN ('instagram', 'facebook', 'tiktok', 'linkedin', 'twitter')),
    caption          TEXT,
    hashtags         TEXT,
    scheduled_for    TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'pending_approval', 'approved', 'revision', 'published')),
    assignee_user_id UUID,   -- FK → auth.users — not enforced here
    media_url        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS content_posts_org_id_idx
    ON orbity.content_posts (org_id);
CREATE INDEX IF NOT EXISTS content_posts_campaign_idx
    ON orbity.content_posts (org_id, campaign_id);
CREATE INDEX IF NOT EXISTS content_posts_client_idx
    ON orbity.content_posts (org_id, client_id);
CREATE INDEX IF NOT EXISTS content_posts_status_idx
    ON orbity.content_posts (org_id, status);
CREATE INDEX IF NOT EXISTS content_posts_scheduled_idx
    ON orbity.content_posts (org_id, scheduled_for);

DROP TRIGGER IF EXISTS trg_content_posts_updated_at ON orbity.content_posts;
CREATE TRIGGER trg_content_posts_updated_at
    BEFORE UPDATE ON orbity.content_posts
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS
ALTER TABLE orbity.content_posts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "content_posts_select_own_org" ON orbity.content_posts;
CREATE POLICY "content_posts_select_own_org" ON orbity.content_posts
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_posts_insert_own_org" ON orbity.content_posts;
CREATE POLICY "content_posts_insert_own_org" ON orbity.content_posts
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_posts_update_own_org" ON orbity.content_posts;
CREATE POLICY "content_posts_update_own_org" ON orbity.content_posts
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_posts_delete_own_org" ON orbity.content_posts;
CREATE POLICY "content_posts_delete_own_org" ON orbity.content_posts
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_posts_service_role_all" ON orbity.content_posts;
CREATE POLICY "content_posts_service_role_all" ON orbity.content_posts
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 3. post_approvals — token-gated client approval workflow
--
-- public_token: the shareable URL token sent to the client. It is uuid-typed
-- with a UNIQUE index so the lookup is fast and collision-resistant.
-- The token IS the authorization for the public approve endpoint — no JWT needed.
-- Expiry is enforced server-side (expires_at column).
--
-- The public approve path uses the service_role (admin) client to bypass RLS
-- for the UPDATE — mirroring exactly how capture_router writes leads. The
-- server validates token existence + expiry + not-already-decided before writing.
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.post_approvals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    post_id         UUID NOT NULL REFERENCES orbity.content_posts(id) ON DELETE CASCADE,
    public_token    UUID NOT NULL DEFAULT gen_random_uuid(),
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'approved', 'revision')),
    client_feedback TEXT,
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    decided_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The unique index on public_token is what makes the public token lookup correct.
CREATE UNIQUE INDEX IF NOT EXISTS post_approvals_token_ux
    ON orbity.post_approvals (public_token);
CREATE INDEX IF NOT EXISTS post_approvals_org_id_idx
    ON orbity.post_approvals (org_id);
CREATE INDEX IF NOT EXISTS post_approvals_post_id_idx
    ON orbity.post_approvals (post_id);

DROP TRIGGER IF EXISTS trg_post_approvals_updated_at ON orbity.post_approvals;
CREATE TRIGGER trg_post_approvals_updated_at
    BEFORE UPDATE ON orbity.post_approvals
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

-- RLS
ALTER TABLE orbity.post_approvals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "post_approvals_select_own_org" ON orbity.post_approvals;
CREATE POLICY "post_approvals_select_own_org" ON orbity.post_approvals
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "post_approvals_insert_own_org" ON orbity.post_approvals;
CREATE POLICY "post_approvals_insert_own_org" ON orbity.post_approvals
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "post_approvals_update_own_org" ON orbity.post_approvals;
CREATE POLICY "post_approvals_update_own_org" ON orbity.post_approvals
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "post_approvals_delete_own_org" ON orbity.post_approvals;
CREATE POLICY "post_approvals_delete_own_org" ON orbity.post_approvals
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- service_role bypass: used by the public approve endpoint (token-gated,
-- no JWT) to read the approval row and write the decision back.
DROP POLICY IF EXISTS "post_approvals_service_role_all" ON orbity.post_approvals;
CREATE POLICY "post_approvals_service_role_all" ON orbity.post_approvals
    FOR ALL TO service_role USING (true) WITH CHECK (true);
