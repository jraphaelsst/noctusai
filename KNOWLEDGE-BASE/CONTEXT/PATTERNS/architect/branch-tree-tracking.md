# Branch-Tree Tracking — the global live map of git-tree × claude-tree

> **Status: CONTRACT (this doc is the dispatch spec for the build + the canonical methodology once shipped).**
> One unified branching methodology. Branching ⊇ dispatching: self-branching is the primitive; dispatch-branching is self-branching applied recursively by an orchestrator to a team. This system gives every agent — at every level of the branch tree — a **real-time, globally-readable map** of who is working where, on which files, in what state, so collisions are seen *before* they happen (even against unshipped work) and no leftover/undone work goes silent.

## 1 · The two trees, mirrored

- **git-tree** — branches, their fork-base (parent edge), current commit (locates the tree), worktree path.
- **claude-tree** — agents, their role (orchestrator | engineer), the orchestrator that dispatched them (parent edge), the session.

The two are **mirrors pointed at each other**, joined 1:1 by the **branch** (every working branch has exactly one owning agent; every working agent has exactly one branch — this holds by construction under self-branch + dispatch-branch). A `branch-pointer` registry is one row that carries BOTH coordinates. A keeper enforces the mirror at code-level (§5).

## 2 · The ledger — `project-history/branch-tree.ndjson`

Append-only ndjson, **tracked and pushed to dev** (sibling of `auto-improvement.ndjson` / `vector-costs.ndjson`; already covered by the `project-history/*.ndjson merge=union` gitattributes rule, so concurrent appends never conflict). Globally accessible: agents read **dev's copy** (not their branch's) to get the live, cross-branch picture.

Append-only ⇒ a status update is a NEW row for the same `branch`; **latest-by-`ts` wins** per branch (the query tool resolves this). No in-place edits ⇒ no merge conflicts.

**🔴 2026-09-17 — the ON-DISK path itself must resolve to the PRIMARY checkout (fifth instance of `KB § PATTERNS/common/claim-vs-evidence-shared-state.md`'s family).** `branch_pointer.LEDGER_PATH`/`MIRROR_PATH` now derive from `settings.LEDGER_ROOT` (`workspace.get_ledger_root()`), never `settings.REPO_ROOT` — the latter deliberately STOPS at a `.claude/worktrees/<slug>` boundary (correct for code-editing tools), so a ledger writer trusting it inherits the wrong guarantee if the MCP server happened to boot with cwd inside a worktree. This is defense-in-depth, not the primary safety net here: `append`/`update`'s commit+FF-push-to-`origin/dev` in the SAME call (§4 below) already makes a successful row durable regardless of which checkout hosted the commit — the constant only matters on a push FAILURE, where the row would otherwise sit uncommitted wherever `LEDGER_PATH` resolved.

### The mirror — `project-history/branch-tree.mirror.ndjson` (repo-tracked, always two)
A second **repo-tracked** ndjson kept **byte-identical** to the canonical ledger, so the branch-tree map is robustly persisted + reliably accessible. **Drift-prevention by construction:** `branch_pointer` writes BOTH files on every `append`/`update` (an agent populating one always populates the other — it's automatic, not a discipline they can forget). The cache-exemption + noc-graph exclusion cover both (`branch-tree.mirror.ndjson` is also metadata, never graph-input). **The gate for when something edits one out-of-band:** `check_branch_tree_mirror` carries a global PARITY invariant — if the two files ever differ (or the mirror is missing), it HARD-BLOCKS with a repair hint (`cp branch-tree.ndjson → branch-tree.mirror.ndjson`). Methodology rule: never hand-edit one alone; always write via the tool. (General principle the user affirmed 2026-06-01: ndjson ledgers are repo-tracked, never gitignored.)

### The `session` coordinate — always-filled, never null (2026-06-02)
The claude-tree's `session` field (the owning Claude session) is **never null by construction**. `branch_pointer.append`/`update` auto-fill it via `_resolve_session_id()` — `$CLAUDE_CODE_SESSION_ID` (the live session UUID the harness sets) → newest-transcript stem in this repo's Claude project dir → **refuse-loudly** (the call errors rather than writing a null; no silent-null). **The gate:** `check_branch_tree_mirror` scans **EVERY** row (incl. terminal/historical — a null session is drift anywhere, not just on a live branch) and HARD-BLOCKS (high) any null/empty `session`, naming the backfill fix. This pair — gate + auto-fill — is the canonical instance of the **gate↔methodology-sync** rule ([[gate-methodology-sync]]): the keeper enforces the invariant; the auto-fill makes compliance automatic so the keeper is a backstop, not the enforcement path. Legacy rows from before this rule were backfilled with their owning work-session slug (`<date>-<branch>`). Both slug (`2026-06-01-hot-drift`) and UUID forms are valid session identifiers.

### Schema (one JSON object per line)

```jsonc
{
  "ts": "2026-06-02T01:23:45+00:00",   // when this row was written (UTC ISO-8601)

  // ── git-tree coordinate ──────────────────────────────
  "branch": "feat/hd-deploy-tunnel",   // JOIN KEY — the branch (1:1 with the owning agent)
  "base":   "feat/hot-drift-batch",    // fork base = git parent edge (origin/dev for an orchestrator)
  "commit": "c036c711",                // current tip (locates the tree); on status=shipped = the final commit
  "worktree": ".claude/worktrees/hd-deploy-tunnel",  // or null

  // ── claude-tree coordinate (mirror) ──────────────────
  "role":   "engineer",                // orchestrator | engineer
  "agent":  "hd-deploy-tunnel",        // claude-tree node label (logical, stable — NOT the ephemeral harness id)
  "parent": "tech-lead",               // who dispatched this = claude parent edge (mirrors git `base`'s owner)
  "project": "sw-extraction",          // OPTIONAL — ship-consent approval unit; omitted ⇒ inherited from parent's pointer; unmapped ⇒ the branch name (KB § PATTERNS/devops/ship-consent-riders.md)
  "session": "2026-06-01-hot-drift",   // owning session

  // ── collision zone (the whole point) ─────────────────
  "paths": [                           // files/globs this branch is touching → its collision zone
    "mcp/noctusai/tools/noctus/dev/deploy_image.py",
    "mcp/noctusai/tests/test_deploy_image.py"
  ],

  // ── status + context ─────────────────────────────────
  "status": "on_going",                // see enum below
  "brief":  "post-recreate tunnel re-resolve + CF edge check",   // ONE-LINER: what this branch/commit does
  "notes":  ""                         // important annotations: lessons / procedures / findings / watch-points
}
```

### `status` enum
| status | meaning |
|---|---|
| `on_going` | actively being worked |
| `shipped` | work committed + merged to the orchestrator branch (full commit done); the branch's job is complete |
| `blocked` | cannot proceed (records why in `notes`); a re-route signal |
| `canceled` | abandoned (records why; e.g. duplicate-of-base — see the JSONB-#3 case) |
| `stale` | no progress + no owner; sweep candidate |
| `deferred` | parked with a named destination (in `notes`) |
| `integrated-worktree-live` | the branch landed in `origin/dev`, but a `.claude/worktrees/<slug>` directory for it still exists — `session_end_sweep`'s auto-heal writes this INSTEAD OF `shipped` (2026-09-17) rather than declare a still-checked-out worktree dead. **Non-terminal** — `pointer_blocks_removal` refuses removal for it exactly like `on_going`, never bypassed by `force=True`. |

`STATUSES`/`TERMINAL_STATUSES` in `branch_pointer.py` are the single source of truth for this enum — every consumer (this module's own validation, the `check_branch_tree_mirror` keeper in `compliance.py`, the CLI `--bp-status` help text) derives from those two frozensets rather than hand-duplicating them, so a new status propagates by construction (the "hand-maintained lists drift" class — `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`).

### `brief` vs `notes` (load-bearing) — `notes` is the inter-agent comms channel
- **`brief`** — a one-liner that lets any agent contextualize the commit/branch instantly, then use the `branch`+`commit` pointer to go in-depth on demand. The cheap orientation layer.
- **`notes`** — the durable value extracted in that commit: lessons, procedures, findings, watch-points — so a future agent inherits it in simplified form without re-reading the diff. **`notes` (+ the commit message it mirrors) is HOW AGENTS TALK TO EACH OTHER**: a running agent signals a collision zone, an orchestrator records the rationale behind a merge/claim, a spotter explains what it absorbed. The orchestrator reads the `notes` trail to reconstruct the *why* of every commit at merge time — it's the merge-decision audit log.

## 3 · The branch-pointer lifecycle (agents MUST NOT skip a step)

1. **Orchestrator, BEFORE dispatch — read STATUS FIRST.** Read **dev's** `branch-tree.ndjson` (`branch_pointer list`) and scan **pointer statuses first**: (a) `on_going` rows = live work → their `paths` are live collision zones; (b) `blocked`/`stale`/`deferred` rows or `shipped`-but-undelivered = **leftover ground**. Only after this status scan do you plan the dispatch — around the live collision zones, even against work not yet shipped/integrated. Overlapping `paths` ⇒ re-scope to a sibling file or sequence (collision-class C1/C2/C3 decided here, against the GLOBAL map, not just local diffs).
   - **Leftover-claim protocol (whoever spots it, owns it):** when ANY agent spots a leftover, that agent is responsible for absorbing + delivering it. It must **IMMEDIATELY flip the pointer to `on_going` with itself as `agent`/owner (+ a `notes` line explaining the claim) and push** — so no second agent spots the same leftover and double-claims it. The other running agents catch the new collision-zone signal on their next status read; the orchestrator takes extra care merging that zone and signals the affected team via `notes`. (Claim = `on_going` + reassigned `agent`; no new status needed.)
> **🟢 2026-09-23: `task_branch` owns steps 2, 4 and 5 (mechanism, not discipline).** `task_branch action=start` claims the `on_going` pointer (pass `project`/`brief`/`paths`/`agent`/`role`/`parent`; `project` omitted ⇒ inherited from `parent`'s pointer), `integrate` records the **post-rebase** commit as `integrated-worktree-live`, and `cleanup` closes it `shipped`. The outcome rides on `result["pointer"]` and never blocks the git lifecycle. Before this, every session appended and closed pointers by hand, and `integrate`'s rebase meant the hand-recorded sha never reached dev. The healer could not prove those branches landed, so pointers sat `on_going` for months. The healer (`session_end_sweep`) and the safety net (`check_stale_branch_pointers`, §5) share one predicate, `_worktree_staleness.pointer_branch_landed`: branch-ref merge past its fork point, OR the recorded commit on dev, OR a `Noc-Branch: <branch>` trailer commit on dev (survives the rebase). Hand `branch_pointer` calls remain for what only a human knows: widening `paths`, `blocked`, `canceled`, a `notes` message.

2. **Engineer, right BEFORE self-branching** — `task_branch action=start` publishes your claim (`status=on_going`) and **pushes ONLY `branch-tree.ndjson` to dev**. Pass your `paths` and `brief` so the collision zone is real *before* you touch a file.
3. **Engineer, on every commit to the orchestrator branch** — append an updated pointer (refresh `commit`, `status`, append to `notes` mirroring the commit message) and **push only that file to dev**. Plus **mid-flight** whenever it fits (entering `blocked`, widening `paths`, a finding worth recording).
4. **On integrate / cleanup** — `task_branch` writes `integrated-worktree-live` then `shipped` itself. By hand: on abandon → `canceled` (with reason); signal the team of any collision zone you're about to touch via `notes`.
5. **Terminal** — `shipped`/`canceled`/`stale` rows let the sweep + wrap surveys catch leftovers and undone work.

The **global read is always via dev** so every agent at every branching level sees the same updated truth in real time; misinformation is designed out by the no-skip + push-on-every-commit rules.

### 🔴 Cache-sync discipline — pointer pushes MUST be lag-free
A pointer push happens **constantly** (before self-branch, every commit, mid-flight). It MUST NOT trigger the heavy cache-refresh hooks (noc-graph / embeddings) — that's the multi-minute lag the platform already hit on every commit. Therefore:
- **`project-history/branch-tree.ndjson` is EXCLUDED from the cache-refresh hook triggers** (post-commit / post-merge / pre-push cache-settle) and from the noc-graph `history` aggregate input — it is tracking METADATA, not graph-input content. A commit/push that touches ONLY this file performs **no** cache refresh.
- Cache sync fires **only on a worktree's final, real push to dev** (the actual code/doc work) — not on pointer updates.
- This is a hook-config exclusion, **not** a keeper bypass: the mirror keeper (§5) still hard-blocks at pre-push; only the *cache-refresh convenience hooks* skip the metadata-only ledger.

**General cache-refresh-timing rule (the root cure — IMPLEMENTED).** The branch-tree exemption is the special case of a broader principle: **graph/cache refresh fires ONLY at the final delivery-push to dev** (when the orchestrator delivers validated branches), **never on intermediate worktree commits/merges/checkouts**, and when it does fire it is **incremental on the modified files only** (the surface-2 per-bucket incremental rebuild is the mechanism). Today the lag came from pre-commit / post-merge / post-checkout / pre-push all refreshing on *every* commit. **Implemented (feat/cache-timing-relocation):** the EXPENSIVE refreshes (kb/code/corpus OpenAI embeddings + noc-graph rebuild) are DEFERRED out of pre-commit / post-merge / post-checkout entirely, and pre-push gates them on the push destination being a shared branch (`dev`/`main`/`prod`) — an intermediate `feat/*` push defers them. They self-heal lazily on read (`noctus.graph.* _ensure_fresh_on_read`) + at the eventual delivery. The CHEAP zero-OpenAI structural settles (keeper / agent-context / auto-improvement) still run on intermediate ops so keeper gates stay fresh in-session. Harness-self-invisibility caveat: the speedup activates after the hooks are re-installed (merge → `bash scripts/install-hooks.sh`).

### Conflict-zone merge ownership — LAST-FINISHER-MERGES (not the orchestrator)
When your `paths` overlap a peer's (you share a collision zone), the merge of those two branches is owned by **whoever finishes LAST** — conflict zones must arrive at the orchestrator already reconciled. On finishing your work, before delivering:
1. Read the peer's pointer **status** from dev's map (`branch_pointer query branch=<peer>`).
2. **Peer is done** (`shipped`/terminal) → **YOU resolve the merge**: merge the peer's branch into yours (least-conflict-first), reconcile, and deliver the combined result. Record the merge rationale in your `notes` (the orchestrator reads it at integration).
3. **Peer is still `on_going`** → you cannot merge a moving target. Instead **write a merge-conflict signal note into the PEER's pointer** and push: `branch_pointer update branch=<peer> notes="MERGE-CONFLICT: merge feat/<you>@<sha> into your work before delivering — zone: <overlapping paths>"`. When the peer finishes, it catches that note on its own pointer (it MUST read its own latest pointer before delivering), resolves the leftover merge (your branch into theirs), then delivers the now-merged work to the orchestrator.

So the merge-resolution work flows to the later finisher; the orchestrator integrates pre-reconciled branches with the rationale already in `notes`. Sibling of the leftover-claim protocol (§3 step 1): both are "whoever spots/finishes-last owns it," signalled through pointer `notes` across context windows.

## 4 · MCP tool API — `noctus.dev.branch_pointer`

Mirror the existing ledger tools (`auto_improvement`, `_worktree_salvage`, `brief_ledger`) for file IO; mirror the salvage-ledger / `task_branch` **FF-push-to-dev** mechanism (fetch dev → stage ONLY `project-history/branch-tree.ndjson` → commit → push to dev FF-only, retry-on-race; union-merge handles concurrent appends).

| action | signature | does |
|---|---|---|
| `append` | `branch, base, commit, role, agent, parent, paths, status, brief, notes?, worktree?, session?, project?, push_dev=True` | append a row; if `push_dev`, commit+FF-push only the ndjson to dev |
| `update` | `branch, status?, commit?, paths?, brief?, notes?, project?, push_dev=True` | append a new row for `branch` carrying forward last values + the deltas (latest-wins) |
| `query` | `from_dev=True, status?, branch?, agent?, project?, paths_overlap?` | resolve latest-per-branch from **dev's** file; `paths_overlap=[…]` returns branches whose collision zone intersects (the pre-dispatch planner) |
| `list` | `from_dev=True, include_terminal=False` | the live map: all non-terminal pointers (add terminal with the flag) |

`query`/`list` default `from_dev=True` — read dev's copy, not the local branch's. Append/update default `push_dev=True` — the no-skip guarantee is the default, not an opt-in.

**Consumer (2026-09-16): `query` is also the live-pointer removal guard.** `tools/noctus/dev/_worktree_staleness.pointer_blocks_removal(branch, run)` calls `query(from_dev=True, branch=branch, runner=run)` directly — reusing the SAME latest-per-branch resolution rather than re-parsing the ndjson — and refuses to classify a worktree as removable when the resolved row's `status` is not in `TERMINAL_STATUSES` (`shipped`/`canceled`/`stale`). Both `noctus.dev.cleanup_stale_worktrees` and `noctus.dev.mole` (worktree scope) call it before ever reaching their "safe to remove" bucket; `force=True` never bypasses it (see `KB § PATTERNS/common/storage-hygiene.md § 2.3`). This is the first non-branch_pointer-module consumer of `query` and the reason a stale/never-updated pointer must resolve to a genuinely terminal status rather than being left `on_going` forever — an abandoned `on_going` row would permanently block that worktree's cleanup.

**🔴 2026-09-17 — the ledger is a CLAIM, the filesystem is EVIDENCE (second-order fix).** The 2026-09-16 guards above trust the LEDGER alone. A follow-on incident showed why that is not enough: `session_end_sweep`'s own auto-heal (`_autoheal_branch_pointers`) flipped a peer session's live `ef-w8-models-worker` pointer from `on_going` straight to the terminal `shipped` the moment its branch integrated into `origin/dev`, WITHOUT ever checking whether the worktree directory (and the session using it) still existed. `pointer_blocks_removal` then read a terminal status and waved a `cleanup_stale_worktrees force=True` sweep through, destroying the session's disk state. Two independent fixes, neither alone sufficient:
1. **`integrated-worktree-live`** (documented in the enum table above) — `_autoheal_branch_pointers` now looks up whether the branch's `.claude/worktrees/<slug>` directory still exists (via the SAME `_worktree_branches` parse the rest of the module already does) before flipping; if it does, it writes this non-terminal status instead of `shipped`. Once the directory is later removed, the heal promotes the pointer to `shipped` (2026-09-23; this was the `integrated-worktree-live-reconcile` remediation), and `task_branch cleanup` now writes `shipped` directly.
2. **Fail-closed unresolvable pointer** — `pointer_blocks_removal` used to return "not blocking" when `query` found no row at all (unknown branch, unreadable ledger, a raised exception). Absence of information is not permission: it now returns `blocks=True, status=None` for all of those, exactly like a live claim. To unblock a branch with no pointer, publish one with a genuinely terminal status — never a tool-side guess.
3. **Filesystem-mtime liveness (Leg 2, `_worktree_staleness.is_recently_active`)** — INDEPENDENT of the ledger entirely: a raw directory walk (pruning `.git`/`node_modules`/`__pycache__`/`dist`/`.pytest_cache`/`venv`) for the most recent file mtime. A worktree touched within `recent_mtime_minutes` (default 60, paired with `DEFAULT_MIN_AGE_MINUTES`) is refused — surfaced as `recently_active` (`cleanup_stale_worktrees`) / `RECENTLY_ACTIVE` (`mole`) — and this guard is NEVER bypassed by `force=True`, same as the pointer guard: evidence of current activity outranks an operator's blanket flag. This is the guard that survives even a missing, wrong, or never-published pointer.

**🔴 2026-09-20 — an unresolvable pointer is not proof of nothing.** Leg 2 above (fail-closed on no row at all) has a second-order cost nobody had measured: a branch simply never published a pointer for is otherwise IMMORTAL — permanently un-sweepable, `force=True` or not. Measured 2026-09-20: 36 of 37 stale worktrees on disk (6.4 GB) carried zero ledger rows, every one independently verified merged into `origin/dev` by true SHA ancestry by hand. `cleanup_stale_worktrees` now consults a SECOND, positive signal in exactly this gap (`pointer_status_for_branch` returns `None` — never when a live OR terminal row exists): `_worktree_staleness.merged_into_base_confirms_dead(run, branch, base)` — the branch is a verified, DIVERGED SHA ancestor of `base` (divergence excludes the 2026-09-16 trivial-self-ancestor false positive above). Each `stale` entry's authorizing evidence (`ledger_pointer` vs `merged_into_base`) is named in the tool's `stale_signals` result. Full writeup: `KB § PATTERNS/common/storage-hygiene.md § 2.3`.

See `KB § PATTERNS/common/storage-hygiene.md § 2.3` for the full guard-by-guard writeup + force-override matrix.

## 5 · The mirror keeper — `check_branch_tree_mirror` (pre-push HARD-BLOCK)

In `compliance.py` (+ keeper-pattern-cache mirror + `--check-branch-tree-mirror` cli flag), wired into the **pre-push** hook. A push to dev is **blocked** unless, for the branch being pushed:
- a **latest pointer exists** and is non-stale (its `commit` resolves; `ts` not absurdly behind the branch tip);
- **git-tree ↔ claude-tree mirror is intact** — git side (`branch`/`base`/`commit`) resolves AND claude side (`role`/`agent`/`parent`) is populated AND consistent (an engineer's `base` fork-point corresponds to its `parent` orchestrator's branch; an orchestrator's `base` is `origin/dev`);
- `status` ∈ enum and not a contradiction (e.g. not `shipped` while the branch has un-pushed commits ahead of its recorded `commit`).
Block message points at the exact `branch_pointer` call to fix it. Rationale for pre-push (not pre-commit): enforce the always-updated/no-misinfo guarantee at the **dev boundary** without taxing every local commit (and without re-introducing the slow-hook tax).

### The lifecycle safety net — `check_stale_branch_pointers` (pre-push, 2026-09-23)

It fires only when the mechanism (§3) AND the healer both missed: a pointer is still `on_going`/`integrated-worktree-live`, its branch demonstrably landed on `origin/dev` (the shared `pointer_branch_landed` predicate), and its worktree is gone. It **blocks only on the pushing session's own pointers** (`session == CLAUDE_CODE_SESSION_ID`); other sessions' stale pointers print as warnings. One agent's miss must never wall off every peer's push in a shared repo. It is unmeasurable (and says so) when the worktree has no toolkit venv. `python mcp/noctusai/cli.py --check-stale-branch-pointers`.

## 6 · Fusion map — one branching methodology (8-way sync, deliverable C)
Consolidate the scattered branching surfaces into ONE methodology with this doc as the tracking-layer anchor:
- `KB § PATTERNS/common/branching.md` + `common/self-branching-mode.md` + `architect/branching-dispatch.md` + `architect/branching-and-merging.md` → one canonical "unified branching (incl. dispatch + tracking)" spine, the others cross-link (lossless-doc-refactor: prove lossless).
- Wire the branch-pointer lifecycle (§3) into: `engineer-seed.md` (the standing protocol — create+push pointer before self-branch; update+push on every commit; never skip), `noc-self-branch` + `noc-branch-dispatch` skills (the procedure steps), `architect.md` (pre-dispatch contextualize-on-the-map), CLAUDE.md §1 (one-liner + pointer), MEMORY.md + a memory entry, CONTEXTUALIZE.md (fresh agents read the live map), and the noc-graph (auto).
- Keeper sync: `check_branch_tree_mirror` joins the eight-way-sync keeper family; keeper-pattern-cache refresh.

> Throughout: this is additive to — and the enforcement layer for — the existing self-branch + dispatch-branch rules; nothing in the current methodology is weakened, only made globally observable and code-enforced.

## 7 · 🔴 The stash stack is shared — a positional `pop` is a cross-worktree swap (2026-09-09)

**The incident.** Rebasing `feat/model-pricing-test-into-ci` failed with
`cannot rebase: Your index contains uncommitted changes`. The three dirty
files were `project-history/branch-tree.ndjson`, its `.mirror`, and
`worktree-salvage.ndjson` — and the added rows **were not that session's**.
They carried session `034951b2`'s `feat/papel-da-parte-editavel` `shipped`
pointer and its `session-end-sweep` row, both stamped 22:32:43, and
`git show origin/dev:<each>` matched none of them. Another session's ledger
rows were sitting uncommitted in a third session's worktree, on no branch.

**The mechanism.** `.git/refs/stash` is **ONE stack for the whole repository** —
the primary checkout and every worktree share it. Both ledger writers stashed
their benign artifacts before rebasing and restored afterwards with a bare
`git stash pop`, i.e. `stash@{0}`, applied into *their own* tree. `stash@{0}`
does not mean "mine"; it means "whatever anyone pushed most recently". So:

```
A: stash push   → stash@{0} = A's rows
B: stash push   → stash@{0} = B's rows, A's slid to stash@{1}
A: stash pop    → A applies B's rows into A's tree, and DROPS them
B: stash pop    → B gets whatever is on top now
```

Each session ends up holding rows it never wrote, in a tree that is not on the
branch those rows belong to.

**Why it is worse than the sibling ledger-drift entries.** Those are about a
row *stranded on the primary* — committed, merely unpushed, and recoverable by
anyone who looks. Here the rows are **uncommitted in a tree their author
neither created nor will revisit**, and every natural unblocking move destroys
them without trace: `git checkout -- project-history/`, a reset to let the
rebase proceed, or `rebase.autoStash` (which would have buried the collision
so thoroughly that nothing would ever have surfaced it). The rebase failure
was the only reason anyone saw it at all.

**The fix — address the entry by SHA, never by position.**
`_benign_stash.stash_benign` now returns the created stash's **commit SHA**
(resolved with `rev-parse stash@{0}` immediately after the push, while it is
still ours), and `pop_stash` takes that SHA: `git stash apply <sha>`, then
re-resolves the positional name from `git stash list --format='%H %gd'` to
drop **exactly that** entry — re-resolved because a peer may have shifted it
down the stack in between. Failure modes are asymmetric on purpose:

- apply fails → **do not drop.** Losing a restore is recoverable; dropping
  someone else's rows is not.
- the SHA cannot be resolved → return `None`, log at ERROR with the stash
  message to grep for, and restore nothing. Never fall back to `stash@{0}`.
- no handle at the call site → restore nothing, deliberately.

**The generalisable lesson.** The carve-out that allowed `git stash` here
(`task_branch._stash_benign_artifacts`: *"an intentional, controlled carve-out
for known-safe paths only"*) reasoned carefully about **which paths** were safe
to stash and not at all about the **stack being shared**. The paths were fine.
The namespace was global. When you allowlist an operation, check whether its
*addressing* is per-tree or repo-wide — `stash@{n}`, `refs/stash`, and the
index are all repo-wide in a worktree layout.

Regression pins: `TestSharedStackIsNotOurs` in
`mcp/noctusai/tests/test_benign_stash.py` (six cases, including "a peer pushed
on top → drop must target `stash@{1}`"), plus the `stash apply <sha>` / no-`pop`
assertions in `test_ledger_push.py` and `test_task_branch.py`.

**Still open (not fixed here):** the ledger append is not atomic — a row is
written to the working tree first and committed later, so the window where it
exists only as an uncommitted modification is what made it stashable at all.
Making the append a write → commit → push unit would remove the class rather
than make it survivable. Logged, not attempted.

**Addendum (2026-09-16) — operator-legible labels, same SHA contract.** With
the fix above landed, the shared stack kept accumulating entries — 10+ at
once observed — that all carried the byte-identical generic message
`"task_branch auto-stash: benign refresh artifacts"`. Correctness was never
at risk (restore/drop are SHA-addressed, never by message), but a human (or
the tech-lead) triaging the stack via `git stash list` had no way to tell
which entry belonged to which worktree. `_benign_stash.stash_message`
now folds in a short content fingerprint (a hash of the sorted benign-path
set) plus, when the caller supplies one, a `label_hint` — `task_branch`
passes its own worktree path. The fixed prefix survives (the ERROR-log grep
target from the incident above still matches), so this is additive:
`"<prefix> [<worktree path>] #<8-char digest>"`. Do NOT clean up the
existing accumulated entries by hand without checking each one first — some
may belong to sessions still in flight; see `noctus.dev.mole` /
`git stash list` for triage, never a blind `git stash clear`.
