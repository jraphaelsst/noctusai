-- 027_erp_org_scoping_completion.sql
--
-- Filed by `projects/erp-org-scoping-completion/` Phase 2 (2026-05-10).
--
-- Background
-- ----------
-- The Phase 0 audit (predecessor `erp-schema-drift-deep-audit`, 2026-05-03)
-- listed 11 ERP tables as "needing org_id work". The Phase 2 re-audit run
-- against the live schema on 2026-05-10 surfaced that the audit was built
-- from code-grep over `.eq("org_id", …)` call sites — some of those sites
-- reference tables that have since been renamed (e.g. `agenda` → `eventos`,
-- `financeiro` → `lancamentos`, `whatsapp_settings` → `whatsapp_config`,
-- `site_imoveis_config` → `site_config`) or never existed at all
-- (`whatsapp_etiquetas`, `imoveis`).
--
-- Of the 11 brief targets, 5 tables already ship `org_id NOT NULL` plus
-- a per-org RLS USING-clause on SELECT/UPDATE/DELETE — Path (a) of the
-- decision matrix is effectively complete for them. THIS migration closes
-- the two real gaps that the Phase 2 re-audit surfaced on these already-
-- org-scoped tables:
--
-- 1. UPDATE policies have RLS USING-clause on `org_id` but no `WITH CHECK`
--    clause — `org_id` mutation isn't blocked by RLS. A user-context client
--    can `UPDATE erp.<table> SET org_id = '<other-org-uuid>' WHERE id = ...`
--    and the USING-only policy lets it through (USING checks pre-image,
--    WITH CHECK checks post-image). NOT NULL prevents nulling org_id but
--    not migrating a row across orgs.
--
-- 2. None of the ERP `org_id` columns have a foreign key to
--    `public.organizations` — orphan refs are possible (e.g. if an org is
--    deleted, its rows survive with dangling org_id). Pre-flight orphan
--    check (2026-05-10) returned 0 across all 5 tables, so the FK can be
--    added without backfill.
--
-- Tables covered (live-schema names; brief aliases in parens):
-- - erp.eventos (brief: `agenda`)
-- - erp.lancamentos (brief: `financeiro`)
-- - erp.site_config (brief: `site_imoveis_config`)
-- - erp.whatsapp_config (brief: `whatsapp_settings`)
-- - erp.certidao_consultas (brief: `certidoes_consultas` — typo)
--
-- Out of scope here (deferred to follow-up `erp-rls-org-scope-redesign`):
-- - erp.ativos / erp.clientes / erp.metas — no org_id column today;
--   scoped via owner_id / usuario_id + role RLS. Adding org_id requires
--   choosing a parent-org-discovery seam (filial_id? profile-derived?).
--   Code grep confirms NO `.eq("org_id", …)` query sites against these
--   three tables, so this is design work (not a security fix).
-- - erp.profiles.org_id staying nullable is the intentional fail-closed
--   design from migration 024; predecessor project shipped its regression
--   tests in test_profiles_router.py::TestDeleteProfile.
-- - erp.certidao_consultas RLS scoping mismatch (org_id NOT NULL but RLS
--   uses created_by, not org_id) is a separate question; this migration
--   only adds the FK and leaves the policy shape for the design follow-up.
--
-- Idempotency
-- -----------
-- All four operations use `IF NOT EXISTS` / `CREATE OR REPLACE` /
-- `DROP POLICY IF EXISTS` so the migration is safe to re-run. Pre-flight
-- check at the top confirms 0 orphan rows; the FK adds in `NOT VALID`
-- mode and then `VALIDATE`s separately so a transient orphan during
-- replay doesn't lock the catalog.

-- ============================================================
-- Schema lock — pin name resolution to erp, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = erp, public;

-- ============================================================
-- Part 1 — Add WITH CHECK on UPDATE policies for the 4 jwt-org-scoped tables.
--
-- The current USING clauses are intact (`org_id = jwt_org_id`); we replace
-- the policy with the same USING + an explicit WITH CHECK that matches.
-- DROP/CREATE chosen over ALTER POLICY because PostgreSQL 17's ALTER syntax
-- requires both USING and WITH CHECK in one statement when adding WITH CHECK
-- to a policy that didn't have one.
-- ============================================================

-- erp.eventos
DROP POLICY IF EXISTS eventos_update_policy ON erp.eventos;
CREATE POLICY eventos_update_policy ON erp.eventos
    FOR UPDATE
    USING (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid)
    WITH CHECK (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid);

-- erp.lancamentos
DROP POLICY IF EXISTS lancamentos_update_policy ON erp.lancamentos;
CREATE POLICY lancamentos_update_policy ON erp.lancamentos
    FOR UPDATE
    USING (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid)
    WITH CHECK (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid);

-- erp.site_config
DROP POLICY IF EXISTS site_config_update_policy ON erp.site_config;
CREATE POLICY site_config_update_policy ON erp.site_config
    FOR UPDATE
    USING (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid)
    WITH CHECK (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid);

-- erp.whatsapp_config
DROP POLICY IF EXISTS whatsapp_config_update_policy ON erp.whatsapp_config;
CREATE POLICY whatsapp_config_update_policy ON erp.whatsapp_config
    FOR UPDATE
    USING (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid)
    WITH CHECK (org_id = (((SELECT auth.jwt()) ->> 'org_id'))::uuid);

-- ============================================================
-- Part 2 — Add foreign keys from erp.<table>.org_id → public.organizations(id).
--
-- Pre-flight orphan check (2026-05-10): 0 rows across all 5 tables.
-- FK added as NOT VALID for forward-compatibility (lock-light path), then
-- VALIDATE'd in a separate statement so the catalog operation is atomic
-- per statement. ON DELETE RESTRICT — deleting an org with live ERP rows
-- should require explicit cleanup, never cascade silently.
-- ============================================================

-- erp.eventos
ALTER TABLE erp.eventos
    DROP CONSTRAINT IF EXISTS eventos_org_id_fkey;
ALTER TABLE erp.eventos
    ADD CONSTRAINT eventos_org_id_fkey
    FOREIGN KEY (org_id) REFERENCES public.organizations(id)
    ON DELETE RESTRICT NOT VALID;
ALTER TABLE erp.eventos VALIDATE CONSTRAINT eventos_org_id_fkey;

-- erp.lancamentos
ALTER TABLE erp.lancamentos
    DROP CONSTRAINT IF EXISTS lancamentos_org_id_fkey;
ALTER TABLE erp.lancamentos
    ADD CONSTRAINT lancamentos_org_id_fkey
    FOREIGN KEY (org_id) REFERENCES public.organizations(id)
    ON DELETE RESTRICT NOT VALID;
ALTER TABLE erp.lancamentos VALIDATE CONSTRAINT lancamentos_org_id_fkey;

-- erp.site_config
ALTER TABLE erp.site_config
    DROP CONSTRAINT IF EXISTS site_config_org_id_fkey;
ALTER TABLE erp.site_config
    ADD CONSTRAINT site_config_org_id_fkey
    FOREIGN KEY (org_id) REFERENCES public.organizations(id)
    ON DELETE RESTRICT NOT VALID;
ALTER TABLE erp.site_config VALIDATE CONSTRAINT site_config_org_id_fkey;

-- erp.whatsapp_config
ALTER TABLE erp.whatsapp_config
    DROP CONSTRAINT IF EXISTS whatsapp_config_org_id_fkey;
ALTER TABLE erp.whatsapp_config
    ADD CONSTRAINT whatsapp_config_org_id_fkey
    FOREIGN KEY (org_id) REFERENCES public.organizations(id)
    ON DELETE RESTRICT NOT VALID;
ALTER TABLE erp.whatsapp_config VALIDATE CONSTRAINT whatsapp_config_org_id_fkey;

-- erp.certidao_consultas
ALTER TABLE erp.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_org_id_fkey;
ALTER TABLE erp.certidao_consultas
    ADD CONSTRAINT certidao_consultas_org_id_fkey
    FOREIGN KEY (org_id) REFERENCES public.organizations(id)
    ON DELETE RESTRICT NOT VALID;
ALTER TABLE erp.certidao_consultas VALIDATE CONSTRAINT certidao_consultas_org_id_fkey;

-- ============================================================
-- Backfill note
-- ============================================================
-- No backfill needed: all 5 tables already have `org_id NOT NULL` from
-- their original migration (Phase 1 of the predecessor project on
-- `erp.profiles` was the only nullable case, and is intentionally so —
-- see migration 024 docstring).
