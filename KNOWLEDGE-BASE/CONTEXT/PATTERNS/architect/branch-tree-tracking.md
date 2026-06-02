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

### The mirror — `project-history/branch-tree.mirror.ndjson` (repo-tracked, always two)
A second **repo-tracked** ndjson kept **byte-identical** to the canonical ledger, so the branch-tree map is robustly persisted + reliably accessible. **Drift-prevention by construction:** `branch_pointer` writes BOTH files on every `append`/`update` (an agent populating one always populates the other — it's automatic, not a discipline they can forget). The cache-exemption + noc-graph exclusion cover both (`branch-tree.mirror.ndjson` is also metadata, never graph-input). **The gate for when something edits one out-of-band:** `check_branch_tree_mirror` carries a global PARITY invariant — if the two files ever differ (or the mirror is missing), it HARD-BLOCKS with a repair hint (`cp branch-tree.ndjson → branch-tree.mirror.ndjson`). Methodology rule: never hand-edit one alone; always write via the tool. (General principle the user affirmed 2026-06-01: ndjson ledgers are repo-tracked, never gitignored.)

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

### `brief` vs `notes` (load-bearing) — `notes` is the inter-agent comms channel
- **`brief`** — a one-liner that lets any agent contextualize the commit/branch instantly, then use the `branch`+`commit` pointer to go in-depth on demand. The cheap orientation layer.
- **`notes`** — the durable value extracted in that commit: lessons, procedures, findings, watch-points — so a future agent inherits it in simplified form without re-reading the diff. **`notes` (+ the commit message it mirrors) is HOW AGENTS TALK TO EACH OTHER**: a running agent signals a collision zone, an orchestrator records the rationale behind a merge/claim, a spotter explains what it absorbed. The orchestrator reads the `notes` trail to reconstruct the *why* of every commit at merge time — it's the merge-decision audit log.

## 3 · The branch-pointer lifecycle (agents MUST NOT skip a step)

1. **Orchestrator, BEFORE dispatch — read STATUS FIRST.** Read **dev's** `branch-tree.ndjson` (`branch_pointer list`) and scan **pointer statuses first**: (a) `on_going` rows = live work → their `paths` are live collision zones; (b) `blocked`/`stale`/`deferred` rows or `shipped`-but-undelivered = **leftover ground**. Only after this status scan do you plan the dispatch — around the live collision zones, even against work not yet shipped/integrated. Overlapping `paths` ⇒ re-scope to a sibling file or sequence (collision-class C1/C2/C3 decided here, against the GLOBAL map, not just local diffs).
   - **Leftover-claim protocol (whoever spots it, owns it):** when ANY agent spots a leftover, that agent is responsible for absorbing + delivering it. It must **IMMEDIATELY flip the pointer to `on_going` with itself as `agent`/owner (+ a `notes` line explaining the claim) and push** — so no second agent spots the same leftover and double-claims it. The other running agents catch the new collision-zone signal on their next status read; the orchestrator takes extra care merging that zone and signals the affected team via `notes`. (Claim = `on_going` + reassigned `agent`; no new status needed.)
2. **Engineer, right BEFORE self-branching** — create your pointer (`status=on_going`, your `paths`, `brief`) and **push ONLY `branch-tree.ndjson` to dev** (`branch_pointer append … push_dev=true`). This publishes your claim to the collision zone *before* you touch a file.
3. **Engineer, on every commit to the orchestrator branch** — append an updated pointer (refresh `commit`, `status`, append to `notes` mirroring the commit message) and **push only that file to dev**. Plus **mid-flight** whenever it fits (entering `blocked`, widening `paths`, a finding worth recording).
4. **Orchestrator, on merge** — flip merged slices to `shipped`; on abandon → `canceled` (with reason); signal the team of any collision zone it's about to touch via `notes`. Push the file to dev.
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
| `append` | `branch, base, commit, role, agent, parent, paths, status, brief, notes?, worktree?, session?, push_dev=True` | append a row; if `push_dev`, commit+FF-push only the ndjson to dev |
| `update` | `branch, status?, commit?, paths?, brief?, notes?, push_dev=True` | append a new row for `branch` carrying forward last values + the deltas (latest-wins) |
| `query` | `from_dev=True, status?, branch?, agent?, paths_overlap?` | resolve latest-per-branch from **dev's** file; `paths_overlap=[…]` returns branches whose collision zone intersects (the pre-dispatch planner) |
| `list` | `from_dev=True, include_terminal=False` | the live map: all non-terminal pointers (add terminal with the flag) |

`query`/`list` default `from_dev=True` — read dev's copy, not the local branch's. Append/update default `push_dev=True` — the no-skip guarantee is the default, not an opt-in.

## 5 · The mirror keeper — `check_branch_tree_mirror` (pre-push HARD-BLOCK)

In `compliance.py` (+ keeper-pattern-cache mirror + `--check-branch-tree-mirror` cli flag), wired into the **pre-push** hook. A push to dev is **blocked** unless, for the branch being pushed:
- a **latest pointer exists** and is non-stale (its `commit` resolves; `ts` not absurdly behind the branch tip);
- **git-tree ↔ claude-tree mirror is intact** — git side (`branch`/`base`/`commit`) resolves AND claude side (`role`/`agent`/`parent`) is populated AND consistent (an engineer's `base` fork-point corresponds to its `parent` orchestrator's branch; an orchestrator's `base` is `origin/dev`);
- `status` ∈ enum and not a contradiction (e.g. not `shipped` while the branch has un-pushed commits ahead of its recorded `commit`).
Block message points at the exact `branch_pointer` call to fix it. Rationale for pre-push (not pre-commit): enforce the always-updated/no-misinfo guarantee at the **dev boundary** without taxing every local commit (and without re-introducing the slow-hook tax).

## 6 · Fusion map — one branching methodology (8-way sync, deliverable C)
Consolidate the scattered branching surfaces into ONE methodology with this doc as the tracking-layer anchor:
- `KB § PATTERNS/common/branching.md` + `common/self-branching-mode.md` + `architect/branching-dispatch.md` + `architect/branching-and-merging.md` → one canonical "unified branching (incl. dispatch + tracking)" spine, the others cross-link (lossless-doc-refactor: prove lossless).
- Wire the branch-pointer lifecycle (§3) into: `engineer-seed.md` (the standing protocol — create+push pointer before self-branch; update+push on every commit; never skip), `noc-self-branch` + `noc-branch-dispatch` skills (the procedure steps), `architect.md` (pre-dispatch contextualize-on-the-map), CLAUDE.md §1 (one-liner + pointer), MEMORY.md + a memory entry, CONTEXTUALIZE.md (fresh agents read the live map), and the noc-graph (auto).
- Keeper sync: `check_branch_tree_mirror` joins the eight-way-sync keeper family; keeper-pattern-cache refresh.

> Throughout: this is additive to — and the enforcement layer for — the existing self-branch + dispatch-branch rules; nothing in the current methodology is weakened, only made globally observable and code-enforced.
