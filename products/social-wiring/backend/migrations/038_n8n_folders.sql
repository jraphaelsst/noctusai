-- 038_n8n_folders.sql — operator-built folder tree for the /n8n workflows page.
--
-- Context: n8n's native folder concept lives inside license-gated "projects"
-- (`GET /projects` → 403 on this instance) — we cannot rely on n8n's own
-- organization. The tree below is OUR metadata, in OUR schema. Workflows
-- themselves are NOT stored here — they live in n8n and are fetched live via
-- the n8n API at request time. We store only the tree shape and each
-- workflow's placement in it.
--
-- An "account" is a row in social_wiring.integration_accounts (provider
-- 'n8n', already CHECK-allowed since 005_integration_accounts.sql), one per
-- client, org-scoped by RLS.
--
-- Design notes (preserve this intent — do not re-derive):
--   • n8n_workflow_placement is keyed (account_id, workflow_id): a workflow
--     tagged for two different client accounts appears independently in
--     each account's tree. No cross-account conflict by construction.
--   • n8n_folders.parent_id ON DELETE CASCADE — deleting a folder removes
--     its subfolders.
--   • n8n_workflow_placement.folder_id ON DELETE SET NULL — deleting a
--     folder drops its workflows to the tree root; it NEVER deletes a
--     workflow's placement row.
--   • workflow_id is TEXT, never UUID — n8n workflow ids are opaque strings
--     (e.g. 'dKXJgslv7_N4w9v1fDqUe'), not UUIDs.
--   • Cycle prevention (reparenting a folder into its own descendant) is
--     enforced in the SERVICE layer, not by a SQL CHECK — a CHECK cannot
--     express a recursive-ancestry predicate.
--
-- RLS: org-scoped via public.current_org_id() (defined in
-- 011_rls_current_org_id.sql — PREREQUISITE). authenticated gets SELECT
-- only; service_role gets ALL (backend writes — including the cycle-check —
-- go through the admin client). Mirrors 013_mailchimp_connections.sql.
--
-- Sibling-name dedup, root included: SQL's UNIQUE treats each NULL as
-- distinct, so UNIQUE (account_id, parent_id, name) alone would NOT stop
-- two root-level (parent_id IS NULL) folders sharing a name. A second,
-- PARTIAL unique index closes that gap for the root case specifically —
-- see uq_sw_n8n_folders_root_name below. Together the two indexes give
-- uniform "no two same-named siblings" at every depth, exactly as intended.
--
-- Forward-only + idempotent. Apply to the noctusai Supabase
-- (social_wiring schema) at deploy.

SET search_path = social_wiring, public;

-- ── n8n_folders — the operator-built tree ──────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.n8n_folders (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL,                    -- RLS anchor (denormalized,
                                                   -- set from account_id's org
                                                   -- at write time; mirrors
                                                   -- mc_/sched_ tables)
    account_id UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    parent_id  UUID
        REFERENCES social_wiring.n8n_folders(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    position   INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, parent_id, name)
);

-- Root-level sibling-name dedup. The table UNIQUE constraint above already
-- covers non-null parent_id (ordinary subfolder siblings) via standard
-- b-tree uniqueness; it does NOT cover parent_id IS NULL because SQL
-- treats every NULL as distinct from every other NULL. This PARTIAL index
-- covers exactly that remaining case — the two constructs are disjoint by
-- WHERE clause, neither shadows nor duplicates the other's job.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_n8n_folders_root_name
    ON social_wiring.n8n_folders (account_id, name)
    WHERE parent_id IS NULL;

ALTER TABLE social_wiring.n8n_folders ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "n8n_folders_select_own_org" ON social_wiring.n8n_folders;
CREATE POLICY "n8n_folders_select_own_org" ON social_wiring.n8n_folders
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "n8n_folders_service_role" ON social_wiring.n8n_folders;
CREATE POLICY "n8n_folders_service_role" ON social_wiring.n8n_folders
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Supports: list all folders for an account (the tree-fetch query).
CREATE INDEX IF NOT EXISTS idx_sw_n8n_folders_account_id
    ON social_wiring.n8n_folders (account_id);

-- Supports: fetch direct children of a folder (tree render, cascade-delete
-- planning by the service layer).
CREATE INDEX IF NOT EXISTS idx_sw_n8n_folders_parent_id
    ON social_wiring.n8n_folders (parent_id);

CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_n8n_folders()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = social_wiring, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS set_updated_at_n8n_folders ON social_wiring.n8n_folders;
CREATE TRIGGER set_updated_at_n8n_folders
    BEFORE UPDATE ON social_wiring.n8n_folders
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_n8n_folders();


-- ── n8n_workflow_placement — where each n8n workflow sits in the tree ──────
-- No row here == workflow lives at the tree root for that account. We never
-- store the workflow itself (name/nodes/etc.) — that stays live in n8n.
CREATE TABLE IF NOT EXISTS social_wiring.n8n_workflow_placement (
    org_id      UUID NOT NULL,                   -- RLS anchor, see above
    account_id  UUID NOT NULL
        REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE,
    workflow_id TEXT NOT NULL,                    -- n8n's opaque workflow id
    folder_id   UUID
        REFERENCES social_wiring.n8n_folders(id) ON DELETE SET NULL,
    PRIMARY KEY (account_id, workflow_id)
);

ALTER TABLE social_wiring.n8n_workflow_placement ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "n8n_workflow_placement_select_own_org" ON social_wiring.n8n_workflow_placement;
CREATE POLICY "n8n_workflow_placement_select_own_org" ON social_wiring.n8n_workflow_placement
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "n8n_workflow_placement_service_role" ON social_wiring.n8n_workflow_placement;
CREATE POLICY "n8n_workflow_placement_service_role" ON social_wiring.n8n_workflow_placement
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Supports: list all placements for an account (join against the live n8n
-- workflow list). The PRIMARY KEY (account_id, workflow_id) already leads
-- with account_id, so this is covered by the PK index — no separate index
-- needed for that query shape.

-- Supports: list workflows currently inside a given folder (folder-content
-- view; also useful when reparenting a folder's contents).
CREATE INDEX IF NOT EXISTS idx_sw_n8n_workflow_placement_folder_id
    ON social_wiring.n8n_workflow_placement (folder_id);
