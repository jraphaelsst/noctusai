-- ============================================================================
-- 010_anon_grant_lockdown.sql — Academia de Reciclagem (academia_de_reciclagem)
--
-- Closes the schema-wide `anon` exposure inherited from
-- `001_academia-de-reciclagem.sql` (via the seed template, before the
-- 2026-09-20 fix in `templates/product-seed/backend/migrations/001_seed.sql`):
--
--   GRANT ALL ON ALL TABLES IN SCHEMA academia_de_reciclagem TO anon, authenticated, service_role;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA academia_de_reciclagem GRANT ALL ON TABLES TO anon, ...;
--
-- That default let the unauthenticated `anon` PostgREST role read AND write
-- every table in this schema by default — including any table not yet
-- covered by an RLS policy, or created outside a migration file entirely
-- (the exact shape that exposed 4 out-of-band backup tables in the live
-- `social_wiring` schema on 2026-09-20; see
-- `KB § PATTERNS/backend/database-rls.md`).
--
-- AUDITED for anon exceptions before writing this file (grepped every
-- `products/academia-de-reciclagem/backend/migrations/*.sql` for `TO anon`,
-- `FOR ... anon`, and TO-less/PUBLIC-role policies). Findings:
--   * `status_pagina.todos_veem_producao` (001) is a deliberate TO-less
--     (PUBLIC, anon included) SELECT policy — page-visibility flags, no
--     PII. Re-granted explicitly below.
--   * `kb_revisions` (007) already has `FOR SELECT TO authenticated` +
--     `service_role_bypass`; anon has no matching RLS policy, so this
--     REVOKE only removes a grant RLS was already blocking at the row
--     level. No re-grant needed.
--   * Every other RLS policy in this schema is `TO authenticated` or
--     `TO service_role`, or the table has RLS enabled with zero policies
--     (implicit deny). REVOKE-only is safe here.
--
-- Forward-only + idempotent (REVOKE/GRANT are safe to replay whether or
-- not this migration already ran against a given database).
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA academia_de_reciclagem FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA academia_de_reciclagem REVOKE ALL ON TABLES FROM anon;

-- `todos_veem_producao` (001_academia-de-reciclagem.sql) is a deliberate
-- PUBLIC-role SELECT policy — anon needs a table-level grant to actually
-- see the rows it allows now that the schema-wide grant above is gone.
GRANT SELECT ON academia_de_reciclagem.status_pagina TO anon;
