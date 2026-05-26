# Proposal: Dispatch-pattern-hardening — Phase 1 delivery

**Agent:** architect-inline (claude-opus-4-7)
**Note kind:** delivery
**Origin:** project:dispatch-pattern-hardening:phase-1
**Generated:** 2026-05-26 17:53
**Severity:** medium
**Effort:** medium
**Affected products:** none (methodology — touches scripts/hooks · compliance.py · MCP tool registry · CLI · KB · tests)
**Status:** pending  <!-- tech-lead (rapha) absorbs lessons + closes -->

---

## 1. Context

The `dispatch-with-project-notes` Phase 1 delivery note (commit `2e3e068a`) surfaced 3 deferred scoped-improvements + 1 drift-found. User instruction in this session: *"implement the deferred scoped-improvement. Dont mind the n=1, implement. fix the pre-commit hook drift."* — overriding the N=1 deferral per `methodology-codification-pipeline.md` (tech-lead-judged promotion is permitted).

The slice closes the loop on the dispatch-with-PROJECT-and-notes methodology: instead of advisory-only enforcement (the §4a rule + per-engineer-discipline), the rule now has **structural enforcement** (keeper) + **structural emission** (codify_log helper). The pre-commit hook drift was a sibling clean-up.

---

## 2. Situation (as-shipped state)

Three slices shipped + one operational fix:

### W1 — Pre-commit hook fix (`scripts/hooks/pre-commit`)

Line 327: `wc -l | tr -d ' ' || echo 0` produced `"0\n0"` under `set -o pipefail` when `grep -E` matched nothing (grep's exit-1 fired the `|| echo 0`, but the `wc | tr` had already written its own `0`). The downstream `[[ "$STAGED_KB_FOR_BASELINE" -gt 5 ]]` then errored with `syntax error in expression (error token is "0\n0")`. Replaced with `grep -cE '^KNOWLEDGE-BASE/.+\.md$' || true` + `: "${VAR:=0}"` default — single source of truth for the count. Smoke-tested with empty-diff + 7-file cases.

### W2 — `check_project_has_dispatch_routing` keeper (`mcp/noctusai/tools/noctus/dev/compliance.py`)

New Stage-4 keeper after `check_codification_pipeline_health`. Walks `_find_all_project_md(root)` (the 3 valid project locations). Fires when PROJECT.md has `### Phase \d+` headers AND lacks `## 4a` heading. **Grandfather rule**: skips projects whose PROJECT.md first-commit predates `2026-05-26` (the rule's birthday) via `git log --diff-filter=A --format=%aI --follow`. Registered in `check_all_products`. CLI flag `--check-project-has-dispatch-routing`. Severity `warning` (advisory — grandfathering keeps the warning surface tractable). 10 tests cover: no projects, §4a present, missing §4a, no phases, pre-birthday grandfather, post-birthday flag, birthday-inclusive boundary, multi-location resolution, untracked-file-falls-through-to-flag, §4a header variants.

### W3 — `noctus.dev.codify_log` helper (`mcp/noctusai/tools/noctus/dev/codify.py`)

New module `codify.py` wrapping `auto_improvement.log_entry` with s-stage progression invariants:

- `s4-keeper` for target T requires preceding `s3-codified` (or legacy `s3-kb`) for same target — else `{ok: False, missing_prereq: "s3-codified"}`.
- `s3-codified` for target T requires preceding `s1-emergent` OR `s2-memory` — else `{ok: False, missing_prereq: "s1-emergent | s2-memory"}`.
- `s1-emergent` / `s2-memory` are entry points (no prereq).
- `force=True` escape hatch bypasses the prereq AND tags the entry's `source_ref` with `force:<original>` for audit.
- Validation: target non-empty, description ≥20 chars, stage in `VALID_STAGES = {s1-emergent, s2-memory, s3-codified, s4-keeper}`. Legacy `s3-kb` NOT emittable (read-side compat only).

Sibling work: added `s3-codified` to `auto_improvement.STATUSES` (legacy `s3-kb` kept as alias). Registered as `noctus.dev.codify_log` MCP tool. CLI flag `--codify-log STAGE TARGET DESCRIPTION [--force --codify-source-ref REF]`. 19 tests cover validation paths + progression + force + ledger integration.

### KB doc update

`KB § PATTERNS/common/dispatch-with-project-and-notes.md` — §Tooling section adds `codify_log` MCP tool + `check_project_has_dispatch_routing` keeper + the 3 new CLI flags. §Recurrence trigger paragraph rewritten: "N=1 (this codification)" → "Promoted to s4 same-day (2026-05-26 evening)" with rationale (user override).

---

## 3. Proposed Solution

Delivery note — solution shipped. Sections 3.1-3.5 record HOW.

### 3.1 Linkage — why this solution fits this situation

The user's instruction *"don't mind the n=1, implement"* explicitly invoked tech-lead-judged-pattern-earned promotion (`methodology-codification-pipeline.md § What legitimately stays at Stage 3`). The keeper + helper compose into structural enforcement: §4a presence is now a `warning` keeper; s-stage emission is now a validated tool call. The pre-commit drift fix is independent but rides the same slice for atomicity.

### 3.2 Application instructions (HOW the change was made)

1. **W1**: Edit `scripts/hooks/pre-commit` line 327 — single-line substitution + 4-line comment explaining the prior failure mode. Smoke via local bash with `set -o pipefail` + two test cases.
2. **W2**: New keeper inserted after `check_codification_pipeline_health` (line ~9722); reuses existing `_find_all_project_md` helper + `_PHASE_HEADER_RE`. Module-level constant `DISPATCH_ROUTING_BIRTHDAY = "2026-05-26"` for the grandfather threshold. Registered in `check_all_products` after `check_phase_state_consistency`. CLI flag + handler added next to `check_codification_pipeline_health`'s handler.
3. **W3**: New module `mcp/noctusai/tools/noctus/dev/codify.py`. Imports from sibling `auto_improvement` module. `_has_prereq_status` helper queries the ndjson directly. `register(server)` for MCP. `auto_improvement.STATUSES` extended (additive — both `s3-kb` AND `s3-codified` valid; codify_log emits canonical `s3-codified`). `__init__.py` registers `codify.register(server)`. CLI flag added; `--codify-log` accepts 3 positional args via `nargs=3`. KB doc § Tooling + § Recurrence trigger updated.

### 3.3 Seed APIs / shared lib involved

- `tools.noctus.dev.auto_improvement.log_entry` — the underlying ndjson appender; `codify_log` wraps it.
- `tools.noctus.dev.compliance._find_all_project_md` — the existing PROJECT.md walker; `check_project_has_dispatch_routing` consumes it.
- `tools.noctus.dev.compliance._PHASE_HEADER_RE` — existing phase header regex; the keeper uses it to confirm "real phases" before flagging.

### 3.4 Risks before applying

Low risk — additive across the board.
- `check_project_has_dispatch_routing` is severity `warning` (advisory, never blocks commits); grandfathering keeps the warning set tiny on the existing tree.
- `codify_log` is opt-in (existing direct ndjson writers still work); adds validation on the new entry point only.
- The pre-commit fix is a strict improvement — broken cosmetic warning → clean output.

### 3.5 Alternatives considered

- **Severity=high for `check_project_has_dispatch_routing`** — rejected: would freeze grandfathered projects from being touched until migrated.
- **Replace all direct ndjson writes with mandatory codify_log** — rejected: breaking change; many call sites; additive helper preserves callers.
- **Surgical grep -cE in 5 sibling places of pre-commit** — rejected: surgical fix is the brief; sibling lines may be functioning fine.

---

## 4. Effects

- **Behavior:** new keeper warning on `--validate` output for any new project (post-birthday) that ships §6 phases without §4a. New MCP tool `noctus.dev.codify_log` + CLI flag `--codify-log`. Pre-commit hook no longer prints `syntax error in expression`.
- **Risk profile:** SAFER — codification pipeline now has structural enforcement at emission (s-stage progression invariants); dispatch-with-PROJECT-and-notes has keeper-warning visibility on missed §4a.
- **Ergonomics:** Future codify_log callers get a one-line invocation that enforces the contract; the 5×-backfill recurrence pattern from earlier today is preempted at the API.
- **Coverage:** +10 tests (`test_check_project_has_dispatch_routing.py`) + 19 tests (`test_codify_log.py`); both green.

---

## 5. Acceptance Criteria

- [x] `scripts/hooks/pre-commit` no longer prints `syntax error in expression`
- [x] `check_project_has_dispatch_routing` exists + registered + has tests (10/10 green)
- [x] `noctus.dev.codify_log` MCP tool exists + has tests (19/19 green) + enforces s-stage invariants
- [x] CLI flags `--check-project-has-dispatch-routing` + `--codify-log` + `--codify-source-ref`
- [x] `KB § PATTERNS/common/dispatch-with-project-and-notes.md` references codify_log + the keeper
- [x] This delivery note filed
- [ ] Keeper gates green (verified in W5)
- [ ] Commit + push + FF-merge dev (W5 in flight)

---

## 6. Related files

- `scripts/hooks/pre-commit` line 327
- `mcp/noctusai/tools/noctus/dev/compliance.py` (W2 keeper + register in `check_all_products`)
- `mcp/noctusai/tools/noctus/dev/codify.py` (NEW, W3)
- `mcp/noctusai/tools/noctus/dev/auto_improvement.py` (STATUSES extension)
- `mcp/noctusai/tools/noctus/dev/__init__.py` (register codify)
- `mcp/noctusai/cli.py` (CLI flags)
- `mcp/noctusai/tests/test_check_project_has_dispatch_routing.py` (NEW)
- `mcp/noctusai/tests/test_codify_log.py` (NEW)
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/dispatch-with-project-and-notes.md`
- `projects/dispatch-pattern-hardening/PROJECT.md` (the dispatch brief)

---

**Codification events emitted (this slice):**
- s1-emergent: none — pattern was already at s1 from prior session
- s2-memory: none — same-commit s3→s4 compression
- s3-codified: `KB § PATTERNS/common/dispatch-with-project-and-notes.md` updated (the helper + keeper documented; § Tooling + § Recurrence trigger rewrites)
- s4-keeper: `check_project_has_dispatch_routing` (warning) + `noctus.dev.codify_log` enforcement tool. **The keeper IS the s4 promotion** for the dispatch-with-PROJECT-and-notes pattern; the helper IS the structural emission point.

**drift-found:** `auto_improvement.STATUSES` had `s3-kb` but `check_codification_pipeline_health` keeper uses `s3-codified` — two-name drift on the same concept. Resolved in-flight (added `s3-codified` as canonical alongside legacy `s3-kb`). 1 ledger entry uses legacy `s3-kb`; not migrated (the helper accepts both on read).

**scoped-improvement:** `noctus.dev.vps_exec_sql` candidate — the schema-init had to switch from `docker exec psql <<EOF` to `docker cp tmp + docker exec psql -f` because SSH-stream-through-docker-exec heredoc munged silently (no error, just empty). A small wrapper around the `docker cp + docker exec -f` idiom would prevent the trial-and-error recurrence. **Codify candidate** — observed N=1 today; surface for future.

**Routes-not-taken encountered + chose-not-to-surface:**
- Could have built a separate `noctus.dev.codify_check` MCP tool that verifies the invariants WITHOUT writing (validation-only) — defer; current shape returns structured dict that callers can use as validation-only by ignoring the write side. YAGNI for now.
- Could have migrated the 1 legacy `s3-kb` entry to `s3-codified` — defer; the helper handles both on read; no consumer complaint.
- Could have lifted `_DISPATCH_ROUTING_HEADER_RE` into a shared `_section_header_re(num, letter=None)` helper — N=2 today (would need a sibling first). Defer per N≥3 rule.
