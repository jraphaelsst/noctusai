-- =====================================================================
-- Sample migration — demonstrates `noctusai_lib.sql` helper composition
-- =====================================================================
-- Authored by the seed-migration-prelude project (2026-05-10) as a
-- reference fixture: this file shows what a fresh migration looks like
-- when the consumer composes `prelude(...)` + `updated_at_trigger(...)`
-- directly (no scaffold tool involvement). Used by both human authors
-- as a copy-paste reference and as a regression fixture in
-- test_sql_helpers.py.
--
-- Note: existing product migrations stay verbatim per the
-- "MCP migrations mirror the file" rule — the helpers are for FUTURE
-- migrations only (high churn risk to rewrite the past).
-- =====================================================================

-- ============================================================
-- Schema lock — pin name resolution to blog, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = blog, public;

-- ----- Schema + tables -----
CREATE SCHEMA IF NOT EXISTS blog;

CREATE TABLE IF NOT EXISTS blog.posts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    body text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS blog.comments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id uuid NOT NULL REFERENCES blog.posts(id) ON DELETE CASCADE,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ----- updated_at auto-touch (function declared once, triggers per table) -----
CREATE OR REPLACE FUNCTION blog.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = blog, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE OR REPLACE TRIGGER set_updated_at_posts
    BEFORE UPDATE ON blog.posts
    FOR EACH ROW EXECUTE FUNCTION blog.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_comments
    BEFORE UPDATE ON blog.comments
    FOR EACH ROW EXECUTE FUNCTION blog.set_updated_at();
