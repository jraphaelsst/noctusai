# Dispatch-pattern-hardening — Project Document

> **Closes the open scoped-improvements from `dispatch-with-project-notes` (Phase 1 delivery note).** The N=1 deferral is being overridden per user instruction — promoting both improvements to s4-keeper + tooling now, so the methodology has structural enforcement instead of advisory-only.

- **Created:** 2026-05-26
- **Last updated:** 2026-05-26
- **Status:** ⏳ in progress
- **Owner / stakeholders:** rapha · architect (tech-lead, this session)
- **Related docs:** `KB § PATTERNS/common/dispatch-with-project-and-notes.md` · `KB § PATTERNS/common/methodology-codification-pipeline.md` · `projects/dispatch-with-project-notes/PROJECT.md` (parent)
- **Project slug:** `dispatch-pattern-hardening`

---

## 1. Context & Purpose

The `dispatch-with-project-notes` delivery note surfaced 3 deferred items + 1 drift-found:

1. **`check_project_has_dispatch_routing` keeper** — promote dispatch-routing-presence to s4 enforcement (was: methodology-in-pilot at s3).
2. **`noctus.dev.codify_log` helper** — wrap ndjson append + enforce s-stage invariants (the bypass-s3 slip needed 5× backfill today).
3. **Pre-commit hook drift** — `scripts/hooks/pre-commit` line 327 syntax error in expression (benign warning, cosmetic).
4. (Open path) Cache-pg VPS bringup — separate project `cache-pg-vps-bringup`.

User instruction: *"implement the deferred scoped-improvement. Dont mind the n=1, implement. fix the pre-commit hook drift."*

The win: dispatch-with-PROJECT goes from advisory → enforced (keeper); codification pipeline goes from manual-prone-to-skip → tool-mediated with invariants.

---

## 2. Confirmed constraints

- **Override N=1** — *(user: "Dont mind the n=1, implement.")* — drives keeper promotion + tool ship even though recurrence hasn't proven it; codification-pipeline rule explicitly allows override when tech-lead judges pattern earned.
- **Grandfather existing projects** — projects created before 2026-05-26 lack §4a (no methodology contract at their birthday); keeper must NOT flag them. Determine via git first-commit-date of PROJECT.md.
- **Codify_log must accept force=True** — backfill use-case (today's 5× backfill required out-of-order writes); enforce by default, escape hatch available.
- **Inline-empersonation throughout** — methodology slice cross-surface shared-state; coherent voice constraint per `parallelization-first-orchestration § inline`.

---

## 3. Design principles

1. **Keeper severity warning, not high** — `check_project_has_dispatch_routing` is advisory; high would block commits on grandfathered projects until they're migrated. Warning surfaces the gap, tech-lead decides cadence of migration.
2. **codify_log composes with existing append** — don't replace direct ndjson writes; ADD a validating helper that callers can choose. Backwards-compat-by-design.
3. **Tests-first for the keeper** — the keeper is itself methodology code; its tests document its contract.
4. **Each slice a separate commit** — file-disjoint, lens-tagged, individually revertable.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every project?** YES — every PROJECT.md with §6 phases should have §4a (universal).
2. **Is the data source product-specific?** NO — keeper reads from disk; helper appends to a single ledger.
3. **Is the placement product-specific?** NO — methodology layer.
4. **Is the visibility / permission rule the same?** YES — every project + every codification event.
5. **Does the seam already exist in seed?** YES — `compliance.py` for keepers; `proposals.py` shape for MCP tools; existing append pattern in `auto-improvement.py` (if any) — verify.
6. **Default-on or opt-in?** DEFAULT-ON for both — keeper runs in `check_all_products`; codify_log enforces by default with `force` escape hatch.

**Litmus:** 0 lines per-product. ✅

---

## 4. Scope

**In scope:**
- W1: Fix `scripts/hooks/pre-commit` line 327 (idempotent — `grep -cE ... || true`)
- W2: `check_project_has_dispatch_routing` keeper in compliance.py + tests + CLI flag + register in check_all_products
- W3: `noctus.dev.codify_log` Python helper + MCP tool registration + tests + CLI flag

**Out of scope:**
- Migrating existing projects to add §4a (opt-in / fix-on-contact)
- Wrapping every existing ndjson append-site to use codify_log (additive — direct writes still valid)
- Cache-pg bringup (separate project `cache-pg-vps-bringup`)
- Memory consolidation (deferred to end-of-session)

---

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice | Lens | Files | Time-box | Dispatched as |
|---|---|---|---|---|
| W1 hook fix | devops-engineer | `scripts/hooks/pre-commit` | 10 min | inline-empersonation |
| W2 keeper | backend-engineer | `mcp/noctusai/tools/noctus/dev/compliance.py` · `mcp/noctusai/tests/test_check_project_has_dispatch_routing.py` (new) · `mcp/noctusai/cli.py` | 45 min | inline-empersonation |
| W3 helper | backend-engineer | `mcp/noctusai/tools/noctus/dev/auto_improvement.py` (or new `codify.py`) · `mcp/noctusai/tools/noctus/dev/__init__.py` (register) · `mcp/noctusai/tests/test_codify_log.py` (new) · `mcp/noctusai/cli.py` | 45 min | inline-empersonation |

*All inline-empersonation: each slice is ≤1 file class + tests; cross-slice shared-state (compliance.py append-point + MCP tool registration) needs coherent voice. Dispatch would multiply merge complexity for negligible parallelism gain.*

### 4a.2 Codification expectations per slice

| Slice | s1 | s2 | s3 | s4 | Why |
|---|---|---|---|---|---|
| W1 hook fix | no | no | no | no | drift-fix-on-contact (pure bug fix) |
| W2 keeper | no | no | no | **yes** | this IS the s4 promotion event for dispatch-with-PROJECT-and-notes |
| W3 helper | yes (recurrence) | no | yes (KB pattern §Tooling updated) | no | tool addition; KB pattern's §Tooling section now mentions codify_log |

### 4a.3 Routes-not-taken (pre-rejected)

| Route | Why rejected |
|---|---|
| Block on missing §4a (severity=high) | Grandfathered projects would freeze the tree; warning preserves cadence flexibility. |
| Replace direct ndjson writes with mandatory codify_log | Breaking change; many call sites; additive helper preserves callers. |
| Refactor `pre-commit` to use `grep -cE` in 5 other places | Surgical fix — only the broken line; sibling lines may be similar but functioning. |
| Migrate every existing PROJECT.md to add §4a same commit | Scope creep — opt-in migration via fix-on-contact rule. |

### 4a.4 Notes — surface + delivery

One delivery note at end of W5 covering all 3 slices. No surface notes expected (routes are clear).

---

## 5. Architecture / Data Model

```
scripts/hooks/pre-commit                                            ← W1: line 327 replaced
mcp/noctusai/tools/noctus/dev/compliance.py                          ← W2: +check_project_has_dispatch_routing()
mcp/noctusai/tools/noctus/dev/auto_improvement.py (or new codify.py) ← W3: +codify_log()
mcp/noctusai/tools/noctus/dev/__init__.py                            ← W3: MCP tool register
mcp/noctusai/cli.py                                                   ← W2 + W3: CLI flags
mcp/noctusai/tests/
  test_check_project_has_dispatch_routing.py                         ← W2: new
  test_codify_log.py                                                  ← W3: new
KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/
  dispatch-with-project-and-notes.md                                  ← W3: §Tooling adds codify_log; W2: §What this does NOT do → flip to "now keeper-enforced"
  methodology-codification-pipeline.md                                ← W3: mention codify_log as the canonical write seam
projects/dispatch-pattern-hardening/                                  ← this folder
  PROJECT.md
  proposals/<delivery-note>.md
```

---

## 6. Implementation phases

### Phase 1 — Pre-commit hook fix (W1) ⏳

- [ ] Read scripts/hooks/pre-commit around line 327
- [ ] Replace the pipeline `wc -l | tr -d ' ' || echo 0` with `grep -cE '^KNOWLEDGE-BASE/.+\.md$' ... || true`
- [ ] Smoke: run the hook locally on a staging diff with 0 KB files (should not error)

**Improvements:** _NOC-FILL-IMPROVEMENTS_

### Phase 2 — check_project_has_dispatch_routing keeper (W2) ⏳

- [ ] Implement keeper function in compliance.py (walks projects/, products/*/projects/, core/projects/)
- [ ] Grandfather: skip projects whose PROJECT.md's first git-commit predates 2026-05-26
- [ ] Register in check_all_products
- [ ] Add CLI flag `--check-project-has-dispatch-routing`
- [ ] Tests covering: no PROJECT.md → no fire · §6 phases + §4a present → no fire · §6 phases + §4a missing + recent → fire · §6 phases + §4a missing + grandfathered → no fire · multi-location project resolution

**Improvements:** _NOC-FILL-IMPROVEMENTS_

### Phase 3 — noctus.dev.codify_log helper (W3) ⏳

- [ ] Implement `codify_log(stage, target, description, ...)` Python helper
- [ ] Enforce s-stage progression invariants (s4 requires s3 for same target in same ledger; configurable lookback window) + `force=True` escape hatch
- [ ] Register as `noctus.dev.codify_log` MCP tool
- [ ] Add CLI flag `--codify-log STAGE TARGET DESCRIPTION`
- [ ] Tests covering: valid s1/s2/s3/s4 progression · s4 without s3 → reject · s4 without s3 + force=True → write · invalid stage → error · empty target → error · missing description → error · idempotency (re-write same target+stage)
- [ ] KB pattern §Tooling updated; methodology-codification-pipeline.md mentions codify_log

**Improvements:** _NOC-FILL-IMPROVEMENTS_

### Phase 4 — Verify + commit + push (W5) ⏳

- [ ] kb_sync ✓
- [ ] check_claude_md_router ✓
- [ ] check_seven_way_sync ✓
- [ ] check_project_has_dispatch_routing ✓ (self-check)
- [ ] All impacted pytest green
- [ ] Commit each slice (W1 / W2 / W3 separately) with Lenses: trailer
- [ ] Push feat/dispatch-hardening-and-cache-bringup
- [ ] FF-merge into dev
- [ ] File delivery note via noctus.dev.file_proposal(kind="delivery", project="dispatch-pattern-hardening")

**Improvements:** _NOC-FILL-IMPROVEMENTS_

---

## 7. Open questions

None — slices are well-specified.

---

## 8. Dependencies & blockers

None — pure code change.

---

## 9. Success criteria

- [ ] pre-commit hook no longer prints `syntax error in expression`
- [ ] `check_project_has_dispatch_routing` exists + registered + has tests
- [ ] `noctus.dev.codify_log` MCP tool exists + has tests + enforces s-stage invariants
- [ ] `KB § PATTERNS/common/dispatch-with-project-and-notes.md` references codify_log
- [ ] Delivery note filed in proposals/
- [ ] dev pushed with all changes

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-26 | Initial draft + execution started | architect (tech-lead) |
