# Storage hygiene — the `mole` and the trio

> **TL;DR.** Third member of the regulatory/curatorial/custodial trio. Keeper guards laws, hound sniffs out hygiene, **mole burrows for storage waste**. Three orthogonal scopes — `artifacts` (regenerable caches/builds), `environments` (venv/node_modules duplication), `worktrees` (stale `.claude/worktrees/agent-*/`). Active by default: pre-dispatch + pre-commit + post-merge.

---

## 1 · Why the mole exists

### The methodology gap it closes

Storage waste accumulates **silently** until it becomes a hard blocker. The 2026-05-11 incident: disk filled to 100% (`ENOSPC` on `/private/tmp`), 4 in-flight engineers blocked at preamble, an entire session paused. Root cause: cleanup script's `mapfile` (bash 4+) crashes silently on macOS bash 3.x, so the methodology-mandated cleanup ran as no-op for the full session.

The shape of the gap:
- **Cumulative**: ~880 MiB per agent worktree × 98 stale worktrees = ~86 GiB consumed unrecoverable until manual sweep
- **Silent**: cleanup script exit-1'd but its output went to a log file nobody read; engineers kept hydrating new worktrees on top
- **Catastrophic**: when storage finally pegs at 100%, EVERY tool fails — bash output spill, pytest, npm install, git push tracking-config

A monitor (`disk-usage-monitor.sh`) detects the failure; a sweeper (`cleanup-stale-worktrees.sh`) reverses it. Neither is **actively scanning for opportunities** the way `keeper --review` and `hound scan` do for code. **The mole is the missing third agent** — an active patrol of the filesystem looking for safe optimization opportunities BEFORE storage pressure becomes a blocker.

### Analogy with keeper + hound

| Agent | Domain | Default mode | Single entry point | Three scopes |
|---|---|---|---|---|
| **Keeper** | Regulatory (compliance contracts) | `--review` observation-only | `noctus.dev.review` | LGPD / webhook-pins / auth-shape / etc. |
| **Hound** | Curatorial (code hygiene) | `scan` (read-only) | `noctus.hound.scan` | absorption / fusion / optimization |
| **Mole** | Custodial (storage hygiene) | `scan` (read-only) | `noctus.mole.scan` | **artifacts / environments / worktrees** |

Each agent has **observation-only scan** (default) + **destructive sweep** (gated, dry-run-by-default).

---

## 2 · The three orthogonal scopes

### 2.1 · Artifacts (regenerable caches + build outputs)

**Definition**: files/directories that build tools regenerate on demand. Safe-to-wipe — losing them just triggers a rebuild on next run.

**Patterns** (canonical list, lives in `scripts/mole.sh` as the artifact deny-list lookup-table):
- `__pycache__/` — Python bytecode (regenerated on next import)
- `.pytest_cache/` — pytest fixture state (regenerated on next run)
- `.ruff_cache/` — ruff linter cache
- `.mypy_cache/` — mypy type-check cache
- `.tsbuildinfo` — TypeScript incremental build state
- `dist/` (under `products/*/frontend/`) — vite build output; ONLY safe if not currently serving prod
- `build/` (under `products/*/frontend/`) — same as dist
- `.next/` — Next.js build output (no current adopters, future-proofing)
- `coverage/` — pytest-cov / vitest coverage reports

**Reversibility test**: would running `pytest` / `vite build` / `tsc --build` regenerate this exactly? If yes → artifact. If no → NOT artifact.

**Anti-patterns** (NEVER classify as artifact):
- `.venv/` — venv recreation costs ~30s + network; classify as environment, not artifact
- `node_modules/` — same; environment
- `.git/objects/` — git history; touching this corrupts the repo

### 2.2 · Environments (venvs + node_modules duplication)

**Definition**: dependency installations that the package manager fetches/builds. Recoverable via `pip install -r requirements.txt` / `npm ci` but at network + CPU cost.

**Patterns**:
- `.venv/` and `venv/` — Python virtual environments
- `node_modules/` — npm/pnpm/yarn dependency tree
- `.tox/` — tox-managed multi-env testing
- Per-product duplication where shared workspace would save space

**Reversibility test**: would running `pip install` / `npm ci` rebuild this? If yes → recoverable but expensive. Wipe only if user explicitly authorizes.

**Active opportunity**: the mole **reports** duplication but does NOT auto-sweep environments. Example finding: "11 products each have `lucide-react/dist` at 34 MB = 370 MB total. pnpm-workspace would share one copy → save ~340 MB."

**Anti-patterns**:
- Auto-wiping `.venv/` without warning — engineer next session loses 30s × N rehydrate cost
- Touching `seed/lib/backend/.venv` — it's the seed lib editable install; deleting requires re-install gymnastics

### 2.3 · Worktrees (stale `.claude/worktrees/agent-*/`)

**Definition**: agent worktree directories under `.claude/worktrees/` whose branch is reachable from `origin/main` by SHA ancestry OR patch-id equivalence (cherry-pick).

**Patterns**:
- `.claude/worktrees/agent-<id>/` with branch SHA-merged to origin/main (true merge)
- `.claude/worktrees/agent-<id>/` with branch commits all present on origin/main by patch-id (cherry-pick — the gap §19 of branching-and-merging.md captures)
- Orphan dirs under `.claude/worktrees/agent-*/` that git doesn't recognize as worktrees (rm'd manually but metadata left)

**Reversibility test**: is the work merged? Either:
- `git merge-base --is-ancestor <branch> origin/main` ✓ → SHA-merged, safe to remove
- `git cherry origin/main <branch>` empty `^+` lines ✓ → patch-id merged, safe to remove
- Both fail → UNMERGED, do NOT remove (active work, cherry-pick pending, or stalled engineer)

**Lock detection**: `git worktree list --porcelain` reports `locked` flag. Cleanup script's `git worktree remove --force` (single force) does NOT break locks; needs `-f -f` (double force) when the agent harness has stale-locked it. The mole handles double-force on stale-merged locked worktrees automatically.

**Anti-patterns**:
- Removing a worktree whose branch has UNMERGED commits — loses the engineer's work
- Removing the main worktree (the repo root itself)
- Removing sibling workspaces (paths NOT under `.claude/worktrees/agent-*/`) — those are user-managed seed workspaces

---

## 3 · The mole's interface

### 3.1 · Single entry point: `scripts/mole.sh`

```bash
bash scripts/mole.sh scan             # all three scopes, read-only, JSON-ish report
bash scripts/mole.sh scan --artifacts   # only artifacts scope
bash scripts/mole.sh scan --environments
bash scripts/mole.sh scan --worktrees

bash scripts/mole.sh sweep            # dry-run by default; --force to act
bash scripts/mole.sh sweep --artifacts --force
bash scripts/mole.sh sweep --worktrees --force

bash scripts/mole.sh report           # machine-readable summary (next_action, sizes, counts)
```

### 3.2 · Default scopes per mode

| Mode | artifacts | environments | worktrees |
|---|---|---|---|
| `scan` (no flags) | ✓ read-only | ✓ read-only | ✓ read-only |
| `sweep` (no flags) | ✓ destructive | ✗ advisory-only (too risky) | ✓ destructive |

**Environments NEVER auto-sweep.** They're reported in `scan` but require explicit `--environments --i-know-what-im-doing` to act on. Reason: a wiped venv blocks the next dev session for ~30s of network install per product — high cost for low recovery.

### 3.3 · Severity grading (per scope)

Mirrors `disk-usage-monitor.sh` exit-code semantics:

| Severity | Threshold | Action |
|---|---|---|
| OK | <70% disk usage AND <5 stale worktrees AND <500 MB artifacts | informational |
| CAUTION | 70-79% OR 5-15 stale OR 500MB-2GB artifacts | suggest sweep |
| WARNING | 80-89% OR 15-30 stale OR 2-5GB artifacts | sweep recommended |
| CRITICAL | ≥90% OR ≥30 stale OR ≥5GB artifacts | sweep mandatory |

`next_action` field in the report names the highest-leverage scope to attack first.

### 3.4 · Safety constraints (NEVER violated)

1. **Never deletes uncommitted work** — checks `git diff --quiet` and `git diff --cached --quiet` before any destructive op.
2. **Never deletes the main worktree** — refuses to operate on `$REPO_ROOT` directly.
3. **Never deletes sibling workspaces** — paths NOT under `.claude/worktrees/agent-*/` are skipped.
4. **Never deletes unmerged branches** — `git merge-base --is-ancestor` OR `git cherry origin/main <branch>` must confirm reachability.
5. **Never deletes `.env` files** — they contain secrets; always in the deny-list.
6. **Never deletes migration files** — `products/*/backend/migrations/*.sql` always preserved.
7. **Always dry-run first when destructive** — `sweep` without `--force` only prints what would be removed.
8. **Always logs the action + size + reason** — output goes to `scripts/mole-last-sweep.log` (gitignored).

---

## 4 · Active triggers (the "active" part)

The mole runs **automatically** at three points in the workflow:

### 4.1 · Pre-dispatch (orchestrator-side)

Before any `Agent(isolation: "worktree")` call, the orchestrator runs `bash scripts/mole.sh scan` and reads the severity. If `next_action` returns `CRITICAL`, the orchestrator MUST sweep before dispatching (the new worktree would push us deeper into ENOSPC territory).

**Wired in**: orchestrator's continuous-flow dispatch routine — `mole.sh scan` is the gating call before parallel-engineer fanout.

### 4.2 · Pre-commit hook (repo-side)

`scripts/pre-commit` calls `bash scripts/mole.sh scan --artifacts` (cheap — only counts pycache/pytest_cache sizes). If artifact total exceeds **2 GB**, prints a `WARNING` to stderr (doesn't block the commit — just informs). The pre-commit's role is to surface bloat trending up, not block work.

### 4.3 · Bootstrap pre-flight (engineer-side)

`scripts/bootstrap-worktree.sh` already calls `cleanup-stale-worktrees.sh`. Migrate that call to `bash scripts/mole.sh sweep --worktrees --force` so the worktree-scope sweep happens automatically when each new engineer worktree is created. Effect: stale worktrees never accumulate across more than one dispatch cycle.

### 4.4 · Post-merge (orchestrator-side)

After `git push origin main` of a cherry-picked commit, the orchestrator MAY run `bash scripts/mole.sh sweep --worktrees --force` to immediately reclaim the just-merged engineer's worktree. Optional — bootstrap pre-flight catches it on next cycle anyway.

---

## 5 · The MCP exposure (future)

Three-segment dotted namespace mirroring `noctus.hound.*`:

- `noctus.mole.scan` — single entry point, runs trio, returns `{scope_findings, severity, next_action, total_reclaimable_mb}`
- `noctus.mole.scan_artifacts` — artifact-scope only
- `noctus.mole.scan_environments` — environment-scope only (read + advisory)
- `noctus.mole.scan_worktrees` — worktree-scope only
- `noctus.mole.sweep` — destructive trio (gated, force-required)

**MCP exposure is deferred to a follow-up engineer dispatch.** The script-level mole is the substantive deliverable; MCP exposure is the call-site convenience layer.

---

## 6 · Anti-patterns (the mole MUST refuse)

- **Recursive deletion at the repo root** — `rm -rf .` or `rm -rf .claude/` outside the worktrees subdir.
- **Wildcard sweeps** of user-content directories (`products/*/data/`, `archive/`, `KNOWLEDGE-BASE/`).
- **Touching `.git/`** beyond the worktree-prune call that `git worktree remove` does internally.
- **Auto-cleaning environments** without explicit user opt-in.
- **Skipping the dry-run gate** in interactive mode.
- **Silently swallowing errors** — failed removals MUST surface to stderr with the path + reason.

---

## 7 · How it differs from keeper + hound

| Dimension | Keeper | Hound | Mole |
|---|---|---|---|
| **Subject of attention** | Code (compliance contracts) | Code (hygiene patterns) | Filesystem (storage) |
| **Default action** | Observation-only (`--review`) | Read-only scan | Read-only scan |
| **Destructive mode** | Never (LLM authors proposals) | Never (architect/engineer authors changes) | Yes (gated by `--force`) |
| **Trio scopes** | LGPD / webhook-pin / auth-shape / etc. | absorption / fusion / optimization | artifacts / environments / worktrees |
| **Lives at** | `mcp/noctusai/tools/dev/compliance.py` | `mcp/noctusai/tools/noctus/seed/*.py` | `scripts/mole.sh` (+ future `mcp/noctusai/tools/noctus/mole/*.py`) |
| **Active triggers** | `pre-commit` (sync rules) | None (architect runs manually) | **Pre-dispatch + pre-commit + bootstrap** (this is the "active" part) |

The mole is the **only** member of the trio with built-in destructive authority. That asymmetry justifies the harder safety constraints in §3.4.

---

## 8 · Implementation phases

**Phase 1 (shipped 2026-05-11)** — script-level mole:
- `scripts/mole.sh` orchestrator
- `scripts/cleanup-stale-worktrees.sh` continues to exist; mole delegates worktree-scope to it
- KB pattern doc (this file)
- CLAUDE.md §1 bullet
- Memory entry `feedback_mole_storage_hygiene.md`
- `bootstrap-worktree.sh` calls `mole.sh sweep --worktrees --force`

**Phase 2 (deferred follow-up)** — active hooks:
- `scripts/pre-commit` calls `mole.sh scan --artifacts` and warns on bloat
- Orchestrator dispatch routine calls `mole.sh scan` as pre-flight gate

**Phase 3 (deferred follow-up)** — MCP exposure:
- `mcp/noctusai/tools/noctus/mole/scan.py` etc.
- Three-segment dotted naming
- Pydantic schemas
- Lazy `NoctusContext`

**Phase 4 (deferred)** — pnpm workspace migration:
- The mole's environment scope finds the structural waste; converting to pnpm workspace is the structural fix. Separate project.

---

## 9 · References

- §19 of `KB § PATTERNS/branching-and-merging.md` — worktree lifecycle methodology (worktree-scope predecessor)
- `feedback_worktree_auto_cleanup.md` + `feedback_disk_usage_monitor.md` — memory entries that motivated this
- `scripts/cleanup-stale-worktrees.sh` — worktree-scope implementation (mole delegates)
- `scripts/disk-usage-monitor.sh` — companion (prevention vs the mole's recovery)
- `KB § PATTERNS/seed-absorption.md § noctus.hound.scan` — hound metaphor parent

**Three-way-synced 2026-05-11**: this pattern doc + memory entry `feedback_mole_storage_hygiene.md` + CLAUDE.md §1 universal-rules new bullet.
