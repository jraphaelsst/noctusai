-- ============================================================================
-- 009_anon_grant_lockdown.sql — Daily Life (daily_life)
--
-- Closes the schema-wide `anon` exposure inherited from `001_daily_life.sql`
-- (via the seed template, before the 2026-09-20 fix in
-- `templates/product-seed/backend/migrations/001_seed.sql`):
--
--   GRANT ALL ON ALL TABLES IN SCHEMA daily_life TO anon, authenticated, service_role;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life GRANT ALL ON TABLES TO anon, ...;
--
-- That default let the unauthenticated `anon` PostgREST role read AND write
-- every table in this schema by default — including any table not yet
-- covered by an RLS policy, or created outside a migration file entirely
-- (the exact shape that exposed 4 out-of-band backup tables in the live
-- `social_wiring` schema on 2026-09-20; see
-- `KB § PATTERNS/backend/database-rls.md`).
--
-- AUDITED for anon exceptions before writing this file (grepped every
-- `products/daily-life/backend/migrations/*.sql` for `TO anon`,
-- `FOR ... anon`, and TO-less/PUBLIC-role policies). The only deliberate
-- anon-facing surface is `status_pagina.todos_veem_producao` (001) — a
-- TO-less (PUBLIC, anon included) SELECT policy over page-visibility
-- flags, no PII. Re-granted explicitly below. `tool_call_audits` (005) is
-- RLS-enabled with no anon-matching policy (service_role-only by design);
-- every other RLS policy in this schema is `TO authenticated` or
-- `TO service_role`. REVOKE-only is safe for the rest.
--
-- Forward-only + idempotent (REVOKE/GRANT are safe to replay whether or
-- not this migration already ran against a given database).
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA daily_life FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life REVOKE ALL ON TABLES FROM anon;

-- `todos_veem_producao` (001_daily_life.sql) is a deliberate PUBLIC-role
-- SELECT policy — anon needs a table-level grant to actually see the rows
-- it allows now that the schema-wide grant above is gone.
GRANT SELECT ON daily_life.status_pagina TO anon;
