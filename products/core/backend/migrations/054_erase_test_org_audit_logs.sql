-- ============================================================================
-- 054_erase_test_org_audit_logs — a second sanctioned erasure door for
-- audit_logs: category='test' organizations only.
-- ============================================================================
--
-- PROBLEM (found live in prod, 2026-09-23): 053_audit_trail_expansion.sql
-- made `public.audit_logs` append-only — UPDATE always refused, DELETE
-- refused unless `public.purge_expired_audit_logs()` is the caller (only
-- rows past `retention_until`, 400 days). `audit_logs.org_id` is
-- `REFERENCES organizations(id)` with the default action, i.e. FK
-- `ON DELETE NO ACTION`. Put together: an organization that owns even ONE
-- audit_logs row can NEVER be deleted until that row ages past 400 days —
-- there was no sanctioned way to delete an org sooner.
--
-- This bit a real workflow: `products/core/backend/tests/realdb/conftest.py`
-- `test_org` creates throwaway orgs (`category = 'test'`,
-- `slug = 'test-realdb-<hex>'`) against the real (prod) Supabase project and
-- deletes them on teardown, clearing `audit_logs` first with a plain
-- `DELETE ... WHERE org_id = ...` (`_ORG_NO_ACTION_DEPENDENTS`). Once 053
-- landed, that teardown DELETE started failing silently in some runs,
-- leaking `category = 'test'` orgs (and their now-undeletable audit rows)
-- into prod. Fixing the realdb-suite opt-in itself is a separate, parallel
-- effort — out of scope here (do not touch `tests/realdb/`).
--
-- WHAT — `public.erase_test_org_audit_logs(p_org_id uuid) RETURNS int`:
--   * SECURITY DEFINER, service_role-only (REVOKE PUBLIC/anon/authenticated,
--     same lockdown shape as `purge_expired_audit_logs` below it and
--     `agents.erase_compiled_prompts`, 012_agent_studio_definitions.sql).
--   * Refuses (RAISE EXCEPTION 'org_not_erasable_test_org') unless
--     `p_org_id` names an `organizations` row with `category = 'test' AND
--     slug LIKE 'test-realdb-%'` — the exact shape `test_org` stamps. A
--     non-existent org, a real ('normal'-category) org, or a `category =
--     'test'` org that isn't a realdb fixture (some other test harness)
--     ALL refuse. This is deliberately narrower than "any test-category
--     org" — `category = 'test'` alone is not proof the row is disposable
--     scaffolding this specific suite owns.
--   * On a match: sets the SAME transaction-local flag
--     `core.audit_log_purge` the purge function sets (`set_config(...,
--     true)` — transaction-scoped, cleared right after), so
--     `guard_audit_logs_append_only` lets the DELETE through via the
--     identical escape hatch. The trigger itself is UNCHANGED — this is a
--     second caller of the existing door, not a new bypass.
--   * Deletes only `audit_logs` rows for that org; it does not touch
--     `organizations` or any other NO-ACTION FK dependent
--     (`ai_feedback` / `api_keys` / `invitations` / `product_usage` /
--     `roles` / `subscriptions`, per the realdb conftest's own list) — the
--     caller still clears those and the org row itself exactly as today.
--
-- NOT BUILT HERE — real (non-test) organization erasure / LGPD: a customer
-- asking for their org's audit trail to be erased is a distinct, much
-- higher-stakes decision (LGPD Art. 18 erasure vs. Art. 16 retention
-- obligations the trail itself exists to satisfy, who else's audit history
-- references that org, whether "erase" should mean delete-rows or
-- anonymize-in-place). That is an owner-decided design, not a mechanical
-- schema fix, and is deliberately NOT addressed by this migration — only
-- the narrow, structurally-provable "this row is disposable test
-- scaffolding" case is.
--
-- `noctus.dev.verify_db_guards` probes `erase_test_org_audit_logs.
-- refuses_non_test_org` (the function's own guard) and
-- `audit_logs.delete_refused_outside_purge` (053, unchanged — a plain
-- DELETE is still refused) prove the erasure door only opens for what it
-- claims to (KB § PATTERNS/common/methodology-execution-discipline.md § 8).
--
-- Forward-only. No DROP/ALTER of the append-only trigger.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.erase_test_org_audit_logs(p_org_id UUID)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count INT;
    v_is_realdb_test_org BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM public.organizations
        WHERE id = p_org_id
          AND category = 'test'
          AND slug LIKE 'test-realdb-%'
    ) INTO v_is_realdb_test_org;

    IF NOT v_is_realdb_test_org THEN
        RAISE EXCEPTION 'org_not_erasable_test_org' USING ERRCODE = 'P0001';
    END IF;

    PERFORM set_config('core.audit_log_purge', 'on', true);
    DELETE FROM public.audit_logs WHERE org_id = p_org_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    PERFORM set_config('core.audit_log_purge', 'off', true);
    RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION public.erase_test_org_audit_logs(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.erase_test_org_audit_logs(UUID) TO service_role;
