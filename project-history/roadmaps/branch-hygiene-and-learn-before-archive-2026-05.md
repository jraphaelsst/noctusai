# branch-hygiene-and-learn-before-archive-2026-05 — stop leftover work from accumulating, never lose content on delete

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: 2026-05-30 — user, after discovering ~330 dangling remote branches + a 3-week-stranded-looking rule, said: *"how many times have we talked about this fking shit … leftover work from other agents … solve this FUCKING problem on our methodology."* Then: *"on phase 3 let's add the learn-before-archive project system … not losing important content to deleted files."*

## Origin / the problem

Two compounding methodology holes, both about **work that's done but never *finished* (closed the loop)**:

1. **Orphan-branch accumulation.** Dispatched-engineer worktrees push their branch to `origin` for durability; their content is cherry-picked/squashed to `dev`; the remote branch is **never deleted**. No tool sweeps *remote* branches (the existing `orphan_branch_sweep` is local-only), and **no hook runs any sweep**. Result observed 2026-05-30: **330 remote branches** (252 integrated noise + 78 needing triage). They get rediscovered out-of-context months later and waste an agent's (and the user's) time re-triaging.

2. **Content loss on delete.** When a branch/worktree/file/project IS deleted, important content (lessons, docs, commands, fix patches, pointers) can vanish. The platform has `persistent-files-absorption` + `salvage-before-delete` as *principles*, but they're not an **enforced gate** — they rely on the agent remembering.

## What SHIPPED this session (2026-05-30) — the cleanup + the slowness root-cause

| # | What | Commit | Status |
|---|---|---|---|
| S1 | Deleted 302 integrated orphan remotes (patch-id / git-cherry verified on dev) + salvage log | `6076d9df` `812681c3` | **shipped** |
| S2 | Resolved remaining 78: 50 subject-landed (deleted), 28 unique **archived as re-appliable patches** under `project-history/orphan-remote-archive-2026-05-30/` then deleted | `812681c3` | **shipped** |
| S3 | **pre-push change-gate** — refresh only caches whose source changed; delete-only/no-source pushes skip entirely (was 30-60s tax on every push) | `ce5a01dc` (merge `1c562f9a`) | **shipped** |
| S4 | Archived the 2 stale bg-safety local branches as patches (durable parity) | `38077620` | **shipped** |
| S5 | Triaged the 5 named archived remotes vs current dev → none still apply/needed (all superseded/moot/ephemeral); confirmed nothing live buried | — | **shipped** |

Remote heads: **330 → 3** (`dev`/`main`/`prod`). Nothing lost — every deletion has a durable, re-appliable salvage net.

## Phase 3 — the PREVENTION subsystem (SHIPPED 2026-05-30)

Four legs. Build order = top-down by leverage.

| # | Leg | Shape | Status |
|---|---|---|---|
| P3.1 | **Learn-before-archive gate** (the conceptual core) | A mandatory pre-delete salvage step for ANY artifact (branch / worktree / file / project / temp). Before delete: (a) is content already on dev / in KB / in memory? if not → extract it (patch for code, KB/memory entry for lessons, recovery pointer for refs); (b) no dangling pointers left behind; (c) record a salvage-log entry. Generalizes `persistent-files-absorption` + `salvage-before-delete` into ONE enforced gate. Codify: CLAUDE.md §1 rule + KB doc + (eventually) a keeper that flags deletes lacking a salvage-log entry. | **shipped** (`learn-before-archive.md` + `salvage_before_delete` tool, dry-run-default; strict keeper deferred) |
| P3.2 | **Dangling-remote keeper** | `check_dangling_remote_branches` — flag `origin/*` unmerged > N days (warning); surfaced in review + session-end so nothing hides for weeks. Squash-aware (subject-on-dev + git-cherry). | **shipped** (`check_dangling_remote_branches`, warning; wired into review + `check_all_products`) |
| P3.3 | **Auto-delete engineer remote post-integration** | Capability SHIPPED as the guarded tool `noctus.dev.delete_integrated_remote` (`dry_run=True` default · guards: integrated-by-classifier ∧ not-protected ∧ salvage-logged-first). **MANUAL-ONLY for now** — invoked explicitly by tech-lead/agents during integration; **NOT auto-wired** into the merge flow. Auto-wiring (fire automatically in `task_branch action=cleanup`) is **DEFERRED until the mechanism is proven** — see decision + proof-criteria below. | **shipped (manual); auto DEFERRED** |
| P3.4 | **Remote-aware session-end sweep** | Extend `session_end_sweep` (+ `orphan_branch_sweep`) to classify `origin/*` branches (integrated / unique-archive-candidate / protected) and actually RUN — not a tool nobody invokes. Wire as an MCP tool + the session-close ritual. | **shipped** (`session_end_sweep` remote section + `classify_remote_branches`) |

### Learn-before-archive — design detail (P3.1, the user's explicit ask)

The gate fires before ANY destructive op and asks: **"what would be LOST, and is it preserved elsewhere?"** Categories to preserve:
- **Code/diffs** → archive as a `git format-patch` under `project-history/<archive>/` (re-appliable via `git am`). Skip if content patch-equiv on dev.
- **Lessons/decisions** → absorb to KB (`KNOWLEDGE-BASE/...`) or memory (`feedback_*`) — the durable methodology surfaces.
- **Commands / runbooks / one-off scripts** → capture the command + context into the relevant KB doc or a script under `scripts/` (NO pointer left dangling to a temp file).
- **Pointers/refs** → recovery pointer (branch→SHA salvage ndjson) so the artifact is re-creatable.
- **Docs** → absorb into the canonical doc tree before the source file is deleted.

Enforcement ladder: (1) **principle** (CLAUDE.md §1 + KB doc) — ship first; (2) **tool** (`noctus.dev.salvage_before_delete` that does the extraction + logging) ; (3) **keeper** (flag a delete in recent history with no matching salvage-log entry) — Stage-4, deferred until the tool exists.

## Trigger / cadence

- P3.1–P3.4 — **all SHIPPED 2026-05-30** (engineer `feat/branch-hygiene-prevention` `e1edb98c`/`e70d7283` → merge; disciplines `8f7ba71f`). Behavioral pair codified separately (see below).
- Behavioral layer SHIPPED: `methodology-execution-discipline.md` + `product-dev-learning-ground.md` (the complementary process∧craft pair) + `.gitattributes merge=union` for ledgers.
- Re-run the remote-classifier monthly OR when `git ls-remote --heads origin | wc -l` > ~10.

## Decision log

- **2026-05-30:** Resolve the 330 by patch-equivalence (`git cherry`), not raw `rev-list` (which lies after cherry-pick/squash). Squash-merged branches detected by subject-on-dev. Unique content archived as patches before deletion (never blind-delete unique work).
- **2026-05-30:** pre-push gated (S3) is a *consistency fix*, not the reversed push-only optimization — it aligns pre-push with the already-gated pre-commit/post-merge/post-checkout boundaries; correctness backstopped by `check_all_cache_freshness`. Override `NOCTUS_FORCE_EMBED_REFRESH=1`.
- **2026-05-30:** bg-safety "stranded gem" was a **false alarm** — content fully landed on dev via the bypass-rationalization sibling; the 2 local branches were stale dupes (byte-identical doc). Lesson: verify content-on-dev before treating an old branch as a gem (this whole class is *why* P3.2's keeper must be squash-aware).
- **2026-05-30 (DECISION — resolves the P3.3 open question):** auto-delete stays **MANUAL-ONLY until the mechanism is proven**, then safely automate (user mandate: *"leave this auto-delete manually used by u or agents for now until we prove it's mechanism, so you can safely automate it"*). The destructive `delete_integrated_remote` tool is invoked explicitly by the tech-lead/agents during integration and is **not auto-wired**. This is the general posture for any new destructive automation: **ship dry-run-default + manual, prove, then auto-wire** (don't trust a brand-new branch-deleting mechanism to fire unattended). **Proof criteria to flip to automatic:** (a) ≥10 explicit manual `delete_integrated_remote(dry_run=False)` invocations across real integrations with **zero wrongful deletion** (every deleted branch's content verified on dev via the salvage log / `git cherry`), AND (b) the `classify_remote_branches` squash-aware verdict spot-checked correct on those runs. When both hold → wire it into `task_branch action=cleanup` (gate: integrated ∧ not-protected ∧ salvage-logged) and update this row to `automatic`.

## Open questions

- _(resolved 2026-05-30 — see decision log: P3.3 manual-until-proven, then automate.)_
- Does the learn-before-archive keeper (P3.1 stage-3) risk false-positives on routine temp-file deletes? Likely scope it to: branches, worktrees, files under `projects/`, and `KNOWLEDGE-BASE/` deletions — not arbitrary `/tmp`.

## Retrospective (closed 2026-05-30)

- Whole subsystem (machinery + behavioral disciplines) shipped in-session; remote heads 330→3, slowness root-fixed, nothing lost. Lessons absorbed to memory: `feedback_methodology_execution_discipline` + `feedback_product_dev_learning_ground` + `feedback_bg_agent_stall_heuristic_false_takeover`.
- Only P3.3 auto-wiring remains deferred by design (manual-until-proven, criteria in decision log).
- Dogfood proof: the agent-kb-alignment + ledger-merge gates fired during the codify commit and were fixed-at-root, not bypassed — the discipline working on itself.

_TBD — absorb lessons to KB/memory when P3 ships._
