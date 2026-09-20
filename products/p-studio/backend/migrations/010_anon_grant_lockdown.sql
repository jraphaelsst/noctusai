-- ============================================================================
-- 010_anon_grant_lockdown.sql — P Studio (p_studio)
--
-- Closes the schema-wide `anon` exposure inherited from
-- `001_p_studio_schema.sql` (built outside noc, copied from the seed's
-- OLD shape before the 2026-09-20 fix in
-- `templates/product-seed/backend/migrations/001_seed.sql`):
--
--   GRANT USAGE ON SCHEMA p_studio TO anon, authenticated, service_role;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA p_studio GRANT ALL ON TABLES TO anon, ...;
--
-- Every table in `001_p_studio_schema.sql` was created AFTER that
-- `ALTER DEFAULT PRIVILEGES`, so each one inherited `ALL` for `anon` at
-- CREATE TABLE time exactly as if a blanket
-- `GRANT ALL ON ALL TABLES IN SCHEMA p_studio TO anon, ...` had run. That
-- let the unauthenticated `anon` PostgREST role read AND write every table
-- in this schema by default — including any table not yet covered by an
-- RLS policy (the exact shape that exposed 4 out-of-band backup tables in
-- the live `social_wiring` schema on 2026-09-20; see
-- `KB § PATTERNS/backend/database-rls.md`).
--
-- AUDITED for anon exceptions before writing this file (grepped every
-- `products/p-studio/backend/migrations/*.sql` for `TO anon`,
-- `FOR ... anon`, and TO-less/PUBLIC-role policies). The only deliberate
-- anon-facing surface is `status_pagina_select_producao` (001) — a
-- TO-less (PUBLIC, anon included) SELECT policy over page-visibility
-- flags, no PII (its own migration 005 notes the P Studio frontend does
-- not even read `status_pagina` yet — this is the cheap-to-fix-now half of
-- a two-half contract). Re-granted explicitly below. Every other RLS
-- policy in this schema is `TO authenticated`. REVOKE-only is safe for
-- the rest.
--
-- Forward-only + idempotent (REVOKE/GRANT are safe to replay whether or
-- not this migration already ran against a given database).
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA p_studio FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA p_studio REVOKE ALL ON TABLES FROM anon;

-- `status_pagina_select_producao` (001_p_studio_schema.sql) is a
-- deliberate PUBLIC-role SELECT policy — anon needs a table-level grant
-- to actually see the rows it allows now that the schema-wide default
-- above is gone.
GRANT SELECT ON p_studio.status_pagina TO anon;
