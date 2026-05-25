# Branching — the unified methodology (the front-door)

> **What this is.** The single entry point for ALL branching / worktree / dispatch work. One primitive, one decision spine, the worktree-sensitivity awareness map, a known-errors bump catalog, and a self-improvement loop. Depth lives in the linked docs; this **routes** — read this first, open a depth doc only for the mechanics of the mode you picked.
>
> **The unification.** Self-branching (1 agent isolates itself), dispatch-branching (an architect dispatches N engineers), and master-tree (N agents × N products) are NOT three methodologies — they are the **same primitive at different scale**. They were authored separately ([[self-branching-mode]], [[branching-dispatch]], [[master-tree-parallel-batches]]) and are unified here. This doc is the spine; [[branching-and-merging]] stays the §0–§21 deep reference.

---

## 0. The one primitive

> **Every WRITE isolates in a `git worktree` forked off `origin/dev` → integrate clean (rebase/merge then FF to `dev`) → tear down → NEVER switch a shared checkout's `HEAD` under a peer.**

It is physics, not preference: a single working directory has exactly one `HEAD`. N agents sharing one checkout cannot each be on their own branch — the moment one runs `git switch`, the others' on-disk files become someone else's branch ⇒ work vanishes mid-flight (the [[branching-and-merging]] §9a "2-days-of-chaos" failure). `git worktree` = one object store, N working dirs, N independent `HEAD`s. So isolation is **mandatory** the instant a second agent might exist — and you must **assume a peer always exists** (multi-terminal world, no single architect on top).

The shared primary checkout **stays on `dev` as the idle baseline**; active writing never happens in it. Branch model ([[branching-and-merging]] §0): `main` 🔒 = blessed release line, `prod` 🔒 = deploy line — both move ONLY via the consent-gated `noctus.dev.release` bless (`dev→main`) / promote (`main→prod`) gates; `dev` = the everyday integration branch + GitHub default. **Engineers commit only on their own worker branch — they never merge/switch/touch `dev`/`main`/`prod`.** Integration is the architect's job (∨ a peer acting as architect of its own task).

---

## 1. The decision spine — the clear path

Pick the row; route to its depth. Axis order: **write-vs-read first** (isolation), then **scale** (dispatch economics).

| You are about to… | Mode | Base | Tool / depth |
|---|---|---|---|
| read / explain / design / query — **no commit** | **stay on `dev`** | dev | — (branching for a read is pure overhead) |
| **write, solo** (1 agent, ANY size) | **self-branch** | `origin/dev` | `noctus.dev.task_branch` → [[self-branching-mode]] |
| write, **tiny** (`<100 LoC ∧ <3 files ∧ single-phase`) | architect does it **inline** (no subagent) — **but still self-branches** | `origin/dev` | [[branching-and-merging]] §18.2.1 |
| **write, parallelizable** into file-disjoint slices | **dispatch** N engineers | `origin/dev` (∨ project staging) | [[branching-dispatch]] + `dispatch_preflight` |
| write, **same-shape across N products** | **master-tree** batches | per-child off `dev` | [[master-tree-parallel-batches]] |
| **explore alternatives** | branch-and-compare ∨ merge-upfront | `origin/dev` | [[branching-and-merging]] §15 |
| **two sessions / humans** (architect + operator) | two-session split | — | [[two-session-architect-operator]] |
| keep working while we talk (dispatch-heavy queue) | autonomous operator subagent | — | [[autonomous-operator-via-subagent]] |

**Three forks that cause reworks — get them right:**
- **`inline` ≠ `no-isolation`.** Inline = "don't dispatch a subagent" (size economics). Self-branch = "isolate the write" (collision-safety). **Orthogonal** — a tiny inline write STILL self-branches. Never reuse "inline" for isolation.
- **Engineers never touch `dev`/`main`/`prod`.** They commit ONLY on their own worker branch; integration (merge / reconcile / push) is the **architect**'s job (∨ a peer-as-its-own-architect). The model **nests**: a self-branching peer that dispatches engineers integrates their sub-branches itself.
- **Collision class is decided at DISPATCH, not at merge** (§4).

---

## 2. The worktree-sensitivity map — the awareness layer (the root WHY)

> **The working tree is a shared, mutable surface that tools READ.** Most noc scan / validate / gate tools walk the **filesystem** (`PRODUCTS_DIR.iterdir()` / `rglob`), **not** git's committed state. So on a shared/busy checkout — or one carrying a peer's uncommitted edits — they read **contamination** and return **wrong answers**. A reading is only trustworthy on a **clean checkout of `origin/dev`** — which an isolated worktree gives you by construction. This is the *same isolation* the write-side needs: **one move buys collision-safe writes AND trustworthy reads.**

### 2.1 Tools that read the working tree (⇒ contaminable)

| Tool / gate | reads | contamination effect |
|---|---|---|
| compliance gates `test_all_products_compliant` / `test_real_products_pass_validate` (`check_all_products` → `PRODUCTS_DIR.iterdir()`) | every file under `products/` | peer's uncommitted test/conftest ⇒ phantom NEW high/critical fingerprints ⇒ **false regression** |
| `noctus.dev.validate` / `validate_product` | product tree | phantom violations |
| `noctus.dev.scan_*` (cross/within-product helpers · service-line · block · recurrence) | services/routers/hooks tree | phantom recurrence / wrong N-count |
| `noctus.hound.scan` | tree (absorption / fusion / optimization) | phantom cleanup targets |
| `noctus.dev.kb_sync` auto-counts | `products/` walk → `02-LANDSCAPE` counts | peer files ⇒ count drift |
| `test_outline_typescript_corpus` | `products/*/frontend/src` TS | peer FE edits ⇒ symbol-count drift |
| `noctus.graph.build` | AST + prose across the workspace | stale / contaminated nodes |
| `git status` / `grep` under the **harness overlay** | the overlay, not always disk | `Edit`/`Write` "success" while disk clean ⇒ self-check LIES ([[harness-overlay-worktree-divergence]]) |

### 2.2 Failure modes
- **Phantom regression** — a scan shows a NEW high/critical (∨ recurrence ∨ drift) absent from committed `origin/dev`; it is a peer's uncommitted file. *(Bit 2026-05-25: an agent reported "2 failing compliance tests"; on a clean `origin/dev` worktree both were green — peer in-flight files on the busy checkout.)*
- **Overlay-divergence (R6)** — `Edit`/`Write` reports success against the harness overlay while the on-disk worktree stays clean; the agent's own `git status` is served the same overlay ⇒ naive self-check lies. Verify true disk from a separate Bash context (`/tmp` patch + on-disk grep). [[harness-overlay-worktree-divergence]]
- **Stale-local-`dev`** — scanning a local `dev` behind `origin/dev` reads old committed state. `git fetch` ∧ ground against `origin/dev`.
- **Nested-tree miscount** — a naive `rglob` from repo-root that descends into `.claude/worktrees/<slug>/` double-counts. Most tools scope to `REPO_ROOT/products` (immune); flag any new tool that does not.

### 2.3 The safe protocol (the rule)
1. **Verify on a clean `origin/dev` worktree before chasing.** ANY working-tree scan/gate red on a shared/busy checkout ⇒ before treating it as committed debt, re-run it in a fresh worktree off `origin/dev` (`task_branch start` gives one) **∨** confirm `git status` shows no peer-uncommitted files under the scanned path. The clean reading is authoritative.
2. **A scan result IS a derived claim** — codebase-is-source-of-truth applies to tools too. Ground it before acting.
3. **Isolate writes (self-branch) — it also gives clean reads for free.** The §0 primitive is the cure for BOTH sides.
4. **Overlay ⇒ verify true disk** from a separate Bash context, never the overlay-served self-check.

---

## 3. The modes (depth routing)
- **Solo write** → [[self-branching-mode]] (`task_branch start → integrate → cleanup`; rebase + FF straight to `origin/dev`, retry-on-race, conflict ⇒ abort + surface, never auto-resolve).
- **Parallel dispatch** → [[branching-dispatch]] (10-step runbook: decompose file-disjoint → isolated worktrees → dispatch-in-one-message → collect signal + `/tmp`-patch overlay-safety → detect collisions [path + semantic] → merge `--no-ff` → honest reconciliation commit → verify → cleanup → gate `main` at 100%). Pre-flight: `dispatch_preflight`.
- **Multi-product same-shape** → [[master-tree-parallel-batches]] (synchronized batches, shared scratchpad, sync-gates pre/mid/post).
- **Deep reference** (push semantics, recovery, worktree recipe §16, wave-gating §18, collision-class derivation §21, lifecycle/cleanup §19) → [[branching-and-merging]].

---

## 4. Guardrails — collisions · overlaps · reworks
- **Collision-safety** — one worktree+branch per concurrently-active agent; NEVER switch a shared `HEAD` under a peer (§9a). The shared primary tree's branch is owned by exactly ONE driver; reflog is truth (commits are never lost — recover by switch-back / cherry-pick, never re-do).
- **Collision detection — TWO kinds** — (a) **path-overlap** (git flags it at merge) ∧ (b) **semantic-duplicate** (different paths, same content — two agents each author a registry/helper; **git does NOT flag this — the architect must**, by reading the deliverables, not the file list).
- **Overlap, designed out at DISPATCH** — file-disjoint slices; at most ONE agent edits any existing file; prefer new-files-per-agent. Classify each slice vs the parallel-active set: **C1** file-disjoint = parallel-clean · **C2** same-file-additive = brief additive-only · **C3** substantive-overlap = re-scope to a sibling file ∨ sequence into a later wave ([[branching-and-merging]] §21).
- **Rework-avoidance** — (i) scope a slice against its SIBLINGS / parity-twins before dispatch (grep duplicates + doc refs — a one-copy change silently breaks an undocumented twin); (ii) verify-the-seed on the FORK-BASE (`git ls-tree origin/dev`), not your working tree ([[verify-seed-on-fork-base]]); (iii) project-level in-flight race check — a peer may fully deliver+archive the SAME project mid-flight; grep `origin/dev` for the success signal before a long dispatch.
- **Cross-cutting improvements SERIALIZE** — global surfaces (CLAUDE.md / KB / MEMORY / keepers / seed) are the collision amplifier: an in-slice agent SURFACES a cross-cutting improvement; the integration owner applies it serially at the merge boundary (solo = no-op, owner == runner).
- **Honest reconciliation** — resolve collisions in a DEDICATED commit; keep the agents' original commits intact; history shows the collision AND the fix (no-silent-errors, applied to git history).

---

## 5. Known errors — the bump catalog (avoid these)

> Open / self-extending (§6): a NEW bump ⇒ ADD a row, never force-fit ∨ ignore. Each row: symptom ⇒ root ⇒ avoid.

| # | Symptom | Root | Avoid / cure | Depth |
|---|---|---|---|---|
| B1 | a sibling's work vanishes mid-flight | two agents shared one checkout; one `git switch` | one worktree per active agent; never switch a shared `HEAD` | §0 · [[branching-and-merging]] §9a |
| B2 | "X is failing" but it is green on a clean tip | a working-tree scan read a peer's uncommitted files | verify on a clean `origin/dev` worktree before chasing | §2 |
| B3 | `Edit` "succeeded" but the change is not on disk | harness overlay-divergence | verify true disk from a separate Bash ctx; `/tmp` patch | [[harness-overlay-worktree-divergence]] |
| B4 | engineer's commit landed on the shared `dev` | engineer Bash cwd resolved to the PRIMARY checkout | `git -C <wt>` + abs paths; architect re-verifies primary clean before integrating | §4 |
| B5 | `feat/<proj>/<slice>` create fails | git cannot nest a ref under a `feat/<proj>` leaf | DASH form `feat/<proj>-<slice>` ∨ fork off `dev` | [[branching-dispatch]] |
| B6 | engineer's worktree lacks `dev`-only commits | harness `isolation:"worktree"` forks from `main` | prefer manual `git worktree add … origin/dev`; self-contained briefs | [[branching-and-merging]] §16.7 |
| B7 | two agents authored the same registry/helper | semantic-duplicate collision git cannot see | architect reads the deliverables, not the file list | [[branching-dispatch]] §5 |
| B8 | a one-copy tool edit broke a "parity" twin | slice under-scoped vs its siblings | grep siblings / parity-twins + doc refs before dispatch | §4 |
| B9 | a long dispatch's project was already shipped | project-axis race (a peer delivered + archived it) | grep `origin/dev` for the success signal pre-dispatch | [[project-execution]] |
| B10 | a leak slipped into a commit despite a check | `echo leak \|\| echo clean` prints, does not exit-error | `if <test>; then …; exit 1; fi` — block, do not print | §4 |
| B11 | agent killed; work seemingly lost | the ~600s watchdog killed stalled return-text gen | write `/tmp/<slice>.patch` EARLY (it survives) | §4 |
| B12 | bless put un-CI'd commits on `main` | bless FF'd to the LIVE `dev` tip, not the verified sha | bless only when `dev` is quiet ∧ assert `origin/dev` == verified-sha | [[branching-and-merging]] §0.2 |
| B13 | green local, red CI / prod | local-green ≠ the CI / slim-prod shape | confirm CI green (+ `predeploy_check` for deploys) before `main` | [[dev-prod-parity]] |
| B14 | the "smallest" projects picked for dispatch include a deploy / blocked / deferred one | folder-size ≠ readiness | select dispatch candidates by **readiness-triage** (state + risk + concurrency), never by size; ground each before dispatching | §1 · [[project-execution]] |
| B15 | two "independent" projects both edit one cross-cutting file (e.g. `compliance.py`) | project-disjoint assumed ⇒ file-disjoint | classify the **actual edit-set** (`git diff --name-only` of would-touch), not project scope (§4 C1/C2/C3) | §4 |
| B16 | dispatched a "filed / not-started" project that was already ~done | the project doc is derived + drifts vs the tree | ground project state against the tree (grep the success signal) before dispatch; doc-size ≠ work-size | §2 · [[project-execution]] |

---

## 6. Self-improvement — the methodology learns from its own bumps

> The branching methodology is **never finished** — it hardens from its own findings (the always-hardening posture, scoped to branching).

The loop (s1 → s4):
1. **Bump hit** during branching work — a collision / overlap / rework / contamination, **or a success worth reproducing**.
2. **Capture in-flight** — append it to the project's `findings.md` the moment it is seen (¬ defer-to-retro). [[project-execution]] §2.13.
3. **Promote at close** — fold the finding into the **§5 bump catalog** (a new row/class — the table is OPEN; never force-fit) + **three-way sync** (KB ↔ CLAUDE.md ↔ MEMORY, same session).
4. **Escalate if it qualifies** — deterministic predicate ∧ recurrence `N≥3` ⇒ Stage-4 keeper / preflight ([[methodology-codification-pipeline]]); otherwise it stays an s3 doc rule. *(Filed follow-up: a `task_branch` / `dispatch_preflight` guard that WARNs when a working-tree scan runs on a checkout with peer-uncommitted files under the scanned path — the §2 phantom-regression class, s3 → s4.)*

**In-code sibling.** A bump too small / out-of-scope to fix in-flight is left as a greppable `NOC-REMEDIATE[<class>]` marker at the site (the in-code analogue of the `findings.md` capture) — swept + triaged in a later batch, never silent. → [[remediation-markers]].

**LOUD surfacing:** a spotted branching improvement is announced in-the-moment (`**Methodology improvement spotted**`), applied before the in-flight work ships (in-slice) ∨ surfaced for the integration owner (cross-cutting) — never silently folded.

---

## 7. References / composition / codification
- Depth modes: [[branching-and-merging]] (the §0–§21 reference) · [[self-branching-mode]] (solo) · [[branching-dispatch]] (parallel) · [[master-tree-parallel-batches]] (multi-product) · [[two-session-architect-operator]] · [[autonomous-operator-via-subagent]].
- Adjacent: [[harness-overlay-worktree-divergence]] · [[verify-seed-on-fork-base]] · [[phased-push-policy]] · [[compliance-regression-baseline]] (a §2-sensitive gate) · [[dev-prod-parity]] · [[dev-toolkit-scaffolders]] (`dispatch_preflight` / `salvage_worktree` / `findings`) · [[storage-hygiene]] (worktree sweep).
- Tools: `noctus.dev.task_branch` (self-mode lifecycle) · `noctus.dev.dispatch_preflight` (parallel pre-flight) · `noctus.dev.release` (the sacred-line gates none of the above ever touch).
- Codification: s3 = this doc (the unified spine) + the CLAUDE.md §1 pointer + MEMORY entries; s4 = the `task_branch` tool (self-mode) + the filed worktree-sensitivity guard follow-up.
