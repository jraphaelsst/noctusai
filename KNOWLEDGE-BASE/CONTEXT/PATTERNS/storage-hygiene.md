# Storage hygiene — the `mole` and the trio

> **TL;DR.** Third member of the regulatory/curatorial/custodial trio. Keeper guards laws, hound sniffs out hygiene, **mole burrows for storage waste**. Three orthogonal scopes — `artifacts` (regenerable caches/builds), `environments` (venv/node_modules duplication), `worktrees` (stale `.claude/worktrees/*` — any subdir, not just `agent-*`). Active by default: pre-dispatch + pre-commit + post-merge. **MCP-exposed** as `noctus.dev.mole` (`mode=scan|sweep`, `scope`, `force`); its worktree-scope merged-base + merged predicate is the **shared `tools/noctus/dev/_worktree_staleness.py` helper**, consumed identically by `noctus.dev.cleanup_stale_worktrees` (one source of truth — no parity drift). **Safe-gate:** `sweep` deletes only with `force=True`, and only merged-to-`dev` (SHA-ancestry|patch-id) worktrees + regenerable artifacts — never uncommitted/unmerged/main/sibling/`.env`/migration content; caller must also confirm no agent is mid-flight in a target worktree (scan → eyeball → force-sweep). Project cleanup is the separate `noctus.dev.archive`.

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

| Agent | Domain | Default mode | Single entry point | Three (or more) scopes |
|---|---|---|---|---|
| **Keeper** | Regulatory + hygiene compliance (any rule with a deterministic predicate) | `--review` observation-only | `noctus.dev.review` | **Regulatory:** LGPD / webhook 5-pin / auth-shape / status-assertion / slowapi-pep563 / etc. **Hygiene-compliance (added 2026-05-11):** archive staleness / dispatcher staleness / branch orphans / gitignore drift. |
| **Hound** | Curatorial (code hygiene) | `scan` (read-only) | `noctus.hound.scan` | absorption / fusion / optimization |
| **Mole** | Custodial (storage execution) | `scan` (read-only) | `noctus.mole.scan` | **artifacts / environments / worktrees** |

Each agent has **observation-only scan** (default) + **destructive sweep** (gated, dry-run-by-default).

**Note (2026-05-11):** the keeper now covers two compliance axes — *regulatory* (the original LGPD / webhook / auth shape) and *hygiene-compliance* (workspace state: archive / dispatcher / branch / gitignore). This expansion is documented in `KB § PATTERNS/methodology-codification-pipeline.md` — the keeper is **Stage 4** of the methodology codification pipeline, not a regulatory silo. Workspace-state rules that meet the codification criteria (deterministic predicate + recurrence ≥3 + clear remediation) belong in the keeper, not in a fourth identity. Mole stays as the **execution layer downstream** of keeper hygiene findings that touch the filesystem.

---

## 2 · The three orthogonal scopes

### 2.1 · Artifacts (regenerable caches + build outputs)

**Definition**: files/directories that build tools regenerate on demand. Safe-to-wipe — losing them just triggers a rebuild on next run.

**Patterns** (canonical list, lives in `noctus.dev.mole` as the artifact deny-list lookup-table):
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

### 2.3 · Worktrees (stale `.claude/worktrees/*`)

**Definition**: ANY worktree directory under `.claude/worktrees/` (an `agent-<id>` from Agent isolation OR a self-branch `feat/<slug>` from `task_branch` / a raw `git worktree add` — broadened 2026-05-25 from the old `agent-*`-only filter so self-branch worktrees can't fall through to a bare hand-`rm`; the merged + clean gate is the safety, not the name) whose branch is reachable from `origin/dev` by SHA ancestry OR patch-id equivalence (cherry-pick). Engineer worktrees fork from + integrate to the `dev` integration branch, NOT `main` (KB § PATTERNS/branching-and-merging.md § 0) — a merged-to-dev-but-not-yet-blessed-to-main worktree was never swept under the old `origin/main` keying.

This merged-base + merged predicate is the **shared `tools/noctus/dev/_worktree_staleness.py` helper** — the single source of truth consumed identically by both `noctus.dev.mole` (worktree scope) and `noctus.dev.cleanup_stale_worktrees`, so changing one can no longer drift the other.

**Patterns**:
- `.claude/worktrees/agent-<id>/` with branch SHA-merged to origin/dev (true merge)
- `.claude/worktrees/agent-<id>/` with branch commits all present on origin/dev by patch-id (cherry-pick — the gap §19 of branching-and-merging.md captures)
- Orphan dirs under `.claude/worktrees/agent-*/` that git doesn't recognize as worktrees (rm'd manually but metadata left) — orphan-detection stays `agent-*`-CONSERVATIVE (an unregistered dir has no branch ⇒ no merge gate); REGISTERED worktrees of any name sweep via the merge+clean gate

**Reversibility test**: is the work merged? Either:
- `git merge-base --is-ancestor <branch> origin/dev` ✓ → SHA-merged, safe to remove
- `git cherry origin/dev <branch>` empty `^+` lines ✓ → patch-id merged, safe to remove
- Both fail → UNMERGED, do NOT remove (active work, cherry-pick pending, or stalled engineer)

**Lock detection + "resolve before sweep"**: `git worktree list --porcelain` reports `locked` flag. Cleanup script's `git worktree remove --force` (single force) does NOT break locks. **The mole NEVER auto-`-f -f` past a lock** — locks exist because another process is using the dir (active agent, stale lock, recovery handle). Force-removing a lock could destroy uncommitted work, stashes, or inflight artifacts the agent hadn't yet committed.

**Instead**, the mole **surfaces locked-stale worktrees as UNRESOLVED findings** with a diagnosis (uncommitted-files / stashes / clean-locked) and a per-case resolution recipe. The user (or architect) decides whether to act. The "resolve" step is:
1. Inspect the worktree (`cd <path> && git status` + `git stash list`)
2. Recover anything valuable (`git stash push` or `git checkout` what you need)
3. `git worktree unlock <path>` (only after verifying nothing is using it — `lsof <path>` or PID check)
4. `git worktree remove <path>` (single force suffices once unlocked)

This matches the **keeper observation-only contract**: detect + report + recommend; never destroy without explicit user action.

**Dead-pid lock auto-unlock (THE-P11 fix, 2026-05-12).** The bootstrap script locks each worktree with `locked claude agent agent-... (pid N)`. The lock survives the process — a crashed Claude session leaves stale locks behind that prevent `git worktree prune` and `git worktree remove` from cleaning the entry forever. The mole now parses the pid from the lock line at scan time, runs `kill -0 <pid>` to test process liveness, and **auto-unlocks if the pid is dead**. The lock metadata is decoupled from a process that no longer exists; preserving it serves no safety purpose. This is bounded to *dead* pids — locks held by a live process are untouched (the safety constraint still holds). Without this fix, the 2026-05-12 incident left 151 phantom-locked entries that mole counted as unsweepable.

**Shared-stash false positive (THE-P11 fix, 2026-05-12).** Linked worktrees share `refs/stash` with the main repo — `git stash list` inside an engineer worktree reports the SAME stashes that exist in main. The naive `wc -l` count credited each linked worktree with N "stashes" (where N was usually 10, the main repo's stash count from accumulated parallel-agent rescue captures). Mole's `STALE_DIRTY` guard then refused to sweep, on the (false) assumption that those stashes were recoverable WIP unique to the worktree. The fix subtracts main's stash commit-hash set from each worktree's set; only stashes UNIQUE to the worktree count as recovery-required WIP. Effect on the 2026-05-12 incident: 65 surviving worktrees had `unique_stash_count == 0` → would have classified as STALE (sweepable), not STALE_DIRTY.

#### Learn/extract-before-delete — the worktree analogue of `archive`'s learn-before-archive (2026-05-25)

**A worktree being deleted is the worktree analogue of a project being archived** — and it suffers the **identical drift**: important content lost on removal. Project-archiving fixed this with an **extraction step** (`noctus.dev.archive` = *learn-before-archive, never deletion*: extract learnings → KB/memory, record provenance in the **tracked** `project-history/ledger.ndjson`, refuse if a tracked surface still points in). Worktree salvage MUST mirror it. We re-hit the drift 2026-05-25: a manual salvage dumped recovery to `~/noctus-worktree-salvage-<date>/` (out-of-repo) — a **transient net, NOT a durable home** (it gets deleted/forgotten exactly like a pre-extraction archive).

Before removing a worktree/branch carrying **unique committed work OR uncommitted diffs** (the merged-clean majority needs none — their content is already on `dev`), run the extraction, the three legs mirroring `archive`:
1. **Learnings → codification pipeline.** Any reusable knowledge in the work (a pattern, fix, gotcha, recurrence) lands in its durable home (KB / memory / `findings.md`, s1→s4) BEFORE the worktree is gone — same contract as learn-before-archive. *Appended ≠ extracted*: a transient `.diff` is recovery, not a learning.
2. **Recovery record → a TRACKED ledger.** The deleted worktree/branch SHAs + one-line provenance land in a **repo-tracked** salvage record so recovery survives the salvage-dir's deletion — the worktree analogue of `project-history/ledger.ndjson` (target: `project-history/worktree-salvage.ndjson`). Out-of-repo `.diff` patches stay a *transient convenience*, never the sole record.
3. **Durable-refs gate.** Do not delete a worktree/branch whose unique work a tracked surface still depends on (mirror `archive`'s refuse-if-referenced gate).

Merged-clean sweep is extraction-no-op for the *learnings* leg (content already on `dev`) — but the **recovery-record leg fires on every removal**. **Status (built 2026-05-25):** leg 2 is now **mechanical on ALL THREE sanctioned removal paths** — `mole sweep` (worktree scope) + `cleanup_stale_worktrees` (the bulk sweeps) **+ `task_branch action='cleanup'`** (the precise single-worktree teardown, incl. the architect's post-merge engineer-worktree cleanup) all record each removed worktree's recovery pointer (branch + SHA + provenance) to the tracked `project-history/worktree-salvage.ndjson` via the shared `tools/noctus/dev/_worktree_salvage.py` helper (one source of truth, mirroring the `_worktree_staleness` shared-predicate pattern; the caller commits the ledger, exactly like `ledger.ndjson`). Returned as `salvaged` + `salvage_ledger` (`cleanup_stale_worktrees`) / `salvage_ledger` (`task_branch cleanup`); surfaced in `mole` notes. **`task_branch cleanup` records the pointer BEFORE the destructive `worktree remove`** (a remove failure can't lose it) and SURFACES the learnings checkpoint (`learnings_checkpoint` + `cleanup_ritual`) + sequences a **mole worktree-sweep before the delete** (storage-hygiene leg). Leg 1 (*learnings* → codification) stays discipline (needs judgment) but is now **surfaced at every teardown** (the checkpoint), not silent. Leg 3 (durable-refs gate) is the existing classifier safety gate (never removes unmerged/dirty).

**🔴 The one path that still skips all three legs: a bare `git worktree remove` typed by hand** (NOT through a tool). The architect's post-merge cleanup MUST go through `task_branch cleanup` (or `mole sweep` / `cleanup_stale_worktrees`) — never a raw `git worktree remove` — or the learnings + recovery pointer are silently lost. This was the 2026-05-25 drift: an engineer worktree (`feat/sw-frontend-verify`) was removed by hand right after merge ⇒ no ledger entry, no learnings extracted until retroactively salvaged. The salvage ritual ORDER at teardown: **(1) extract learnings → KB/memory → (2) record recovery pointer → (3) mole worktree-sweep → (4) remove.** Sibling: `KB § PATTERNS/project-execution.md` (learn-before-archive) · `01-PHILOSOPHY.md § Durable docs are self-contained` · `KB § PATTERNS/branching-dispatch.md` (the architect's merge→cleanup step) · `KB § PATTERNS/self-branching-mode.md § cleanup`.

**Operational gaps surfaced by dogfooding the mechanism (2026-05-25)** — running the salvage-before-delete clean against the very session that built it exposed three rough edges (each fixed ∨ doc'd; the dogfood *is* the methodology working):
- **G1 · reused/renamed worktree dir ≠ `feat/<slug>` (FIXED in code).** `task_branch cleanup` keys on the dir but *derived* the branch as `feat/<slug>`. A worktree whose dir name had diverged from its branch (dir `sw-waha-youtube` on branch `feat/salvage-before-delete` — a reused worktree) made `head` resolve to a **nonexistent** branch ⇒ the recovery-pointer leg **silently no-op'd** (`if head:` falsy) and `branch -d` failed — the mechanism skipping its own salvage on exactly that worktree state. Fixed on contact: cleanup now resolves the **ACTUAL** branch from `git worktree list --porcelain` keyed by the dir (`_branch_for_path`, falls back to `feat/<slug>`); regression test `test_cleanup_resolves_actual_branch_for_reused_worktree_dir`.
- **G2 · a just-codified MCP mechanism isn't LIVE until (a) its code is on the PRIMARY checkout ∧ (b) the MCP server restarts.** The salvage code shipped to `origin/dev`, but the running server loads tools from the primary tree (which was *behind* `origin/dev`) ⇒ MCP `task_branch cleanup` would run the pre-mechanism code. To exercise a fresh tool change: FF the primary to `origin/dev`, then restart the MCP server — or drive it via a fresh-process CLI (`--mole sweep` / `--cleanup-stale-worktrees` reload current code each invocation and already carry the mechanical leg). Sibling of [[dev-prod-parity]] (codebase-is-source-of-truth applies to the *running tool*, not just the file).
- **G3 · ledger-commit home vs never-work-on-dev.** `record_sweep` writes the append to its `root` and returns the path for the **caller to commit** (like `ledger.ndjson`); via MCP `root` = the primary `dev` tree, where committing would violate never-work-on-dev. Resolution: the caller commits the append from a **self-branch worktree** (FF-push to dev); the **terminal** worktree's own removal-record (the last removal — no surviving worktree to host its ledger line) is committed as a bookkeeping FF-push **only when the primary is verified clean+idle** (no peer), else it rides the next self-branch integrate. The `primary_root`/`salvage_recorder` seams are **test-injection only** (not exposed on the MCP wrapper) ⇒ redirecting the ledger cross-tree is a fresh-process move, not an MCP one. **Corollary — a single idle self-branch worktree at the `dev` tip is an expected steady state, not debt** (the terminal-worktree ledger-home property).
- **G4 · a `wire_env`'d worktree was un-removable by the mechanism (FIXED at root).** `task_branch start wire_env=True` (the L3 lever) symlinks `node_modules` into each product/seed frontend; the `.gitignore` pattern was `node_modules/` (trailing slash ⇒ **directories only**), so the symlink-to-dir form leaked as **untracked** ⇒ `git worktree remove` (the cleanup's remover) refused as "dirty" — and `--force` is a **banned token** (force is structurally impossible in this tool), so the mechanism could not tear down its own wire_env'd worktree. Root fix: `.gitignore` `node_modules/` → `node_modules` (no slash matches dirs *and* symlinks) ⇒ the symlinks are ignored, the worktree is clean, `git worktree remove` succeeds with no force needed. (Bonus: also stops an accidental `git add` from staging a symlink.) The cleanup code is unchanged — the artifact simply shouldn't have leaked.
- **G5 · the salvage tools don't cover sibling-path or staleness-unclassified worktrees.** `mole sweep` / `cleanup_stale_worktrees` only act on worktrees their staleness classifier flags (4 merged-but-recently-touched leftovers scored `STALE=0`) **and** skip sibling-path worktrees (outside `.claude/worktrees/`, e.g. `../noctus-fleet`); `task_branch cleanup` assumes `.claude/worktrees/<slug>`. So an idle-but-unclassified ∨ sibling worktree must be torn down **manually** — but still **salvage-first, never bare**: verify content-on-dev (∨ extract), record the recovery pointer via the shared `_worktree_salvage.record_sweep` helper, THEN `git worktree remove`. The "never bare `git worktree remove`" anti-pattern means *never skip salvage* — a manual remove **after** the legs are complete (because no tool covers the case) is the sanctioned fallback, not a violation. (2026-05-25 housekeeping: 4 leftovers torn down this way — `../noctus-fleet`@`fleet/build-isolated` was UNMERGED but every commit + the uncommitted `app.py` `is_api_or_ops` guard was **verified semantic-dup-on-dev** before a `branch -D`; the recovery pointers + this learning were committed as a terminal-bookkeeping FF-push under user-confirmed no-active-peers.)

**Anti-patterns**:
- **A bare hand-typed `git worktree remove` to tear down a worktree** — bypasses ALL THREE salvage legs (no recovery pointer, no learnings checkpoint, no mole sweep). Always go through `task_branch cleanup` / `mole sweep` / `cleanup_stale_worktrees`. (The 2026-05-25 architect-post-merge drift.)
- **Salvaging only to an out-of-repo dir** (`~/…-salvage-*/`) and calling it done — that's the transient net, not the durable extraction; learnings + a tracked recovery record must land first (the 2026-05-25 re-drift).
- Removing a worktree whose branch has UNMERGED commits — loses the engineer's work
- Removing the main worktree (the repo root itself)
- Removing sibling workspaces (paths NOT under `.claude/worktrees/`) — those are user-managed seed workspaces
- **`git worktree remove -f -f` (double force) as automation** — bypasses the lock check that was put there for a reason. Use only after manual verification.
- **Auto-removing locked-stale worktrees on the assumption that "lock == stale"** — a lock can be active. Always diagnose before destroying.

### 2.4 · Docker images (obsolete product/stock images)

**Definition**: docker images on the local daemon that are no longer needed — either superseded products no longer in the active set, or stock images unrelated to the current platform stack.

**Patterns** (canonical list, lives in `noctus.dev.mole` as the docker-image deny-list lookup-table):
- `ghcr.io/jraphaelsst/noctus-<slug>:dev` where `<slug>` is NOT the active product the user is working on AND no container is currently running on it
- Stock images NOT referenced by any compose file in the repo: `nginx:alpine` (no current adopter), `alpine:latest` (rarely used), `cloudflare/cloudflared:latest` (only for tunnels, easy re-pull), `aquasec/trivy:*` (CI scanner, easy re-pull), unused n8n/redis/postgres untagged-latest copies when a pinned version exists
- Old versions of base/runtime images when a newer same-purpose tag exists (e.g. `devlikeapro/waha:arm` when `devlikeapro/waha:latest` is what compose actually pulls)

**Reversibility test**: would the image be re-pulled or re-built from a known recipe? Stock images → `docker pull` returns them. Product images → `docker compose up -d --build <slug>` re-bakes from the canonical Dockerfile. Both are recoverable; deletion is low-risk for non-active products.

**Protected (NEVER delete — the "really important" set)**:
- `noctus-seed-{backend,frontend}-base:dev` — every product Dockerfile FROMs them; deleting these breaks every product build until rebuilt
- The image of any container currently `docker ps` running (in-use refcount)
- Stock images referenced by the active compose files (`postgres:16-alpine`, `redis:7-alpine`, `devlikeapro/waha:latest` if compose pulls that tag, `python:3.11-slim`, `node:20-alpine` — the Dockerfile FROM bases)
- `docker/dockerfile:1.7` — used by `# syntax=` directives in Dockerfiles

**Detect command**:
```bash
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}'
docker ps --format '{{.Image}}'   # what's actively used; protect these
```

**Anti-patterns**:
- `docker rmi -f noctus-seed-*-base:*` — breaks every product build downstream
- `docker image prune -a -f` without first listing — too aggressive; removes anything not currently tagged-and-in-use, including stock images that compose just hasn't pulled yet in this session
- Deleting an image while its container is stopped (not running) — losing the image means the container can't restart without a full rebuild

### 2.5 · Docker volumes (orphans from past stacks)

**Definition**: docker volumes on the local daemon that no running container has mounted, and that aren't named-state for a still-relevant compose stack.

**Patterns**:
- Anonymous (hex-named) volumes with no parent container — residue from `docker rm` of containers that had anonymous mounts (e.g. each `up --build` recreate of a product container leaves the previous anonymous FE-node_modules volume behind)
- Named volumes from closed/absorbed projects (e.g. `whatsapp-google-scheduling_*` after the absorption into social-wiring; `chatbot-docker_*` after the chatbot-docker stack was deprecated; `bookstore_*` from an unrelated experiment)
- Stock-image-named volumes (e.g. `redis-data` of an old `redis:latest` when the current stack pins `redis:7-alpine` with `dev-noctusai-infra_redis_data`). NOTE: the old `noctusai-infra_postgres_data` is one such orphan — local Postgres was removed 2026-05-25, so any leftover `*_postgres_data` from this stack is now safe to drop.

**Reversibility test**: does any active compose file reference this named volume? `grep -rn "<volume-name>" docker-compose*.yml products/*/docker-compose.yml`. If no match AND no running container mounts it → orphan, safe to remove.

**Protected (NEVER delete — production state, the "really important" set)**:
- `dev-noctusai-infra_redis_data` — Redis state (cache, queues, dedup keys)
- `dev-noctusai-infra_waha_sessions` — WAHA WhatsApp session state (linked accounts; losing this forces re-pairing every WhatsApp connection)
- Any anonymous volume mounted by a currently-running container (typically a product FE's `node_modules` arm64 isolation volume)
- Any named volume referenced by a compose file in the active set

**Detect command**:
```bash
docker volume ls --format '{{.Name}}'
docker ps -q | xargs -I{} docker inspect {} --format '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{println}}{{end}}{{end}}'
# Volumes in the first list MINUS volumes in the second list = candidates
```

**Sweep approach**:
- `docker volume prune -f` removes ALL unused (anonymous + named-but-unmounted). Use when the named-unused set is already confirmed-orphan.
- `docker volume rm <name>` is the surgical form when only specific named volumes should drop.

**Anti-patterns**:
- `docker volume prune -af` (the `-a` adds local volumes too — same as `-f` for local-driver volumes, but the flag is misleading and inconsistent across daemon versions)
- Deleting `dev-noctusai-infra_waha_sessions` — every WhatsApp number must re-pair via QR scan
- Pruning while a container is stopped (not running) — the named volume isn't refcounted-protected; deletion is permanent

---

## 3 · The mole's interface

### 3.1 · Single entry point: `noctus.dev.mole`

```bash
python mcp/noctusai/cli.py --mole scan             # all three scopes, read-only, JSON-ish report
python mcp/noctusai/cli.py --mole scan --artifacts   # only artifacts scope
python mcp/noctusai/cli.py --mole scan --environments
python mcp/noctusai/cli.py --mole scan --worktrees

python mcp/noctusai/cli.py --mole sweep            # dry-run by default; --force to act
python mcp/noctusai/cli.py --mole sweep --artifacts --force
python mcp/noctusai/cli.py --mole sweep --worktrees --force

python mcp/noctusai/cli.py --mole report           # machine-readable summary (next_action, sizes, counts)
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
3. **Never deletes sibling workspaces** — paths NOT under `.claude/worktrees/` are skipped.
4. **Never deletes unmerged branches** — `git merge-base --is-ancestor` OR `git cherry origin/dev <branch>` must confirm reachability (the shared `_worktree_staleness` predicate).
5. **Never deletes `.env` files** — they contain secrets; always in the deny-list.
6. **Never deletes migration files** — `products/*/backend/migrations/*.sql` always preserved.
7. **Always dry-run first when destructive** — `sweep` without `--force` only prints what would be removed.
8. **Always logs the action + size + reason** — output goes to `scripts/mole-last-sweep.log` (gitignored).

---

## 4 · Active triggers (the "active" part)

The mole runs **automatically** at three points in the workflow:

### 4.1 · Pre-dispatch (orchestrator-side)

Before any `Agent(isolation: "worktree")` call, the orchestrator runs `python mcp/noctusai/cli.py --mole scan` and reads the severity. If `next_action` returns `CRITICAL`, the orchestrator MUST sweep before dispatching (the new worktree would push us deeper into ENOSPC territory).

**Wired in**: orchestrator's continuous-flow dispatch routine — `mole.sh scan` is the gating call before parallel-engineer fanout.

### 4.2 · Pre-commit hook (repo-side)

`scripts/hooks/pre-commit` calls `python mcp/noctusai/cli.py --mole scan --artifacts` (cheap — only counts pycache/pytest_cache sizes). If artifact total exceeds **2 GB**, prints a `WARNING` to stderr (doesn't block the commit — just informs). The pre-commit's role is to surface bloat trending up, not block work.

### 4.3 · Bootstrap pre-flight (engineer-side)

`scripts/bootstrap/bootstrap-worktree.sh` already calls `cleanup-stale-worktrees.sh`. Migrate that call to `python mcp/noctusai/cli.py --mole sweep --worktrees --force` so the worktree-scope sweep happens automatically when each new engineer worktree is created. Effect: stale worktrees never accumulate across more than one dispatch cycle.

### 4.4 · Post-cherry-pick (orchestrator-side) — **MUST**, not MAY

After every successful cherry-pick + push of an engineer's branch to `main`, the orchestrator MUST immediately remove the source worktree + delete the branch:

```bash
git worktree unlock "<source-worktree>" 2>/dev/null
git worktree remove --force "<source-worktree>"
git branch -D "<source-branch>"
```

Strengthened from MAY → MUST on 2026-05-12 after the THE-P11 incident (150+ worktrees accumulated despite bootstrap pre-flight and pre-dispatch triggers because mole's stash-shared false positive blocked them from being eligible — see §2.3). Eliminating accumulation at the cherry-pick boundary is the most reliable trigger; it doesn't depend on mole's classification reaching the right decision.

The cleanup belongs in the orchestrator playbook (operator side when split per `KB § PATTERNS/two-session-architect-operator.md`; architect side in single-session mode). Cherry-pick that doesn't cleanup the source worktree is incomplete work.

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
| **Lives at** | `mcp/noctusai/tools/dev/compliance.py` | `mcp/noctusai/tools/noctus/seed/*.py` | `noctus.dev.mole` (+ future `mcp/noctusai/tools/noctus/mole/*.py`) |
| **Active triggers** | `pre-commit` (sync rules) | None (architect runs manually) | **Pre-dispatch + pre-commit + bootstrap** (this is the "active" part) |

The mole is the **only** member of the trio with built-in destructive authority. That asymmetry justifies the harder safety constraints in §3.4.

---

## 8 · Implementation phases

**Phase 1 (shipped 2026-05-11)** — script-level mole:
- `noctus.dev.mole` orchestrator
- `noctus.dev.cleanup_stale_worktrees` continues to exist alongside mole's own worktree classifier (originally framed as "mole delegates worktree-scope to it"; **2026-05-24** both were refactored to consume the shared `_worktree_staleness` merged-base + merged predicate — no delegation, one source of truth)
- KB pattern doc (this file)
- CLAUDE.md §1 bullet
- Memory entry `feedback_mole_storage_hygiene.md`
- `bootstrap-worktree.sh` calls `mole.sh sweep --worktrees --force`

**Phase 2 (deferred follow-up)** — active hooks:
- `scripts/hooks/pre-commit` calls `mole.sh scan --artifacts` and warns on bloat
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
- `noctus.dev.cleanup_stale_worktrees` — sibling worktree-cleanup tool; shares the `tools/noctus/dev/_worktree_staleness.py` merged-base + merged predicate with mole's worktree scope (one source of truth)
- `noctus.dev.check_disk_usage` — companion (prevention vs the mole's recovery)
- `KB § PATTERNS/seed-absorption.md § noctus.hound.scan` — hound metaphor parent

**Three-way-synced 2026-05-11**: this pattern doc + memory entry `feedback_mole_storage_hygiene.md` + CLAUDE.md §1 universal-rules new bullet.
