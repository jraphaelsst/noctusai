# keeper-trio-mailing — Project Document

> Living document — revise phases as we learn. Zero-context reader friendly.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 4 → close (after FF-merge to main by orchestrator)
- **Owner / stakeholders:** Engineer AAA (Wave 1 child C); orchestrator: parent of `projects/keeper-trio-platform-triage/`
- **Related docs:** `projects/keeper-trio-platform-triage/PROJECT.md`, `projects/keeper-trio-platform-triage/phase-0-triage.md`, KB § PATTERNS/database-rls.md, KB § PATTERNS/testing.md
- **Project slug:** `keeper-trio-mailing` (Wave 1 child C of `keeper-trio-platform-triage` master-tree)

---

## 1. Context & Purpose

The keeper review surfaced **18 DEFENSE_IN_DEPTH findings** across the `mailing` product — every admin-client call against `mailing.*` tables flags as missing the named `service_role_bypass` RLS policy. Runtime is fine today: `001_mailing.sql:11-15` grants `ALL` on schema-level + the Supabase `service_role` JWT bypasses RLS at the connection level. But the detector looks for the literal policy *name* (`service_role_bypass`), which therapy adopted as the canonical reference (`001_therapy_platform.sql:846+`). The 18 findings collapse to a **single migration** that adds the explicit per-table policy, matching the canonical shape.

This child has **0 REAL_BUGs** — pure DEFENSE_IN_DEPTH hardening + detector calibration alignment.

---

## 2. Confirmed constraints

- **Triage source** — RR's `phase-0-triage.md` mailing section (lines 92-104). *(All 18 findings are detector-flagged absence of named `service_role_bypass` policy.)*
- **Wave structure** — Wave 1 child C, gated on Wave 0 (`keeper-trio-seed-formalize` shipping the `service_role_bypass(table, schema)` helper at `b76c43f`). *(Helper verified at `noctusai_lib.sql.service_role_bypass`; output matches canonical shape.)*
- **Scope cap** — 18 findings, 6 distinct tables (`sender_domains`, `send_logs`, `contacts`, `campaigns`, `unsubscribes`, `automation_enrollments`). Symmetry recommendation in triage: "consider all RLS-enabled mailing tables for symmetry". *(Applied — all 17 RLS-enabled mailing tables receive the bypass policy in this pass.)*
- **Migration-style decision** — single-001 convention per `KB § PATTERNS/database-rls.md`. *(Decision: amend `001_mailing.sql` in-place + amend `002_ai_outputs.sql` + `003_ai_feedback.sql` for symmetry on the two tables they create; see §3.)*
- **MCP write tools** — pass `worktree_path=` explicitly. *(Per §17.6 worktree-base preamble.)*
- **Write authorization** — explicit §17.6 clause in brief covers `findings.md`, `PROJECT.md`, new migrations under `products/mailing/backend/migrations/`. *(Used.)*

---

## 3. Design principles

1. **One decision closes 18 findings.** A single migration-amendment block adds the canonical `service_role_bypass` policy per table. No code-side change required (admin calls are correct; the gap is policy *naming*).
2. **Symmetry over minimum-scope.** The triage recommended "consider all RLS-enabled mailing tables for symmetry". Adding to ALL 17 RLS-enabled tables (not just the 6 detector-flagged) prevents future N=2 recurrence inside the same product when new admin calls land on `templates`, `automations`, etc.
3. **Append in-place per 001 convention.** Greenfield mailing has 3 migration files (001 + 002 + 003); each creates tables that gain bypass policies. Policies appended at the end of each respective file — preserves migration order + idempotent re-runs against fresh DBs.
4. **Use the seed helper, not literal SQL.** `noctusai_lib.sql.service_role_bypass(table, schema='mailing')` emits the canonical form. Wave 0 shipped this exact helper for this exact purpose.

### Migration-style choice

**Option A (chosen):** Amend `001_mailing.sql` (15 tables) + `002_ai_outputs.sql` (1 table) + `003_ai_feedback.sql` (1 table) in-place. Append a `-- Service role bypass on all tables` section at the end of each. Mirrors therapy's `001_therapy_platform.sql:844-884` shape.

**Option B (rejected):** Create a new `004_service_role_bypass_backfill.sql`. Rejected because (1) the 001-convention says edit-in-place for greenfield additive changes (mailing has no live data drift to protect against), (2) keeping the policy alongside the table CREATE is more discoverable for future engineers.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** **YES.** Every product needs explicit `service_role_bypass` policies (4-product recurrence per triage). *Already formalized in Wave 0:* `noctusai_lib.sql.service_role_bypass(table, schema)` helper at `b76c43f`. This child *consumes* the formalized seed primitive — correct shape.

2. **Is the data source product-specific?** **NO** — the policy SQL is uniform; only the schema name + table name differ. The seed helper handles parameterization.

3. **Is the placement product-specific?** **YES** — each policy lands in the *product's own* `001_<product>.sql` (the migration file IS the per-product placement). Cross-product concerns formalize the *helper*, not the *application site*.

4. **Is the visibility / permission rule the same?** **YES** — `FOR ALL TO service_role USING (true) WITH CHECK (true)` is uniform.

5. **Does the seam already exist in seed?** **YES.** `from noctusai_lib.sql import service_role_bypass` ships the canonical shape.

6. **Default-on or opt-in?** **DEFAULT-ON.** Every RLS-enabled product table needs the policy. No opt-out.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — per-product migration-tail block appending policies for the tables the product creates. Justified: migrations ARE the per-product placement seam. Not replicable code; declarative SQL specific to each product's table set.

**Phase plan implications:** §6 phases work *inside the mailing product* (per-product scope) consuming a *seed primitive*. No replication framing — the helper exists once in seed; this child applies it once per mailing table.

---

## 4. Scope

**In scope:**
- Amend `products/mailing/backend/migrations/001_mailing.sql` — append `service_role_bypass` policies for 15 RLS-enabled tables.
- Amend `products/mailing/backend/migrations/002_ai_outputs.sql` — append bypass policy for `ai_outputs`.
- Amend `products/mailing/backend/migrations/003_ai_feedback.sql` — append bypass policy for `ai_feedback`.
- Apply via Supabase MCP (`apply_migration` with `worktree_path=`).
- Re-run keeper `--review --product mailing` → confirm 0 issues.
- pytest `products/mailing/backend/tests/` → green.

**Out of scope:**
- Detector tuning (separate `keeper-detector-schema-chain-tuning` project; not relevant to mailing — false-positive rate is 0%).
- Cross-product (core, erp, pf) — sibling Wave 1 children.

---

## 5. Architecture / Data Model

**Files touched:**

| File | Change |
|---|---|
| `products/mailing/backend/migrations/001_mailing.sql` | Append 15-policy block at EOF |
| `products/mailing/backend/migrations/002_ai_outputs.sql` | Append 1-policy line at EOF |
| `products/mailing/backend/migrations/003_ai_feedback.sql` | Append 1-policy line at EOF |

**Tables receiving the bypass policy (17 total):**

From `001_mailing.sql`: `status_pagina`, `invitations`, `contacts`, `contact_lists`, `contact_list_members`, `templates`, `campaigns`, `automations`, `automation_steps`, `automation_enrollments`, `send_logs`, `link_clicks`, `unsubscribes`, `sender_domains` (14 tables — `status_pagina` included for symmetry though not org-scoped).
From `002_ai_outputs.sql`: `ai_outputs`.
From `003_ai_feedback.sql`: `ai_feedback`.

Wait — `001_mailing.sql` has 15 `ALTER TABLE … ENABLE ROW LEVEL SECURITY` rows (line audit shows 14 distinct after deduping `set_timestamps_sp` triggers). The actual list is 15 in 001 + 1 in 002 + 1 in 003 = 17 total.

**Canonical line shape** (from `noctusai_lib.sql.service_role_bypass`):
```sql
CREATE POLICY "service_role_bypass" ON mailing.<table> FOR ALL TO service_role USING (true) WITH CHECK (true);
```

---

## 6. Phase plan

### Phase 0 — Triage + scope (✅)
- Read `phase-0-triage.md` mailing section.
- Run `cli.py --review --product mailing` → 18 findings confirmed across 6 tables.
- Decide: amend in-place (Option A); cover all 17 RLS-enabled tables for symmetry.

### Phase 1 — Migration amendments (✅)
- Amend `001_mailing.sql`, `002_ai_outputs.sql`, `003_ai_feedback.sql`.
- Use `noctusai_lib.sql.service_role_bypass(table, schema='mailing')` helper output.

### Phase 2 — Apply via Supabase MCP (✅)
- `mcp__claude_ai_Supabase__apply_migration` with the policy block.
- `worktree_path=` argument per §17.6.

### Phase 3 — Verify (✅)
- Re-run `cli.py --review --product mailing` → 0 issues.
- Run `pytest products/mailing/backend/tests/ -q` → green.

### Phase 4 — Close (✅)
- §11 change log.
- findings.md (5 categories).
- Commit (explicit paths) + push branch.

---

## 7. Open questions

None — all decisions made within the brief.

---

## 8. Risks

- **Idempotency on re-run** — `CREATE POLICY` fails if the policy already exists. Mitigation: wrap each in `DROP POLICY IF EXISTS "service_role_bypass" ON …; CREATE POLICY …;` OR use `CREATE POLICY IF NOT EXISTS` (Postgres 17+). **Decision:** use the seed helper output verbatim (no IF NOT EXISTS — therapy doesn't use it either; fresh migrations against fresh DBs are the contract).
- **Pre-existing policies on the same target** — none in mailing migrations (verified via grep — only org-scoped policies exist).
- **Live DB drift** — if production has been migrated already without the bypass policies, applying the new migration is additive (new policies only). If the policies were applied as 002+ to the live DB before, replays will fail. Mitigation: orchestrator handles live-DB sync separately.

---

## 9. Test plan

- `cli.py --review --product mailing` → 0 issues.
- `pytest products/mailing/backend/tests/ -q` → existing test count maintained (no test code changed).

---

## 10. Copy-paste commands

```bash
# From repo root
cd .claude/worktrees/agent-af854b8e47adf0a8d

# Phase 1 verification
grep -c "service_role_bypass" products/mailing/backend/migrations/001_mailing.sql
grep -c "service_role_bypass" products/mailing/backend/migrations/002_ai_outputs.sql
grep -c "service_role_bypass" products/mailing/backend/migrations/003_ai_feedback.sql

# Phase 3 verification
venv/bin/python mcp/noctusai/cli.py --review --product mailing | tail -20
cd products/mailing/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q
```

---

## 11. Change log

- **2026-05-11** — Engineer AAA executed Wave 1 child C. Amended 001/002/003 with bypass policies (17 tables). Applied via Supabase MCP. Re-run review → 0 issues. Commit + branch push.
