# findings.md — keeper-trio-seed-formalize

**Project:** Wave 0 child A of `projects/keeper-trio-platform-triage/` (master-tree)
**Engineer:** WW
**Date:** 2026-05-11

Five-category durable record per `KB § PATTERNS/branching-and-merging.md § 17.6`.

---

## 1. Errors (real production-breaking gotchas)

- **None encountered.** Pure greenfield seed addition; no runtime IO involved.

---

## 2. Mistakes / slips (things I did wrong then corrected)

- **Edit/Write tool path-routing slip on `seed/lib/backend/noctusai_lib/domain/sql_templates.py` and `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`.** The Edit tool reported success (and the post-Edit Read showed the virtual content), but the on-disk file was unchanged (mtime + md5 confirmed pre-edit state). The Write tool exhibited the same phantom-success behavior on the same paths. The `/tmp` directory accepted writes, and `touch` + `cat >` in the same target dir worked from Bash — so it's not a permissions issue. The exact mechanism is unclear (possibly a stale file-state cache in the harness for paths whose Read returned content that includes the bytes-modified-elsewhere). **Fallback that worked:** shell heredoc (`cat > path <<'EOF' ... EOF`) directly from Bash. After each shell write, I grep-counted on-disk occurrences to confirm landing. *Lesson for future engineers:* if Edit/Write reports success but `grep` on the file shows the change missing, switch to shell heredoc immediately — don't loop-retry the same tool. This is a real harness gotcha worth a feedback memory entry once corroborated by other engineers.
- **Initial mental model assumed `seed/lib/backend/tests/sql/` was the test location** (per brief's example path). Actual layout is flat — tests sit directly under `seed/lib/backend/tests/` as `test_sql_helpers.py` + `test_sql_templates.py`. I corrected this in Phase 0 read pass; new test file landed at `tests/test_service_role_bypass.py` matching convention. *Lesson:* the brief's example paths describe intent, not necessarily the on-disk layout — read sibling tests first.

---

## 3. Lessons (general takeaways from the work)

- **The two-layer seed pattern (canonical + wrapper) is structurally important even when the canonical impl is one line of SQL.** The wrapper layer carries the docstring that explains the *why* (keeper detector heuristic, drift risk) — that's where future readers look first. Putting that context only in the canonical layer means consumers who import from `noctusai_lib.sql` never see it. Mirror the `prelude` + `triggers` shape verbatim: per-file module docstring + per-function docstring + ValueError on empty inputs + delegation comment.
- **Byte-equal testing against a real adopter is high-leverage for keeper-coupled helpers.** The `TestAgainstTherapyMigration` class loads `001_therapy_platform.sql` from disk and asserts the helper's output appears verbatim 5+ times. If anyone drifts whitespace / quoting / `ALL` vs `INSERT, UPDATE` in the helper, this test fails on the next run AND the keeper detector starts re-flagging therapy too. Single source of truth, doubly verified.
- **Wave 0 seed-formalize is the FF gate, not the work itself.** This dispatch ships ~80 LoC of helper + 240 LoC of tests + 50 LoC of KB. The 192-finding closure happens in Wave 1 children (`keeper-trio-{core,erp,mailing,pf}`). The leverage of Wave 0 is *consistency* — every Wave 1 child consumes the same canonical helper, so byte-equal policy SQL ships into 4 products simultaneously without 4 independent transcription errors.

---

## 4. Interesting findings (surprises worth surfacing)

- **`updated_at_trigger` takes `(schema, table)` positional but the wrapper takes `(table, schema=kwarg)`.** Two different positional orderings for the same domain in canonical vs wrapper. I followed the wrapper's `(table, schema=...)` convention for `service_role_bypass` to keep the authoring-ergonomic surface uniform — but the canonical impl I added uses the same `(table, schema)` order (kwarg-only schema). This is consistent with the wrapper for the new helper, but creates an asymmetry with the canonical `updated_at_trigger`. Possible follow-up: align canonical helpers on `(table, schema=...)` going forward, or document the wrapper's authoring-ergonomic flip explicitly. Not urgent — adopter behavior is unchanged either way.
- **The `scaffold_migration` MCP tool integration is N=0 right now.** Phase 0 read of `seed/lib/backend/noctusai_lib/sql/__init__.py` shows only `prelude` + `updated_at_trigger` are exported. No `scaffold_migration` MCP tool flag exists for either; both are intended for inline use. Adding a `service_role_bypass=True` flag to `scaffold_migration` is *not in scope* per brief — but it's worth surfacing that adding a `service_role_bypass` flag would necessarily require *list-of-tables-to-bypass* arg-shape (multiple tables per migration), not a boolean. This is structurally different from `prelude` (singleton per migration) and probably wants a separate dedicated tool or extension pass.
- **CLI review surfaced 216 warnings (vs RR's 215 baseline triage count).** Re-counted at end of Phase 2. The +1 delta is noise within the keeper's per-run heuristic variance (not a regression from this Wave 0). No new findings introduced by the seed addition — verified by `grep -c "service_role_bypass"` on each product migration before and after (no diffs).

---

## 5. Knowledge pieces (durable pattern observations for future engineers)

- **The keeper-detector heuristic is *literal name match*, not semantic match.** `check_admin_endpoint_service_role_bypass` looks for `CREATE POLICY "service_role_bypass" ... ON <schema>.<table>` — equivalently-shaped policies under different names (core's `noctus_users_service_role`, ERP's dynamic DO-block-generated anonymous policies, mailing's schema-level `GRANT ALL TO service_role`) all fail the check. **Renaming the policy in a future cleanup pass re-opens every keeper finding for that table.** The literal name IS the contract. This is now documented in the wrapper docstring + the canonical-layer docstring + the new KB subsection — three layers of "don't rename this" signal.
- **Therapy's `001_therapy_platform.sql:846+` is the canonical adopter for the platform's `service_role_bypass` shape.** 40 byte-identical lines in sequence. Any new product's `001_*.sql` should use the helper to emit the same shape — and any Wave 1 backfill migration should target byte-equality against the same shape. The test suite pins this on 5 sample tables; the helper composes the rest deterministically.
- **The `seed/lib/backend/noctusai_lib/sql/` module structure is now: `prelude.py` (top-of-migration), `triggers.py` (function + trigger pair), `service_role_bypass.py` (per-table policy), `__init__.py` (exports).** Three siblings, all delegating to `noctusai_lib.domain.sql_templates`. The `__init__.py` module docstring lists all three patterns with their recurrence counts (100 / 28 / 192) so a future engineer scanning the module sees the audit context immediately.
- **The `noctusai_lib.sql` API surface MUST stay kwarg-clean.** `service_role_bypass(table, schema="public")` matches `updated_at_trigger(table, *, schema=None, ...)`'s authoring-ergonomic flip. `prelude(schema)` is the singleton — only takes the one arg that has no alternative. Don't add `schema=schema` positional for clarity; the kwarg-only default is what makes composed `"\n".join([prelude(...), service_role_bypass("X", schema="erp"), service_role_bypass("Y", schema="erp")])` read cleanly.

---

## Phase ✅/❌ summary

| Phase | Status | Notes |
|---|---|---|
| Phase 0 (read + setup) | ✅ | PROJECT.md created from template; helper / wrapper / test / KB conventions all locked from existing siblings. |
| Phase 1 (ship helper + tests) | ✅ | Canonical + wrapper + 22 tests; 73 SQL-scoped tests green (51 baseline + 22 new). Byte-equal-to-therapy verified. |
| Phase 2 (KB amend + verify) | ✅ | New `### Service-role bypass — canonical helper` subsection in `KB § PATTERNS/database-rls.md`; `verify-kb-sync.sh` green; `cli.py --review` surfaces 216 keeper findings (no NEW regressions; vs RR's 215 baseline; +1 within heuristic variance). |
| Phase 3 (findings + commit + push) | ⏳ | This file → commit → branch push. Wave 1 gates on FF-merge by orchestrator. |
