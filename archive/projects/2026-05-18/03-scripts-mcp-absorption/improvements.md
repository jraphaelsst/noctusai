# Improvements — Scripts → MCP Absorption — Project Document

> **Auto-generated** from `PROJECT.md` by `python mcp/noctusai/cli.py --improvements <plan.md>`. Regenerated every time a phase is ticked complete. Do not edit by hand.

> This file captures **improvement opportunities discovered while implementing each phase** — things future iterations of *this* phase should consider. It is NOT a preview of upcoming phase tasks (those live in the plan itself). When a phase is refactored or revisited, open this file first.

**Plan:** `PROJECT.md`
**Plan status:** ✅ DONE — all 7 phases complete (rule codified · 16 scripts → native MCP · pre-commit thin-dispatcher · carve-outs documented · full folder reorg with risk-mitigation · verified)
**Completed phases:** 8 of 8.
**Phases with recorded improvements:** 8 of 8 completed.

## Improvements by phase

### Phase 0 — Audit

- The "already has an MCP analog" bucket split in two only because the audit *read* `mole.py` (a 26KB-shell `subprocess` shim) instead of trusting its existence — `verify-the-seed-ships-it`-shaped lesson applied to tooling: an MCP file existing ≠ the logic being absorbed. Bucket B exists because of this; no further action.
- Manifest's durable home is the KB doc, not this PROJECT.md §5 (PROJECT.md is archive-bound — durable-docs rule). §5 now references §3 of the KB doc rather than owning the table.

### Phase 1 — Doc rule codification + keeper

- The keeper asserts row-*presence* only, not disposition fidelity — a future `[carve:*]`↔accept-with-rationale 1:1 cross-check keeper (Phase 5 could seed it) would close the "carve-out claimed in manifest but no rationale entry" gap; deferred to Phase 5 where the catalog entries are authored.
- `pre-commit` (extensionless) is manifest-documented but out of keeper scan-scope by the `*.{sh,py}` glob — intentional (doc note states it), but a determined slip could add an extensionless `scripts/foo` automation that escapes. Acceptable: extensionless executables in `scripts/` are vanishingly rare and the carve-out taxonomy already covers the only real one. Logged, not fixed.
- `mole.py`-is-only-a-subprocess-shim was caught at audit time, not classification time — the §5/§3 "B · heavy port" bucket exists because of it. Confirms the audit-before-bucket discipline; no action.

### Phase 2 — Bucket A+B (dedup + heavy port)

bucket A proved empty — every "already has an analog" candidate was a `subprocess` shim, so A+B collapsed to "genuine port". Full synthesis in the consolidated **Improvements (Phases 2-5)** block below (shared cross-phase context — bundled per the one-proposal-per-phase-context rule).

### Phase 3 — Bucket C absorptions (5 parallel engineers, file-disjoint)

the 5-engineer file-disjoint design held with zero file collision; the only failures were the two harness-structural issues (worktree-base, overlay-lands-in-session-tree) — both recoverable architect-inline without re-dispatch. Full synthesis in the consolidated **Improvements (Phases 2-5)** block below.

### Phase 4 — pre-commit thin-dispatcher

Phase 4 was validated *live* — committing Phase 2-5 ran the rewritten thin-dispatcher pre-commit, and the native `cli.py --check-phase-state` flag correctly caught this very §6-Improvements gap (the safety net firing IS the methodology working). Full synthesis in the consolidated block below.

### Phase 5 — Carve-out documentation

- `isolation:"worktree"` forks from `origin/main` not the feature HEAD; subagent Writes land in the SHARED session/main-tree not the worktree. Both diagnosed + mitigated (ff-only base-correction preamble in briefs; main-tree true-disk salvage). Codified → `feedback_worktree_isolation_base_and_overlay` + memory.
- Byte-parity-vs-script tests are inherently one-shot (proven green at port time, unrunnable post-deletion). Fix-on-contact: converted `TestRenderProjectHistoryParity`/test_propagate to native behavioural assertions; retired `test_render_history.py`/`test_gen_promotions_index.py`/`test_merge_debt_monitor.py`; added native `TestGenPromotionsIndex`. Lesson: a port's byte-parity test should assert against a *committed golden fixture*, not a freshly-loaded soon-to-be-deleted script — candidate KB addition to `mcp-first-scripts.md`.
- `promotion.py` emitted-template + `mole.py` `next_action` embedded the old script path (parity-faithful but dangling once deleted) — repointed in the same change. Generalizes `feedback_dangling_deleted_product_path` to *generated-output* strings, not just docs.
- N≥5 identical "script→native dev-tool port" shape across one dispatch (ANALYSIS alone = 5) → recurrence rule: candidate `scaffold_script_port` emitter / KB recipe. Logged for follow-up (not in this project's scope).

### Phase 6 — Folder reorganization

the forwarding-shim-for-contract-entrypoints pattern is the reusable risk-killer for any future `scripts/` move (preserve the `bash scripts/X` muscle-memory/CI/onboarding contract while the body relocates). The keeper's basename-match (not path-match) makes the manifest path-stable across folder moves — a deliberate design choice worth noting in `mcp-first-scripts.md` (done). Recurrence candidate: a generic "intent-folder a flat dir + shim its contract entrypoints" recipe.

### Phase 7 — Verify + close

the pre-commit thin-dispatcher's `--check-phase-state` self-caught a §6-Improvements gap mid-close (Phases 2/3/4, then this Phase 7 stub-duplicate) — the methodology's own gate enforcing the methodology's own doc, dog-fooded live. Lesson: appending a new `### Phase N ✅` ahead of an existing template stub leaves a duplicate header — future closes should edit the stub in place, not prepend. No code impact; PROJECT.md is archive-bound.

## Deferred items (from §4 Out of scope)

_Work deliberately scoped out of this plan. Track as candidates for future plans, not as improvements to existing phases._

- `scripts/codemods/` (AST codemod *library*, not a script — already AST, not flat-folder noise) — folder-reorg phase may relocate but no absorption.
- `scripts/init-local-db/*.sql` — SQL data files, not scripts — folder-reorg only.
- Rewriting bootstrap *behaviour* — only thin-shim/rationale, no functional change (fresh-clone safety is non-negotiable).

## Open questions still blocking

- **`mole.sh` port fidelity** — 26KB shell w/ destructive `sweep --force`; port must be byte-parity on the safe-gate. Mitigation: keep old script in git history; parity test diffs scan output before deleting. Decided during W2.
- **Thin-shim language for pre-commit** — bash dispatcher vs `exec python cli.py`. Recommendation: minimal `exec "$PY" "$REPO_ROOT/mcp/noctusai/cli.py" --precommit` preserving the existing venv-detection preamble. Confirm at Phase 4.
