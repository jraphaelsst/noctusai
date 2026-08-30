# Self-branching mode — per-task worktree isolation for peer terminal-agents

> **Front-door.** The *solo* mode of the unified [[branching]] methodology (the §0 primitive at scale = 1). Read [[branching]] first for the decision spine, the worktree-sensitivity map, the known-errors bump catalog, and the §4.5 **branch-tree tracking layer** ([[branch-tree-tracking]] — create+push your branch-pointer right BEFORE you self-branch, then update+push it on every commit; never skip); this doc is the solo-mode depth.

> **One-liner.** When a terminal-agent is assigned a **writing** task, it **self-isolates** by default: do the work in a per-task `git worktree` forked from `origin/dev`, integrate straight to `origin/dev`, tear the worktree down, return to idle — **without ever switching the shared primary checkout's branch out from under a sibling**. Automatic (no "branch this" keyword), one `noctus.dev.task_branch` lifecycle call per stage.
>
> **The governing frame.** In a multi-terminal world (N agents in N terminals on the **same workspace/checkout** — e.g. several terminals in one Antigravity window) there is **no single architect on top**. Every terminal-agent is a **peer**, and a peer **cannot cheaply know whether a sibling is active in the same checkout**. So the safe default is **assume peers always exist ⇒ self-isolate every writing task**. This is the *unconditional* generalization of [[branching-and-merging]] §9a (which isolates only *when* a second agent is known active). Born 2026-05-24 (user: *"every task i ask you to do, you branch yourself on a branch separate from dev … after finalizing and pushing the branch to dev, agents switch back to dev and await for next branch dispatch"*).

---

## 0. The absolute rule — NEVER work directly on `dev` (non-negotiable, user mandate 2026-05-25)

**Every agent — dispatched or inline, team or individual, "main session" or peer — works on its OWN branch off `dev`, and NEVER does work directly on the `dev` branch / primary `dev` checkout.** Working on `dev` is *prohibited*. The primary `dev` checkout is a **clean, idle integration anchor only** (a fetch/rebase target) — never a workspace for edits.

- The FIRST action on ANY assigned task that will produce changes is to self-branch: `git worktree add .claude/worktrees/<slug> -b feat/<slug> origin/dev` (or `noctus.dev.task_branch action=start`), then work THERE. The `.claude/worktrees` model is proven — there is no reason to ever edit `dev` directly.
- Binds **inline** work too: "inline" = *no dispatch*, NOT *work on dev*. A tiny inline writing task STILL branches (§1).
- **Nobody is exempt** — dispatched engineers, agent teams, and the orchestrator/"main" session itself all branch.
- `dev` is touched ONLY at integration, and only as a **ref** (rebase-onto-latest → FF-push from the worktree, §5b) — never by editing the `dev` checkout.
- Reads / pure conversation may stay on `dev` (they produce no changes); the instant a task writes, it branches.

**Why (the mandate's root):** work done directly on `dev` is the collision source — a peer's uncommitted work on the primary `dev` checkout makes the tree "hot," and any cross-tree tool then collides (§5b). Banning work-on-`dev` removes the precondition entirely. This makes the long-standing self-branching default a hard prohibition: no exceptions, no "just this once on dev."

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
#   → SALVAGE-before-delete (learn-before-delete, KB § storage-hygiene § 2.3): records the branch+SHA
#     recovery pointer to the tracked worktree-salvage ledger (MECHANICAL — before the destructive remove)
#     + surfaces the learnings-extraction checkpoint + sequences a mole worktree-sweep, THEN
#   → git worktree remove (refuses if dirty — no --force) → prune → git branch -d feat/<slug> (merged-only)
#   → agent idle on the dev baseline; next writing task re-fetches + re-branches
#   ⚠️ Tear down ONLY via this tool (or mole sweep / cleanup_stale_worktrees) — a bare hand-typed
#     `git worktree remove` skips all three salvage legs (lost learnings + lost recovery pointer).

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
- `cleanup` **salvages before deleting** (learn-before-delete): records the branch+SHA recovery pointer to the tracked `project-history/worktree-salvage.ndjson` BEFORE `worktree remove` (mechanical — same leg the bulk sweeps carry) + surfaces the learnings checkpoint + sequences a mole worktree-sweep ⇒ a precise teardown can no longer silently lose the worktree's durable knowledge.
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

**Primary-contamination fix (2026-07-16 bug, closed 2026-07-20).** The
observable contract above is unchanged; the INTERNAL mechanism for
per-product node_modules changed. The old scheme whole-dir symlinked
`wt/products/<slug>/frontend/node_modules` → the PRIMARY's real directory,
then created `@noctusai/{lib,seed}` *inside* that path — since the path
resolves THROUGH the symlink, the write landed in the PRIMARY's shared
node_modules, re-pointing **every worktree fleet-wide** at whichever
worktree wired last (confirmed live twice: 9 products silently pointing at
a peer's `.claude/worktrees/n8n-page-ui/seed/lib/frontend`, then again at
`orbity-funnel-seed`). Fix: a product's `node_modules` is now a REAL
directory *in the worktree*, populated with one symlink per top-level
primary vendor package (cheap — a symlink, not a copy) EXCEPT the
`@noctusai` scope, which is always worktree-owned. A pre-existing stale
whole-dir symlink (left by a worktree wired before the fix) is converted
to a real directory before any entry is planned under it. See
`mcp/noctusai/tools/noctus/dev/task_branch.py` `_plan_env_wiring` /
`_apply_env_wiring` module doc + the `test_two_worktrees_wire_env_never_
contaminates_primary` regression test in `test_task_branch.py`.

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

---

## §10 · The gate (2026-08-05) — why the rule needed one

**This rule was the most-violated rule in the methodology.** It is stated as
🔴 ABSOLUTE in `CLAUDE.md` §1, restated as step 0 of `noc-self-branch`, and it
was broken in essentially every session — including twice in one session by an
agent that had it in context both times and had *already apologised for it once*.

### Why discipline could never have worked

**Nothing fails at the moment of the mistake.** `git commit` on `dev` in the
primary checkout succeeds. Every hook passes. Every test passes. Local `dev`
diverges from `origin/dev` silently.

The bill arrives later and elsewhere:

```
hint: Diverging branches can't be fast-forwarded, you need to either:
```

…at integrate or deploy — several steps from the cause, and reading like a git
problem rather than the process slip it is. Agents therefore "fixed" it with a
rebase and moved on, learning nothing, and repeated it the next session.

That shape — **invisible at the moment of violation, expensive much later** — is
the signature of a rule that needs a mechanism. Restating it more loudly is a
non-intervention; every restatement had already been tried.

### The gate

`check_primary_checkout_commit` (`--check-primary-checkout-commit`), wired as
the **first** step of `scripts/hooks/pre-commit`. Blocks when all three hold:

1. the repo is the **primary** checkout (`--absolute-git-dir` == `--git-common-dir`;
   a linked worktree reports a path under `<common>/worktrees/<name>`), **and**
2. `HEAD` is a **shared** branch — `dev` / `main` / `prod`, **and**
3. the staged set contains anything outside `project-history/`.

It runs first deliberately: it costs ~50ms, and its failure invalidates every
gate after it. Spending two minutes of checks before telling the committer they
are on the wrong branch would be its own small cruelty.

### The one exception, and why it cannot be laundered

The MCP toolkit commits its append-only ledgers straight to `dev` from the
primary checkout **by design** — `branch_pointer`, worktree-salvage, cost logs.
That is how parallel agents publish their collision zones, so blocking it would
break coordination.

So a commit whose **entire** staged set lives under `project-history/` passes.
Stage one source file alongside them and it blocks, with only the source file
named. Without that, "it's just a ledger commit" becomes a hole wide enough to
drive the original slip through — and `test_work_MIXED_INTO_a_ledger_commit_is_still_blocked`
exists to keep it shut.

### Escape hatch

`NOCTUS_ALLOW_PRIMARY_COMMIT=1` — an env var rather than a CLI flag, so it
cannot be baked into a script and forgotten. `--no-verify` is **not** an escape
hatch (`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`).

### Recovering a commit already made on the wrong branch

Nothing is lost — the commits just need a branch to live on:

```bash
git branch feat/<slug>              # give the commits a home
git reset --hard origin/<branch>    # return the shared branch to origin
git checkout feat/<slug>            # ...or work from a worktree off it
```

### The general lesson

Per `KB § PATTERNS/common/gate-methodology-sync.md`: **a rule whose violation
produces no immediate signal is advice, not a rule.** When a documented
constraint is found to have been violated repeatedly, the correct response is
not a stronger restatement — it is to ask *what would have failed at the moment
of the mistake*, and build that.

---

## §11 · The gate, again (2026-08-19) — the commit keeper fires too late

§10 built the gate and closed with the right question: *what would have failed
at the moment of the mistake?* It answered "the commit", and that answer was
**one step too late**.

**The 2026-08-18 recurrence.** An agent slipped twice in one session with
`check_primary_checkout_commit` installed and working. The keeper caught
neither, because neither slip ever reached `git commit` — the edits were spotted
by eye first. Nothing was lost, but the remedy was still a hand migration: diff
the primary, re-apply in the worktree, revert the primary, re-verify. The gate
prevented the *divergence*; it did nothing about the *waste*, because the
mistake is made when the file is written, not when it is committed.

**The mechanism the slip actually uses.** Both times it was the same shape:

```bash
cd /path/to/primary && sed -i '' 's/…/…/' products/…/app.py
```

A `cd` inside one Bash call silently re-points the write. The harness reports
the **session** cwd, which still says the worktree, so nothing in the tool call
looks wrong — and a guard that only reads the reported cwd sees nothing either.
This is why the guard parses `cd` out of the command itself.

### The gate

`primary_write_guard.decide()` (`mcp/noctusai/tools/noctus/dev/primary_write_guard.py`),
wired as a **`PreToolUse` hook** over `Edit`/`Write`/`MultiEdit`/`NotebookEdit`/
`Bash` in the checked-in `.claude/settings.json` →
`scripts/hooks/claude-guard-primary-write.py`. It **denies the tool call**, so
the wrong-tree edit never happens at all.

Refuses when all three hold:

1. the target resolves **inside the primary checkout** — and *not* inside a
   linked worktree. Linked worktrees live at `<primary>/.claude/worktrees/<slug>/`,
   i.e. physically under the primary root, so containment alone would refuse the
   one place work belongs. Worktree roots come from `git worktree list
   --porcelain`, never from the path convention; **and**
2. the primary checkout's `HEAD` is a **shared** branch (`dev`/`main`/`prod`);
   **and**
3. the tool call is a **write**. Reads are never blocked — `cat`, `grep`,
   `sed -n`, `git status`, `git log` in the primary checkout stay free.

### What is deliberately NOT guarded

**The orchestrator's own git duties**, exempt *by name*: `git pull`, `fetch`,
`merge`, `push`, `worktree`, `tag`, `branch`. Syncing and integrating the
primary checkout on `dev` **is** the job. A guard that fought it would be
switched off within a session, and a gate that gets switched off protects
nothing. Designing the legitimate case out of the guard beats teaching anyone
to bypass it (`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`).

`project-history/` is exempt for the same reason it is exempt at commit time —
one definition, imported: `compliance.py` now takes `SHARED_BRANCHES` and the
ledger allowlist **from** `primary_write_guard`, so the two gates cannot drift
into disagreeing about what "shared" or "ledger" means.

#### What git ignores, the guard ignores (2026-08-30)

The guard refused **every** path under the primary except worktrees, `.git/` and
the ledgers — including paths git itself declares out-of-repo. That blocked a
whole class of ordinary work with no correct alternative:

| refused | why it was never a divergence risk |
|---|---|
| `npm install` → `node_modules/` | gitignored |
| any python import → `__pycache__/` | gitignored |
| `vite build` → `dist/` | gitignored |
| removing a scratch dir | gitignored (once declared) |

🔴 **A gitignored file cannot be committed, so it cannot diverge `dev`** — which
is the harm the refusal message itself names. This is the same reasoning that
already exempts `project-history/`, with one improvement: **git decides**, not a
hardcoded prefix list, so the exemption tracks the repo's own declaration and
cannot drift from it.

**Still refused, and this is the point:** every TRACKED path, and every
untracked-but-**not**-ignored path. That second category is the original
2026-08-18 incident — a NEW source file created in the wrong tree is untracked
too. Only git saying *ignored* exempts it.

**Fails closed.** `git check-ignore` exits 0 = ignored, 1 = not ignored,
128 = cannot answer. Only a clean 0 exempts. This is load-bearing rather than
defensive: in the test environment the probe genuinely returns 128, so 37
existing refusal tests pass *because* it fails closed — verified by mutating it
to fail open and watching them go red.

**Cost is nil on the hot path.** The probe is only reached for a path already
inside the primary, outside every worktree, outside `.git/` and outside the
ledgers — the about-to-refuse set. A worktree write returns before it, pinned by
`test_worktree_writes_never_reach_the_ignore_probe`.

> **Corollary for scratch dirs.** Untracked-but-not-ignored at the repo root is
> now doubly bad: it is the `drift-fix-on-contact` class *and* it makes the path
> un-deletable by an agent. Declare scratch in `.gitignore` (root-anchored) at
> the moment it is created. `/tmp/` was declared 2026-08-30 for exactly this.

#### The ledger exemption covers the WHOLE round trip (2026-08-27)

An exemption that lets a file be dirtied but not cleaned is not an exemption —
it is a one-way door. Three legs are exempt when, and only when, every path
they name is under `project-history/`:

| leg | judged on |
|---|---|
| `git add <paths>` | the pathspecs |
| `git restore <paths>` · `git checkout -- <paths>` | the pathspecs |
| `git commit` | the real staged set |

**Why `restore` had to join them.** `noctus.dev.auto_improvement_log` and its
siblings write their ledger into the **primary** checkout by design. When the
orchestrator decides those lines belong elsewhere, the guard permitted the
write, permitted the `add`, permitted the `commit` — and refused the
`git checkout --` that would undo it. The only remedies left were
`reset --hard origin/dev`, which also discards unrelated pointer commits living
in the same tree, or `NOCTUS_ALLOW_PRIMARY_WRITE=1` — switching the gate off to
undo something the gate itself had allowed. That is the anti-pattern, not the
repair (`KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`).

**A bare `git checkout <token>` stays refused.** Only the explicit `--`
separator makes a `checkout` qualify, because before it a lone token is
ambiguous between a path and a **branch** — and switching the primary's HEAD out
from under every linked worktree is the §9a sin this whole methodology exists to
prevent. `git restore` needs no separator: it cannot switch a branch. Pathless
forms (`git checkout .`, `git restore .`) name nothing readable and stay
refused; those are the destructive ones.

**`git add <ledger> && git commit -m …` in ONE call now works.** It never did
before, and the reason was invisible: the hook runs *before* the command, so the
`add` had not executed and `git diff --cached` was empty. The commit leg read
"nothing staged" and refused. Splitting the two across separate tool calls
worked — a trap rather than a rule, since the compound is how the command is
habitually written. An empty index is now allowed, which is safe because a
preceding `add` of non-ledger paths refuses the whole command on its **own**
leg; a commit can therefore only reach an empty index behind an add that was
already ledger-confined. Still refused: `git commit -a`/`-p` (they stage at
commit time, so an empty index proves nothing) and any non-ledger pathspec.

🔴 **Empty ≠ unanswerable.** `_run_git` returns `""` both when git said nothing
and when git could not be asked. The commit leg is the one caller where those
point in *opposite* directions, so it uses `_run_git_checked` and refuses when
the probe did not answer. Collapsing the two would turn every environment where
the probe breaks into a blanket allow — a fail-OPEN inversion, pinned by
`test_git_commit_falls_closed_when_the_staged_probe_cannot_answer`.

### Two gates, deliberately

The Bash leg can only ever be a good *parser* of an arbitrary shell command,
never a proof. So the commit keeper stays as the backstop for whatever the
parser misses, and the two are independent:

| | fires at | catches | can be fooled by |
|---|---|---|---|
| `primary_write_guard` | the write | the mistake itself | exotic shell quoting, an interpreter one-liner |
| `check_primary_checkout_commit` | the commit | the divergence | nothing — it reads the real staged set |

When the parser cannot resolve a target but sees write intent (a `python -c`
that opens a file for writing), it refuses against the effective cwd and **says
so in the message**. The permissive answer is the one that lets the slip
through; an over-refusal costs one absolute path.

### Performance is a correctness property here

The hook runs before *every* Bash/Edit/Write call. `compliance.py` costs ~0.27 s
to import — a quarter-second tax on every command in every session is how a gate
becomes the thing someone deletes. So the decision lives in a **stdlib-only**
module the hook loads **by path** (not as a package), and the whole hook runs in
~60 ms.

### Escape hatch

`NOCTUS_ALLOW_PRIMARY_WRITE=1`, mirroring `NOCTUS_ALLOW_PRIMARY_COMMIT=1`. An
env var, never a flag, and never `--no-verify`.

### The general lesson, sharpened

§10 said: build what would have failed at the moment of the mistake. §11 adds
the follow-up — **ask when the mistake is actually made, not when it becomes
expensive.** A gate placed at the first *expensive* consequence still lets the
work be done in the wrong place; a gate placed at the *act* prevents it. When a
gate fires but the same class of incident keeps costing rework, the gate is at
the wrong point in the pipeline, not too weak.
