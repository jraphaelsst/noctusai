# Self-branching mode — per-task worktree isolation for peer terminal-agents

> **Front-door.** The *solo* mode of the unified [[branching]] methodology (the §0 primitive at scale = 1). Read [[branching]] first for the decision spine, the worktree-sensitivity map, and the known-errors bump catalog; this doc is the solo-mode depth.

> **One-liner.** When a terminal-agent is assigned a **writing** task, it **self-isolates** by default: do the work in a per-task `git worktree` forked from `origin/dev`, integrate straight to `origin/dev`, tear the worktree down, return to idle — **without ever switching the shared primary checkout's branch out from under a sibling**. Automatic (no "branch this" keyword), one `noctus.dev.task_branch` lifecycle call per stage.
>
> **The governing frame.** In a multi-terminal world (N agents in N terminals on the **same workspace/checkout** — e.g. several terminals in one Antigravity window) there is **no single architect on top**. Every terminal-agent is a **peer**, and a peer **cannot cheaply know whether a sibling is active in the same checkout**. So the safe default is **assume peers always exist ⇒ self-isolate every writing task**. This is the *unconditional* generalization of [[branching-and-merging]] §9a (which isolates only *when* a second agent is known active). Born 2026-05-24 (user: *"every task i ask you to do, you branch yourself on a branch separate from dev … after finalizing and pushing the branch to dev, agents switch back to dev and await for next branch dispatch"*).

---

## 1. The trigger — write-vs-read (NOT size)

The trigger axis is **"will this task produce committable changes?"** — *not* task size.

| Task class | Mode |
|---|---|
| **Writing** — edits code / docs / config (any size, even 1 line) | **Self-branch** — always. The driver is **collision-safety across terminals**, not effort: even a 1-line edit collides if two agents share one checkout. |
| **Read-only / conversational** — "explain X", "what does Y do", design/architecture discussion, a pure query | **Stay on `dev`** — no branch. Branching for a read is pure overhead. |

> **⚠ Distinct axis from the [[branching-and-merging]] §18.2.1 inline cutoff.** The inline cutoff is **size-based** (`<100 LoC ∧ <3 files` ⇒ architect does it *without dispatching a subagent*). Self-branching is **binary on write-vs-read** and is **orthogonal**: a tiny inline writing task **still self-branches** (it's collision-safety, not dispatch economics). Do **not** reuse the word "inline" for this mode — `inline` = "no dispatch"; this is "self-isolate." Two different decisions.

---

## 2. Why a shared checkout *forces* worktrees (the physics)

A single git working directory has exactly **one `HEAD`** — one branch checked out at a time. N agents sharing one checkout **cannot** each be on their own branch: the moment agent B runs `git switch B`, agent A's files on disk become B's — A's work vanishes mid-flight. That is the literal [[branching-and-merging]] §9a *"2-days-of-chaos"* failure. So the mode's substrate is **mandatory**:

- **`git worktree`** — one `.git` object store, N separate working dirs each with its own `HEAD`/branch. Cheap, shares objects. **This is what self-branching uses.** Worktrees live under `.claude/worktrees/<slug>` (gitignored; bulk-swept by [[storage-hygiene]] / `noctus.dev.cleanup_stale_worktrees`).
- *(separate clones — heavier; coordinate via `origin/dev` only. Not the default.)*

The shared primary checkout **stays on `dev`** as the idle baseline; active work never happens *in* it.

---

## 3. Branch model + the engineer/peer boundary

Self-branching sits **on top of** the sacred-`main` model ([[branching-and-merging]] §0) — it changes *who isolates and when*, not the branch roles.

- **`main` / `prod` are off-limits** to everyday work entirely; they move only via the consent-gated `dev→main` (bless) + `main→prod` (promote) gates (`noctus.dev.release`).
- **Engineers** (dispatched subagents) **commit/stage ONLY on their own worker branch** — they **never merge, switch, or touch `dev`, `main`, OR `prod`.** All integration is the architect's job. *(The `prod` clause was previously implicit — made explicit 2026-05-24 alongside this mode.)*
- **A peer terminal-agent in self-branching mode acts as the architect of its own task** — so it MAY integrate *its own* worktree branch to `dev` (`integrate` below). If a peer-agent itself **dispatches** engineers for a sub-task, those engineers stay on their own sub-branches and the peer-agent (as their architect) integrates — the model **nests** cleanly.

So integration to `dev` is done by an **architect** — either the lone architect of a dispatch, or a peer-agent-as-its-own-architect. Engineers never push anywhere.

---

## 4. The lifecycle — `noctus.dev.task_branch`

Four actions. Writes are **DRY-RUN by default → `confirm=True` executes**; `status` is always read-only. (The agent passes `confirm=True` itself when ready — the gate is a safety review point, not user friction.)

```
# on a WRITING task assignment (automatic — no keyword needed):
noctus.dev.task_branch action="start" slug="<task-slug>" confirm=True
#   → git fetch origin
#   → git worktree add .claude/worktrees/<slug> -b feat/<slug> origin/dev
#   → cd .claude/worktrees/<slug>   ← the agent works HERE, isolated

# ... do the work; commit on feat/<slug> (explicit-path git add, own files only) ...

noctus.dev.task_branch action="integrate" slug="<task-slug>" confirm=True
#   → fetch → rebase onto origin/dev → FF-push HEAD → origin/dev
#   → on the concurrent-push race (non-FF): fetch, rebase, RETRY (≤5)
#   → on a rebase CONFLICT: abort (worktree restored clean) + surface loudly — never auto-resolve

noctus.dev.task_branch action="cleanup" slug="<task-slug>" confirm=True
#   → git worktree remove (refuses if dirty — no --force) → prune → git branch -d feat/<slug> (merged-only)
#   → agent idle on the dev baseline; next writing task re-fetches + re-branches

noctus.dev.task_branch action="status"   # read-only: active self-branch worktrees + ahead/behind vs origin/dev
```

This realizes the user's `dev → branch.commit/push → dev` lifecycle, done collision-safely.

### 4.1 The integrate mechanic — `origin/dev` is the only integration site

Under one shared checkout the primary tree must **never** be the integration site (switching its `HEAD` is the collision). So the worktree integrates **straight to `origin/dev`**, never touching the shared local `HEAD`:

```
git fetch origin
git rebase origin/dev          # replay my task commits on the latest tip   (in the worktree)
git push origin HEAD:refs/heads/dev   # FF-push my commits straight to remote dev
  └─ rejected (a peer FF'd dev first)? → fetch; rebase origin/dev; retry
```

This is **exactly [[branching-and-merging]] §10.2 Option A** with `dev` substituted for the integration ref. The concurrent-push race **self-heals** via fetch→rebase→retry (standard distributed-git). Pushing only the task branch's own commits respects *commit-only-your-own-work* (the branch forked from `origin/dev`, so it carries nothing but this task's work). **Pushes only ever target `dev`** — the tool refuses any refspec to `main`/`prod` by construction.

### 4.2 Safety (the tool enforces, tests assert)
- Safe git allowlist; **no banned token** (`reset`/`checkout`/`switch`/`restore`/`clean`/`merge`/`--force`/`--force-with-lease`/`-f`/`-D`) ⇒ can't force, reset, rewrite history, or switch the primary checkout.
- **Dev-only push boundary** — every push dst MUST be `dev`; main/prod refused structurally; `NOCTUS_ALLOW_MAIN_PUSH` never set (this tool can't reach the sacred lines).
- `cleanup` refuses a **dirty** worktree (no `--force`) ∧ refuses an **unmerged** branch (`-d` not `-D`) ⇒ never silently drops unintegrated work.
- Rebase conflict ⇒ **abort + surface** (no silent auto-resolve, no half-rebase left behind).

---

## 5. Multi-terminal / Antigravity note

Each peer-agent's edits land **on disk in its worktree** (`.claude/worktrees/<slug>/…`), not in the primary tree the IDE editor shows. Trade-off: the user won't *see* a peer-agent's edits live in the primary editor unless they open the worktree dir — but the work is correct and lands on `dev` at integrate. This is the price of collision-safety under a shared checkout; it is the right default (the alternative — editing the shared tree — is the §9a hazard).

---

## 5a. Verifying builds/tests in a fresh worktree (the env recipe)

A fresh worktree is a clean git checkout — `node_modules/`, `.venv/`, and seed-version stamps are **gitignored, so they are ABSENT**. `noctus.dev.vite_build`/`noctus.dev.pytest` (MCP) run against the **primary** tree, not the worktree — so to verify *your worktree's* changes before integrate, wire the env in (all gitignored ⇒ never staged):

**Frontend (vite build / vitest):** symlink the PRIMARY's per-package `node_modules` into the worktree, then **re-point the `file:` local deps to the WORKTREE copies** so your lib edits are seen:
```
PRIMARY=/Users/rapha/Documents/repository/NoctusAI/noctusai ; WT=$PRIMARY/.claude/worktrees/<slug>
ln -sfn "$PRIMARY/products/<slug>/frontend/node_modules" "$WT/products/<slug>/frontend/node_modules"
ln -sfn "$PRIMARY/seed/lib/frontend/node_modules"        "$WT/seed/lib/frontend/node_modules"
ln -sfn "$PRIMARY/seed/framework/frontend/node_modules"  "$WT/seed/framework/frontend/node_modules"
ln -sfn "$WT/seed/lib/frontend"       "$WT/products/<slug>/frontend/node_modules/@noctusai/lib"
ln -sfn "$WT/seed/framework/frontend" "$WT/products/<slug>/frontend/node_modules/@noctusai/seed"
( cd "$WT/products/<slug>/frontend" && npx vite build )   # the product-FE CI gate (esbuild — compiles, no typecheck)
```
The `@noctusai/{lib,seed}` re-point is the crux: the symlinked `node_modules/@noctusai/lib` otherwise points at the PRIMARY lib, so your worktree lib changes are invisible to the build.

**Backend (pytest):** the seed backend has no per-product venv; use the PRIMARY root `./venv` (it carries the deps) + put the framework + lib on `PYTHONPATH` (conftest only adds the lib):
```
PYTHONPATH="$WT/seed/framework/backend:$WT/seed/lib/backend" "$PRIMARY/venv/bin/python" -m pytest products/<slug>/backend/tests/ -q
```
MCP-toolkit tests: `"$PRIMARY/mcp/noctusai/.venv/bin/python" -m pytest tests/ -q` run from `$WT/mcp/noctusai` (cwd selects the worktree's files).

**Known worktree-env caveats (codified breadcrumbs):** (a) the lib's *vitest render* tests dual-React-fail in a symlinked worktree — pre-existing, **not CI-gated** (lib CI gate is `tsc`); see [[reference_lib_frontend_vitest_render_harness_gap]]. (b) Seed-version-stamp critical false-positives in compliance scans (stamp gitignored/absent) — scope the scan or copy the stamp. (c) `noctus.dev.scan_wiring` may not be live as an MCP tool in a long-running session (no CLI flag yet); call the pure `analyze_*`/`scan_wiring()` functions directly. **Fallback when env-wiring is too fragile: author in the worktree, let the architect build-verify on the primary at integrate** (the documented verify-on-integrate path). **Automated:** `noctus.dev.task_branch action=start wire_env=True` now auto-wires this recipe AFTER the worktree exists — it symlinks the PRIMARY tree's per-package `node_modules` in + re-points each `products/<slug>/frontend/node_modules/@noctusai/{lib,seed}` at the WORKTREE's seed copies, reports `wired`/`skipped`, honors dry-run (reports `would_wire` without `confirm`), and is best-effort (missing primary `node_modules` / a real `node_modules` already in the worktree are reported in `skipped`, never clobbered). All target paths are gitignored ⇒ never staged.

---

## 5b. Cross-tree hazards under LIVE peers — the worktree isolates Edits, not the tooling

A worktree perfectly isolates your **Edits**. It does NOT, by itself, isolate **tooling** or the **shared `dev` ref**. Two hazards bit us 2026-05-25 (`social-wiring-waha-youtube`) *even though the worktree was correct* — so "I branched but still collided with the peer" is a real, recurring failure, and here is its anatomy:

**(a) MCP-fixed-CWD crossing.** `noctus.dev.*` MCP tools run from the **PRIMARY checkout's CWD**, not your worktree ([[feedback_harness_cwd_resets_to_primary]] / MCP-fixed-CWD). A git-**mutating** MCP tool — `task_branch action='integrate'` — therefore operates partly on the **primary tree**; if a peer has uncommitted work there, its rebase **leaks the peer's uncommitted files into your worktree** and aborts with an empty `conflicted_files`. → **Rule:** under a live peer, do git **mutations** worktree-explicitly — integrate with a direct ref-only push: `git -C <wt> fetch origin && git -C <wt> rebase origin/dev && git -C <wt> push origin HEAD:dev` (NOT the MCP `integrate` wrapper). `task_branch` **`start`** is safe (it only `git worktree add`s a fresh checkout); **`integrate`** is the CWD-crossing one — prefer the manual ref-only push until the tool is made `git -C`-aware. Reads/scans are fine **only with** `worktree_path=` (e.g. `scan_wiring`).

**(b) Peer-on-primary makes the primary tree "hot".** The collision needs TWO conditions: a peer with uncommitted work in the primary checkout AND a tool that crosses into it. Remove the first: **everyone worktrees — nobody parks WRITES on the primary `dev` checkout.** The primary stays clean/idle as the integration anchor; *every* agent (including the one that "feels like the main session") works in its own `.claude/worktrees/<slug>`. A peer editing the primary tree directly is the §9a sin wearing a different hat.

**(c) `dev` integration is a shared-ref RACE.** With N active agents `origin/dev` moves under you (it moved 3× in one session: 5755947a→01ea5bf0→8060cbf4→4c629672). Integrate is therefore *always* fetch→rebase-onto-latest→FF-push, **retry on non-FF** — never `--force`. A clean rebase (no file overlap) is the norm; a true conflict is abort+surface.

> **"Can two agents branch in parallel in the same workspace?"** — **YES**, that is exactly what worktrees are for (§2 physics): each gets its own working dir + `HEAD` off `origin/dev`, sharing one `.git`. The thing that *cannot* coexist is plain `git checkout` of two branches in ONE directory (single `HEAD`). So the recurring collision was **never the worktree concept** — it was (a)+(b): tooling crossing into a peer-occupied primary tree. The fix is process + tooling discipline, not a different branching model.

---

## 6. Anti-patterns

- **Integrating via the MCP `task_branch integrate` while a peer occupies the primary tree.** It runs from the primary CWD and leaks the peer's uncommitted files into your worktree (§5b a). Use the ref-only `git -C <wt> push origin HEAD:dev`.
- **A peer parking WRITES on the primary `dev` checkout.** Makes the primary "hot" so every cross-tree tool collides; everyone worktrees, primary stays the clean integration anchor (§5b b).
- **Sharing one checkout + independent `git switch`.** The cardinal §9a sin; self-branching exists to make avoiding it automatic. A peer NEVER switches the primary checkout's branch.
- **Branching for a read.** Empty worktrees for "explain this function" — the trigger is write-vs-read; reads stay on `dev`.
- **Reusing "inline" for this mode.** `inline` = no-dispatch (size). This = self-isolate (write-vs-read). Distinct axes (§1).
- **Blind `--ff-only` / `push origin dev` from a shared local `dev`.** The integration site is `origin/dev` via rebase+retry from the worktree, never a switch-and-push of the shared local `dev` (which moves it under siblings).
- **An engineer touching `dev`/`main`/`prod`.** Engineers commit only on their own branch; the architect (or peer-as-own-architect) integrates.
- **Leaving the worktree behind after integrate.** Always `cleanup`; the terminal returns to the `dev` baseline. (Stale worktrees are caught by [[storage-hygiene]], but lifecycle hygiene is the agent's job.)

---

## 7. Composition / references

- [[branching-and-merging]] §9a (concurrent-agents-never-share-one-checkout — the conditional rule this generalizes) · §9b (this mode's home there) · §0 (branch model) · §10.2 Option A (the rebase-retry integrate) · §16 (worktree recipe) · §19 (worktree lifecycle/cleanup).
- [[branching-dispatch]] — the *dispatch* runbook (architect dispatches N engineers). Self-branching is the *self*-case: the agent isolates itself rather than dispatching. They nest (§3).
- `noctus.dev.task_branch` (this mode's tool) · `noctus.dev.cleanup_stale_worktrees` (heuristic bulk-sweep sibling) · `noctus.dev.release` (the sacred-line gates self-branching never touches).
- Codification: emerged + s2 memory `feedback_self_branching_mode.md` + s3 this doc + CLAUDE.md §1 pointer; s4 tooling = the `task_branch` tool (the *process*-shape analogue of a keeper).
