-- ============================================================================
-- 011_anon_grant_lockdown.sql — Agents (agents)
--
-- Closes the schema-wide `anon` exposure inherited from `001_agents.sql`
-- (via the seed template, before the 2026-09-20 fix in
-- `templates/product-seed/backend/migrations/001_seed.sql`):
--
--   GRANT ALL ON ALL TABLES IN SCHEMA agents TO anon, authenticated, service_role;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA agents GRANT ALL ON TABLES TO anon, ...;
--
-- That default let the unauthenticated `anon` PostgREST role read AND write
-- every table in this schema by default — including any table not yet
-- covered by an RLS policy, or created outside a migration file entirely
-- (the exact shape that exposed 4 out-of-band backup tables in the live
-- `social_wiring` schema on 2026-09-20; see
-- `KB § PATTERNS/backend/database-rls.md`).
--
-- AUDITED for anon exceptions before writing this file (grepped every
-- `products/agents/backend/migrations/*.sql` for `TO anon`, `FOR ... anon`,
-- and TO-less/PUBLIC-role policies). Findings:
--   * `status_pagina.todos_veem_producao` (001) is a deliberate TO-less
--     (PUBLIC, anon included) SELECT policy — page-visibility flags, no
--     PII. Re-granted explicitly below.
--   * `session_transcript_entries` (009), `app_integration_config` and
--     `runtime_settings` (010) already carry an explicit
--     `REVOKE ALL ... FROM anon, authenticated` at the per-table level —
--     this schema-wide REVOKE is a no-op restatement for those three,
--     never a widening.
--   * Every other RLS policy in this schema is `TO authenticated` or
--     `TO service_role`. REVOKE-only is safe for the rest.
--
-- Forward-only + idempotent (REVOKE/GRANT are safe to replay whether or
-- not this migration already ran against a given database).
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA agents FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA agents REVOKE ALL ON TABLES FROM anon;

-- `todos_veem_producao` (001_agents.sql) is a deliberate PUBLIC-role
-- SELECT policy — anon needs a table-level grant to actually see the rows
-- it allows now that the schema-wide grant above is gone.
GRANT SELECT ON agents.status_pagina TO anon;
