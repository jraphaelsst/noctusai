# worktree-bootstrap-script — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED 2026-05-10.** All phases (0-2) shipped. Script lives at `scripts/bootstrap-worktree.sh` (executable, idempotent, `--check` mode); KB §16.7 amended with Step 0 environment-hydration clause. Smoke verified: 14/14 frontends hydrated (90s first pass; 0.23s idempotent re-run); vite build green on `products/seed/frontend`.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `worktree-bootstrap-script`

---

## 1. Context & Purpose

Engineers in isolated worktrees consistently waste ~5-10 minutes per session on env-parity issues:

- **Engineer G** (2026-05-10): vite build failed with `Cannot find module 'tailwindcss-animate'` — needed `npm install` in BOTH `products/therapy-platform/frontend/` AND `seed/framework/frontend/`.
- **Engineer Q** (2026-05-10): same shape; `npm install` in both PF frontend + framework before vite build worked.
- **Engineer AA** (2026-05-10): vitest workers failed on `Cannot find package 'jsdom'`; required `npm install` in **3 places** (PF frontend + framework + lib). N=2 in one session.
- **Engineer N** (2026-05-10): python venv inherited host py3.10 instead of py3.11; required explicit `python3.11` + editable installs.
- **Engineer S** (2026-05-10): cross-realm type errors traced to missing `npm install` in lib.

**N=5+ confirmed**. Mechanical fix.

## 2. Confirmed constraints

- **`.git` worktrees share `.git/config` + objects** but each has its own working tree files. `node_modules/` is .gitignored, so fresh worktrees start without it.
- **Python venv** (`/Users/rapha/Documents/repository/NoctusAI/noctusai/venv`) is shared across worktrees — but PYTHONPATH overrides + editable installs may need re-running per worktree.
- **`mcp/noctusai/.venv`** is the MCP toolkit venv; usually OK as the MCP server is process-shared.

## 3. Design principles

1. **One script, one command.** `scripts/bootstrap-worktree.sh` runs all installs in series; idempotent.
2. **Detect-and-skip.** If `node_modules/` exists with current `package.json.lock` hash, skip.
3. **Print recap.** End with "✓ frontends ready · PYTHONPATH=… · python3.11 active."

## 3a. Seed-first analysis

- **Cross-product?** YES — every engineer worktree benefits.
- **Per-product code count?** 0 — script lives at `scripts/`.

## 4. Scope

- **In scope:** `scripts/bootstrap-worktree.sh` (executable, idempotent, runs `npm ci` in {seed/lib/frontend, seed/framework/frontend, every products/*/frontend with package.json}; ensures python3.11 + PYTHONPATH).
- **Out of scope:** auto-running on worktree create (could be a future Agent-tool integration).

## 5. Architecture / Data Model

```bash
#!/usr/bin/env bash
# scripts/bootstrap-worktree.sh — hydrate a fresh worktree's env
set -euo pipefail

WORKTREE_ROOT="$(git rev-parse --show-toplevel)"
cd "$WORKTREE_ROOT"

echo "→ Hydrating worktree at $WORKTREE_ROOT"

# 1) Seed frontends
for d in seed/lib/frontend seed/framework/frontend; do
  if [[ -f "$d/package.json" ]]; then
    echo "  · npm ci in $d"
    (cd "$d" && npm ci --silent)
  fi
done

# 2) Per-product frontends
for d in products/*/frontend; do
  if [[ -f "$d/package.json" ]]; then
    echo "  · npm ci in $d"
    (cd "$d" && npm ci --silent)
  fi
done

# 3) Print Python recap
PY="$(which python3.11 2>/dev/null || which python3)"
echo "→ Python: $PY"
echo "→ Suggested PYTHONPATH: $WORKTREE_ROOT/seed/lib/backend"
echo ""
echo "✓ Worktree env hydrated. To run backend tests, export:"
echo "  export PYTHONPATH=$WORKTREE_ROOT/seed/lib/backend"
```

## 6. Implementation phases

### Phase 0 — Confirm scope + write script ✅

- [x] Author `scripts/bootstrap-worktree.sh` per §5 template (with two extensions: `--check` read-only mode + `npm install` fallback when `package-lock.json` absent).
- [x] Idempotency check — re-run on hydrated worktree is 0.23s (skip-if-newer guard via `node_modules/.package-lock.json` mtime comparison).
- [x] `chmod +x scripts/bootstrap-worktree.sh` (mode `-rwxr-xr-x`).

**Improvements (Phase 0):**
- Added `--check` mode (read-only baseline reporter) — useful for orchestrators detecting whether a dispatched worktree needs hydration before re-dispatch.
- Added `npm install` fallback when a frontend has no `package-lock.json`. First-pass smoke surfaced this: `products/imobi-scheduling/frontend` + `products/youtube-crawler/frontend` have no checked-in lockfile, so `npm ci` errored. Fallback unblocked both. These two products SHOULD eventually check in their lockfiles for deterministic CI — deferred (see Phase 2 Improvements).
- Hardened error reporting: per-frontend FAILED tracking + non-zero exit + recap so partial failures are loud, not silent.

### Phase 1 — Document + amend engineer-brief preamble ✅

- [x] KB §16.7 amended with new "Step 0 — environment hydration" paragraph; references `scripts/bootstrap-worktree.sh` + idempotency timing + N=5+ origin + skip-rule (purely-backend briefs).
- [x] Memory entry update routed to orchestrator per engineer/architect role split (engineer doesn't edit `MEMORY.md`). Surfaced in findings.

**Improvements (Phase 1):** none identified — KB amend is a single paragraph at a known location; no design decisions surfaced.

### Phase 2 — Close ✅

- [x] Smoke: this worktree was fresh (all 14 frontends started without `node_modules/`); script hydrated 12 via `npm ci`, then 2 via `npm install` fallback, all green on retry. Verified `npx vite build` on `products/seed/frontend` → green in 3.4s. Idempotent `--check` re-run confirms 0 stale.
- [x] Improvements blocks captured per-phase (above).
- [x] §11 close-row added (below).
- [x] Archive — orchestrator handles per brief instruction.

**Improvements (Phase 2):**
- **Lockfile check-in for `imobi-scheduling` + `youtube-crawler`.** N=2 cross-product recurrence: both lack `package-lock.json` in git. Triage = **formalize** (commit the generated lockfiles per product) — small + deterministic + removes the `npm install` fallback's need over time. The lockfiles WERE generated as side-effects of the smoke run; left untracked because they're not engineer-authored code per the brief's authorship discipline. Orchestrator can stage them in a follow-up commit or file a dedicated follow-up.

## 7. Open questions

- None.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [x] Script ships at `scripts/bootstrap-worktree.sh`.
- [x] §16.7 preamble references it (Step 0 — environment hydration clause, NEW 2026-05-10).
- [ ] Memory entry mentions Step 0 for worktree-frontend work. *(deferred to orchestrator per role split — engineer does not edit MEMORY.md)*
- [x] Smoke: fresh worktree → run script → all frontends green (12 via `npm ci`, 2 via `npm install` fallback; vite build smoke on `products/seed/frontend` green in 3.4s).

## 10. How to use this plan

Single-engineer dispatch. Mechanical.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** N=5+ confirmed across Engineers G, Q, AA, N, S in this session (~5-10 min wasted each on env-parity dance: npm install in seed/lib + seed/framework + product/frontend + python venv). One-shot script + §16.7 preamble update. | claude-opus-4-7 |
| 2026-05-10 | **Phases 0-2 closed by Engineer.** Script lives at `scripts/bootstrap-worktree.sh` (executable, idempotent, `--check` flag). KB §16.7 amended with "Step 0 — environment hydration" clause. Smoke: 14/14 frontends hydrated (12 via `npm ci`, 2 via `npm install` fallback — `products/imobi-scheduling/frontend` + `products/youtube-crawler/frontend` lack `package-lock.json`; surfaced as Improvement). Idempotent re-check: 0.23s. Vite build green on `products/seed/frontend` (3.4s). Memory-entry sync deferred to orchestrator per role split. Mid-flight slip: 3 of my Edit calls landed on `/Users/rapha/.../noctusai/...` (main repo) instead of `.../noctusai/.claude/worktrees/agent-.../...` (this worktree); recovered via `git stash` in main repo + re-applied on worktree paths. Slip explained in end-state findings. | engineer-agent-a8fc647dc320b0bb2 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
