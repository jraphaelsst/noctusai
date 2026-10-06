# Migration-SQL security gates — SECURITY DEFINER EXECUTE revoke + typed empty arrays

Two static keepers over migration SQL, born from the 2026-10-06 security sweep.
Both are the commit-time half of a contract whose runtime half already existed
(or failed on prod). Gate and mechanism ship together
(`KB § PATTERNS/common/gate-methodology-sync.md`).

## 1. SECURITY DEFINER functions must revoke caller EXECUTE

Postgres grants `EXECUTE` on every new function to `PUBLIC`. A `SECURITY DEFINER`
function runs with its OWNER's rights (RLS bypassed), so unless the same
migration revokes it, `anon`/`authenticated` can call it through PostgREST
`/rpc/<fn>` — a data-exposure hole.

**Mechanism (compliance by construction).** Every migration that creates one adds,
in the SAME file:
`REVOKE EXECUTE ON FUNCTION <schema>.<fn>(<args>) FROM PUBLIC, anon, authenticated;`
then `GRANT EXECUTE ... TO service_role` where a caller needs it. A dynamic
`DO` loop that `format()`s a REVOKE (the `*_secdef_execute_lockdown` migrations)
also satisfies the keeper.

**Gate.** Keeper `check_secdef_migration_revokes_execute`
(`--check-secdef-migration-revokes-execute`; pre-commit 6g3, blocking; also in
`check_all_products`, so the CI compliance-baseline gate runs it). Scans every
`migrations/*.sql` under `products/` (ALL products, not active-only: an asleep
product's migrations still hit the shared DB), `seed/` and `templates/`.
Comments are stripped before matching, so a commented-out REVOKE does not count.

**Legacy baseline.** 225 pre-keeper functions are recorded as `relpath::function`
in `mcp/noctusai/tests/secdef_migration_baseline.json`. Migrations are immutable,
so the baseline never grows; new files are enforced from day one. Their LIVE
state is covered by the runtime probe below.

**Runtime twin.** `verify_db_guards` probe
`secdef.execute.no_caller_executable_outside_rls_helpers` (a `predeploy_check`
leg) asks the live DB: is any SECURITY DEFINER function executable by
anon/authenticated that is NOT referenced by a `pg_policy`?

### The RLS-helper rule (allowlist semantics)

The ONLY legitimate caller-executable SECURITY DEFINER functions are RLS helpers —
functions a policy expression calls (the caller's role evaluates the policy, so it
needs EXECUTE). The probe derives that set from `pg_policy` usage at probe time.
Therefore:

- A migration `-- secdef-execute-ok: rls-helper <why>` escape MUST name a function
  that a policy actually references. A hard-coded keep-list in a lockdown migration
  must equal the probe's rule, not a guess (2026-10-06: core 061 kept
  `current_user_id()` / `is_customer()` as "helpers" although no policy used them;
  core 064 revoked them). Prefer deriving the keep-list inside the migration from
  `pg_policy` (as the lockdown DO-blocks do) over listing names.
- No policy reference ⇒ no escape: revoke it.

## 2. Untyped empty array literals

`ARRAY[]` with no cast fails at apply time with `42P18 could not determine data
type of empty array`; it passes review and fails on prod. Always `ARRAY[]::text[]`
(or the correct element type).

**Gate.** Keeper `check_migration_untyped_empty_array`
(`--check-migration-untyped-empty-array`; pre-commit 6g3, blocking; in
`check_all_products`). Every migration file must be clean; no baseline.

## Related gates from the same sweep

- `check_no_metadata_authz` — org/role only from `public.noctus_users`
  (`KB § PATTERNS/backend/no-metadata-authz.md`). Now ALSO in `check_all_products`
  (CI); scan roots are `seed/**` + catalog-derived active products
  (`_active_product_dirs`), never hand-listed.
- Behaviour fixes carry CI-gated regression tests, not keepers: invite acceptance
  bound to the invited email (`products/core/backend/tests/routers/test_team_router.py`),
  SSO tokens single-use via `jti` (`products/core/backend/tests/routers/test_sso_router.py`,
  `seed/lib/backend/tests/test_auth.py`). Core runs in the CI product matrix; the
  seed backend runs in the `seed-backend-tests` job.

## Not done (deliberately)

A write-time harness-mod warning (PreToolUse-style) for `SECURITY DEFINER` without
REVOKE / `user_metadata` org-role reads. The mods framework only renders what a
canonical Python guard emits (`[noc-guard:<name>]` marker); a warning needs a new
Python guard script plus marker plumbing first
(`KB § PATTERNS/common/harness-mods.md`). The pre-commit keepers already fire with
specific fix text at commit time; revisit only if the keepers become a wall.
