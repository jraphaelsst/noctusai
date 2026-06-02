-- Migration 039: Add org_type and number_of_users to organizations
-- Purpose: Support company-vs-individual org typing with prefixed slugs.
--          Root-fix for the signup journey: these columns are written at
--          account-creation time so every new org carries its type immediately.
--
-- Forward-only (applied once). Safe to run on a live DB — all changes are
-- ADD COLUMN with defaults, followed by a conservative backfill and a slug
-- prefix pass for new orgs going forward (existing slugs are NOT renamed to
-- avoid breaking any FKs or bookmarks).
--
-- Backfill rationale:
--   All existing orgs are set to 'individual' / number_of_users=1 as the
--   safe conservative default. Orgs that are clearly companies (have a cnpj
--   or have nome ending in common legal suffixes) are NOT auto-upgraded here
--   because the data quality is not reliable enough for a destructive
--   assumption. A manual review pass can upgrade specific orgs afterward.

-- 1. Add org_type column with CHECK constraint
ALTER TABLE public.organizations
    ADD COLUMN IF NOT EXISTS org_type TEXT NOT NULL DEFAULT 'individual'
    CHECK (org_type IN ('individual', 'company'));

-- 2. Add number_of_users column with CHECK constraint
ALTER TABLE public.organizations
    ADD COLUMN IF NOT EXISTS number_of_users INTEGER NOT NULL DEFAULT 1
    CHECK (number_of_users >= 1);

-- 3. Backfill: existing rows stay at defaults (individual, 1).
--    Document for reviewers: to upgrade a known company org run:
--      UPDATE public.organizations
--         SET org_type = 'company', number_of_users = <N>
--       WHERE id = '<uuid>';

-- 4. Index for fast org_type queries (e.g. admin dashboards, analytics)
CREATE INDEX IF NOT EXISTS idx_organizations_org_type
    ON public.organizations (org_type);

-- 5. Note on slug prefixes:
--    New orgs receive prefixed slugs ('indv_<base>' / 'comp_<base>') via
--    application logic in auth.py and oauth.py — no DB-level migration of
--    existing slugs, as renaming would break bookmarks and any external
--    references. Existing slug values remain unchanged.
