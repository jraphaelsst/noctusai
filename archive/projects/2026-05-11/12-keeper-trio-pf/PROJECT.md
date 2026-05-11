# keeper-trio-pf — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Done (Phase 0/1/2 all ✅)
- **Owner / stakeholders:** joaoraphaelsst · Engineer BBB (Wave 1 child D)
- **Related docs:** `projects/keeper-trio-platform-triage/PROJECT.md`, `projects/keeper-trio-platform-triage/phase-0-triage.md` (§ personal-finance), `seed/lib/backend/noctusai_lib/sql/service_role_bypass.py` (Wave 0 helper, commit `b76c43f`), `mcp/noctusai/tools/noctus/dev/compliance.py § check_admin_endpoint_service_role_bypass`
- **Project slug:** `keeper-trio-pf` (root `projects/<slug>/` — child of the master-tree triage; not a single-product methodology shift, the migration is product-bounded but the detector teach is platform)

---

## 1. Context & Purpose

Wave 1 child D of the keeper-trio platform triage. Smallest child: 1 DEFENSE_IN_DEPTH finding from the platform audit — `products/personal-finance/backend/app/scheduler.py:30` calls `get_admin_client().table("recorrentes")` but `"personal-finance".recorrentes` has no explicit `service_role_bypass` policy. Runtime is fine (service_role JWT bypasses RLS at the connection level + schema-level GRANTs cover DML), but the platform's `check_admin_endpoint_service_role_bypass` keeper detector enforces the explicit per-table policy convention. Ship it.

Predicted size from parent PROJECT.md: "≈5-min fix; could be inlined." Held up — until a Wave 0 detector-regex gap surfaced (see Phase 2).

---

## 2. Confirmed constraints

- **Scope strictness** — 1 table only (`recorrentes`). Symmetric extension to PF's other 15 RLS-enabled tables is suggested by the triage doc ("once you're already in there") but explicitly out-of-brief. *(Captured in findings.md for follow-up.)*
- **Migration vehicle** — new file 009, NOT amending 001 (live DB already past 008; amending 001 would diverge from the live migration log). *(Phase 0 decision option A.)*
- **Helper** — use `noctusai_lib.sql.service_role_bypass(table, schema='"personal-finance"')` from Wave 0 (commit `b76c43f`). Caller wraps the dashed schema per the helper's documented caller-responsibility contract.

---

## 3. Design principles

1. Honor brief scope — single-table migration; defer-with-destination on symmetry.
2. Apply at the root layer — when verification surfaces a detector-regex gap, fix the detector, not the migration.
3. Regression-test-the-detector — every detector teach ships a colocated pinned test.

---

## 3a. Seed-first analysis

1. **Identical contract every product?** YES — every product uses `service_role_bypass` policy convention. The Wave 0 helper formalized it.
2. **Data source product-specific?** YES — the table being protected is PF-scoped.
3. **Placement product-specific?** YES — migration lands in PF's own migrations dir.
4. **Visibility / permission rule uniform?** YES — all products use the same policy shape (`FOR ALL TO service_role USING (true) WITH CHECK (true)`).
5. **Seam exists in seed?** YES — `noctusai_lib.sql.service_role_bypass` (Wave 0).
6. **Default-on?** N/A — opt-in per-table via migration. Future cleanup: auto-emit in `scaffold_migration` when `with_table` is provided.

**Per-product code count this design requires:** 1 line of SQL per table (the `CREATE POLICY` statement). Acceptable — the cross-product helper produces the string; the migration just calls it.

**Phase plan implications:** §6 phases are product-bounded for the migration but touch platform code (detector regex) for the verification gap. Cross-cutting work is captured as a Wave-0-detector-teach amendment, not as per-product copy.

---

## 4. Scope

**In scope:**
- New migration `009_recorrentes_service_role_bypass.sql` applying the explicit policy.
- Apply via Supabase MCP to live DB.
- Phase 2 verification: re-run review → 0 issues.
- Detector-regex teach (surfaced during Phase 2): extend `_SERVICE_ROLE_BYPASS_POLICY_RE` to recognize quoted-dashed-schema prefixes.
- Regression test pinning the dashed-schema case.

**Out of scope (for now — with reason):**
- Adding `service_role_bypass` to PF's other 15 RLS-enabled tables — triage suggested it but explicitly outside the 1-finding brief; captured in findings.md as DRY-N=15 follow-up candidate.

---

## 5. Architecture / Data Model

- **Migration:** `products/personal-finance/backend/migrations/009_recorrentes_service_role_bypass.sql` — single `CREATE POLICY` statement.
- **Detector patch:** `mcp/noctusai/tools/noctus/dev/compliance.py § _SERVICE_ROLE_BYPASS_POLICY_RE` — regex alternation for `"<dashed>".` schema prefix.
- **Test:** `mcp/noctusai/tests/test_compliance_prod.py § TestCheckAdminEndpointServiceRoleBypass.test_dashed_schema_bypass_policy_is_recognized`.

---

## 6. Implementation phases

### Phase 0 — Confirm finding ✅

- [x] Run `noctus.dev.review --product personal-finance` via MCP server: reported 0 issues. **Surprise.**
- [x] Run detector directly against the worktree path: 1 finding (`backend/app/scheduler.py:30 recorrentes`). **MCP server probably points at main-tree path; brief's stated baseline of 1 is correct on the worktree.**
- [x] Verify `"personal-finance".recorrentes` exists in `001_personal_finance.sql:221` + has only `recorrentes_org_scoped` policy (no `service_role_bypass`).
- [x] Decide migration option: A (new file 009) — live DB is past 008, amending 001 would diverge the migration log.

**Improvements:** the MCP-server-vs-worktree path discrepancy is a real gap — when running an engineer inside a worktree, the MCP review tool walks the main-tree path. Engineers may incorrectly read "0 issues" as "Phase 0 already done." Cross-check by running the detector directly. Captured in findings.md.

### Phase 1 — Ship migration ✅

- [x] Generate SQL via `noctusai_lib.sql.service_role_bypass('recorrentes', schema='"personal-finance"')` (caller-wrapped quotes per helper contract).
- [x] Write `009_recorrentes_service_role_bypass.sql` with explanatory header (triage link, defer-with-destination note for the 15 other tables).
- [x] Apply via `mcp__claude_ai_Supabase__apply_migration(project_id="nyplttplcoyiiqjrvtiw", name="009_recorrentes_service_role_bypass")`.
- [x] Verify live policy via `pg_policies`: both `recorrentes_org_scoped` (authenticated) + `service_role_bypass` (service_role) present.

**Improvements:** the Wave 0 helper's `schema` parameter docstring already calls out caller-responsibility for dashed-schema quoting; consider auto-wrapping in a future iteration (helper detects `-` in schema name → wraps + warns). Captured as findings.md DRY note.

### Phase 2 — Verify + close ✅

- [x] Re-run detector: STILL flagged. Initial result misleading — investigation found the regression-detector regex `_SERVICE_ROLE_BYPASS_POLICY_RE` couldn't parse `"personal-finance".recorrentes` (only unquoted-schema prefix matched).
- [x] **In-scope fix at root layer:** extend regex alternation to `(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\.` — supports both quoted-dashed and unquoted forms.
- [x] Add regression test `test_dashed_schema_bypass_policy_is_recognized`.
- [x] Re-run detector: **0 issues** on personal-finance. Cross-product regression check: core/erp/mailing unchanged from triage baselines.
- [x] Run PF backend pytest: 590 passed, 10 skipped, 0 errors, 1 deprecation warning (pre-existing python_multipart starlette warning, unrelated). No regression.
- [x] Run compliance detector tests: 21 passed (was 20 — the new dashed-schema regression test).

**Improvements:** detector-regex gap was a Wave 0 oversight — `b76c43f` shipped the helper assuming the existing detector parsed both quoted + unquoted schema prefixes. Could have been caught at Wave 0 with a dashed-schema fixture test. Captured in findings.md.

---

## 11. Change log

| Date | Phase | Note |
|---|---|---|
| 2026-05-11 | 0 | Confirmed 1 finding on worktree (MCP server reports 0; discrepancy due to main-tree-vs-worktree path). Decided migration option A (new file 009). |
| 2026-05-11 | 1 | Migration 009 written + applied live. `pg_policies` confirms both policies. |
| 2026-05-11 | 2 | Surfaced detector-regex gap; applied root-layer fix; added regression test; final verification 0 issues + 590/0/0 PF tests + 21/21 compliance tests. Closed. |

---

## 12. Verification (final)

- `python -c "compliance.check_admin_endpoint_service_role_bypass(Path('products/personal-finance'))"` → `[]` (was `[recorrentes@scheduler.py:30]`).
- `cd products/personal-finance/backend && pytest -q` → `590 passed, 10 skipped, 1 warning in 6.03s`.
- `cd mcp/noctusai && pytest tests/test_compliance_prod.py -q` → `21 passed in 0.12s`.
- `pg_policies` on `"personal-finance".recorrentes` → `[recorrentes_org_scoped@authenticated, service_role_bypass@service_role]`.
