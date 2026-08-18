-- ============================================================================
-- Migration 059 -- social_wiring: raise the clientes-inactivity platform
-- default from 180 to 365 days.
--
-- `058` shipped `clientes_inactivity_config.threshold_days` with
-- `DEFAULT 180`, matching D16's original ratified number
-- (`project-history/roadmaps/lead-card-hub-2026-08.md` D16). The apply-time
-- measurement recorded in `migrations/APPLIED.md` ("058 -- D16 inactivity")
-- showed what that number actually does against the live ~10 204-cliente
-- base:
--
--   | Threshold | Clientes still active | Swept inactive | % swept |
--   |---:|---:|---:|---:|
--   | 180 days (ratified in 058) | 3 072 | 7 132 | 70% |
--   | 365 days                   | 5 498 | 4 706 | 46% |
--
-- 70% of the board disappearing on the very first scheduled tick is not a
-- number anyone should discover after the fact. The user raised the default
-- to 365 on 2026-08-18, explicitly reversible per-org from the UI
-- (`PUT /api/settings/clientes-inactivity` -- see
-- `app/routers/settings_router.py` + `app/pages/Settings.tsx`'s new
-- "Clientes" tab, both shipped alongside this migration).
--
-- This migration changes ONLY the *default* an org falls back to when it
-- has never configured its own value (`clientes_inactivity_config` has no
-- row for that org_id) -- via `ALTER COLUMN ... SET DEFAULT`, which never
-- touches any EXISTING row. An org that already has a configured row (its
-- own explicit `threshold_days`, including an explicit `0`) is entirely
-- unaffected; this migration changes no data. The matching in-process
-- constant is `app/config.py`'s
-- `clientes_inactivity_threshold_days_default` (also updated to 365,
-- same commit) -- the two must never drift apart, since
-- `clientes_inactivity_service.get_threshold_config` reads the Python
-- constant, not the column default, for an unconfigured org; the column
-- default only matters for a row inserted WITHOUT an explicit
-- `threshold_days` (there is no such write path today, but the column
-- default should still tell the truth about what "unconfigured" means at
-- the schema level).
--
-- `058`'s own DEFAULT 180 is left as authored -- migration files are a
-- historical record of what ran, and `058` genuinely did ship 180. This is
-- a NEW, forward-only, idempotent change on top of it, matching every
-- migration in this product.
--
-- 🔴 MIGRATION FILE ONLY -- not applied to any database by this change.
-- Apply via `noctus.dev.migrate_product` only with explicit tech-lead/user
-- go-ahead, same as every migration in this file's neighbourhood. See
-- `migrations/APPLIED.md`'s header: this product runs against the prod
-- Supabase project dev shares, so applying anything here is a production
-- change and never an agent's decision alone.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.clientes_inactivity_config
    ALTER COLUMN threshold_days SET DEFAULT 365;

COMMENT ON COLUMN social_wiring.clientes_inactivity_config.threshold_days IS
    '0 = sweep explicitly disabled for this org. No row at all = never '
    'configured, sweep falls back to the platform default (365, raised '
    'from 180 in migration 059 -- see this migration''s header for the '
    'live-measurement reasoning). See the header for why these are kept '
    'distinct.';

NOTIFY pgrst, 'reload schema';
