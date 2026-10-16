-- ============================================================================
-- Migration 020 — Content plans: monthly planning with ordered items
--
-- WHY (owner request 2026-10-16: parity with the production Orbity planner):
--   011 gave the agency campaigns -> posts -> client approval, but nothing to
--   PLAN a month before the posts exist. This adds the planning layer:
--     content_plans       one plan per client per month (manual or AI-assisted)
--     content_plan_items  the ordered contents of a plan
--
-- HOW PLANS RELATE TO THE EXISTING FLOW (reuse, do not duplicate):
--   * plan.campaign_id  -> optional link to content_campaigns (same month /
--     client). A plan is the PLAN; the campaign stays the editorial container.
--   * item.task_id      -> the production task spawned from the item
--     (tasks table, 007). ON DELETE SET NULL keeps the item if the task goes.
--   * item.post_id      -> the content_posts row (011) the item was promoted
--     to, which then rides the unchanged draft -> pending_approval ->
--     approved/revision -> published + post_approvals/public-token flow.
--   Items never carry approval state themselves.
--
-- Item statuses: planned | task_pending | task_created | in_progress | published |
--   discarded. 'task_pending' is the transient CLAIM held while a task is being
--   created (compare-and-set in the service: only the caller that flips the row
--   wins and creates the task, so concurrent calls can never double-create).
--   Deleting an item that already has a task is a SOFT delete (-> discarded,
--   task kept); otherwise the row is hard-deleted (enforced in the service).
--
-- RLS: org-scoped via public.current_org_id() exactly like 011; service_role
-- bypass policy; no anon grant (016 default-privileges lockdown applies).
-- IDEMPOTENT: IF NOT EXISTS / DROP ... IF EXISTS.
-- ============================================================================

SET search_path = orbity, public;


-- ============================================================================
-- 1. content_plans
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.content_plans (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    client_id        UUID REFERENCES orbity.clients(id) ON DELETE SET NULL,
    campaign_id      UUID REFERENCES orbity.content_campaigns(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    month            TEXT NOT NULL CHECK (month ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    strategy_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('draft', 'active')),
    creation_mode    TEXT NOT NULL DEFAULT 'manual'
                         CHECK (creation_mode IN ('ai', 'manual')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS content_plans_org_id_idx
    ON orbity.content_plans (org_id);
CREATE INDEX IF NOT EXISTS content_plans_org_client_idx
    ON orbity.content_plans (org_id, client_id);
CREATE INDEX IF NOT EXISTS content_plans_org_month_idx
    ON orbity.content_plans (org_id, month);

DROP TRIGGER IF EXISTS trg_content_plans_updated_at ON orbity.content_plans;
CREATE TRIGGER trg_content_plans_updated_at
    BEFORE UPDATE ON orbity.content_plans
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.content_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "content_plans_select_own_org" ON orbity.content_plans;
CREATE POLICY "content_plans_select_own_org" ON orbity.content_plans
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plans_insert_own_org" ON orbity.content_plans;
CREATE POLICY "content_plans_insert_own_org" ON orbity.content_plans
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plans_update_own_org" ON orbity.content_plans;
CREATE POLICY "content_plans_update_own_org" ON orbity.content_plans
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plans_delete_own_org" ON orbity.content_plans;
CREATE POLICY "content_plans_delete_own_org" ON orbity.content_plans
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plans_service_role_all" ON orbity.content_plans;
CREATE POLICY "content_plans_service_role_all" ON orbity.content_plans
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. content_plan_items
-- ============================================================================

CREATE TABLE IF NOT EXISTS orbity.content_plan_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    plan_id         UUID NOT NULL REFERENCES orbity.content_plans(id) ON DELETE CASCADE,
    order_position  INTEGER NOT NULL DEFAULT 0,
    title           TEXT NOT NULL,
    description     TEXT,
    format          TEXT,
    platform        TEXT
                        CHECK (platform IS NULL OR platform IN
                               ('instagram', 'facebook', 'tiktok', 'linkedin', 'twitter')),
    post_date       DATE,
    due_date        DATE,
    caption         TEXT,
    reference_notes TEXT,
    status          TEXT NOT NULL DEFAULT 'planned'
                        CHECK (status IN ('planned', 'task_pending', 'task_created',
                                          'in_progress', 'published', 'discarded')),
    task_id         UUID REFERENCES orbity.tasks(id) ON DELETE SET NULL,
    post_id         UUID REFERENCES orbity.content_posts(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS content_plan_items_org_id_idx
    ON orbity.content_plan_items (org_id);
CREATE INDEX IF NOT EXISTS content_plan_items_plan_order_idx
    ON orbity.content_plan_items (plan_id, order_position);
CREATE INDEX IF NOT EXISTS content_plan_items_task_idx
    ON orbity.content_plan_items (task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS content_plan_items_post_idx
    ON orbity.content_plan_items (post_id) WHERE post_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_content_plan_items_updated_at ON orbity.content_plan_items;
CREATE TRIGGER trg_content_plan_items_updated_at
    BEFORE UPDATE ON orbity.content_plan_items
    FOR EACH ROW EXECUTE FUNCTION orbity.set_updated_at();

ALTER TABLE orbity.content_plan_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "content_plan_items_select_own_org" ON orbity.content_plan_items;
CREATE POLICY "content_plan_items_select_own_org" ON orbity.content_plan_items
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plan_items_insert_own_org" ON orbity.content_plan_items;
CREATE POLICY "content_plan_items_insert_own_org" ON orbity.content_plan_items
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plan_items_update_own_org" ON orbity.content_plan_items;
CREATE POLICY "content_plan_items_update_own_org" ON orbity.content_plan_items
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plan_items_delete_own_org" ON orbity.content_plan_items;
CREATE POLICY "content_plan_items_delete_own_org" ON orbity.content_plan_items
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "content_plan_items_service_role_all" ON orbity.content_plan_items;
CREATE POLICY "content_plan_items_service_role_all" ON orbity.content_plan_items
    FOR ALL TO service_role USING (true) WITH CHECK (true);
