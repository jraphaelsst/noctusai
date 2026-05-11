# worktree-bootstrap-script — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 📋 **READY FOR EXECUTION.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineers Q + AA + N + S confirmed N=4+ worktree env-parity gotcha: fresh worktrees inherit empty node_modules + need `npm install` in multiple seed/product dirs to verify changes.
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

### Phase 0 — Confirm scope + write script

- [ ] Author `scripts/bootstrap-worktree.sh` per §5 template.
- [ ] Idempotency check (re-run on hydrated worktree should be fast or no-op).
- [ ] `chmod +x scripts/bootstrap-worktree.sh`.

### Phase 1 — Document + amend engineer-brief preamble

- [ ] Add reference in `KB § PATTERNS/branching-and-merging.md §16.7` (worktree-base-verification): "Step 0: run `bash scripts/bootstrap-worktree.sh` if your brief touches frontend or runs vitest/vite build."
- [ ] Mention in `feedback_worktree_base_verification.md` memory entry (sub-rule for env-parity).

### Phase 2 — Close

- [ ] Smoke: create a fresh worktree via `git worktree add`, run the script, verify all frontends + python work.
- [ ] Improvements block + §11 + archive.

## 7. Open questions

- None.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] Script ships at `scripts/bootstrap-worktree.sh`.
- [ ] §16.7 preamble references it.
- [ ] Memory entry mentions Step 0 for worktree-frontend work.
- [ ] Smoke: fresh worktree → run script → all frontends green.

## 10. How to use this plan

Single-engineer dispatch. Mechanical.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** N=5+ confirmed across Engineers G, Q, AA, N, S in this session (~5-10 min wasted each on env-parity dance: npm install in seed/lib + seed/framework + product/frontend + python venv). One-shot script + §16.7 preamble update. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
