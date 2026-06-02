# HANDOFF — `feat/hot-drift-batch`  (2026-06-01)

> For the **merge agent**: this branch is a 4-fix hot-drift batch, isolated off `origin/dev @ a03e5ec2`, validated 100% on its own branch, **deliberately not pushed to dev**. Merge it when the tech-lead/user calls it. After absorbing the lessons below, this file can be deleted (the durable lesson is already in agent memory — see Lessons §1).

## What's in the batch

Base: `origin/dev @ a03e5ec2`. Four `--no-ff` merges (first-parent):

| Surface | Merge | What | Why | Tests |
|---|---|---|---|---|
| **1 — deploy edge-resolve** | `6d674318` | `deploy_image.py`: after a successful container recreate, restart `noctus-tunnel` so cloudflared re-resolves its stale pre-recreate origin; optional post-recreate edge-reachability curl with a **browser UA** (CF WAF blocks non-browser UAs) → surfaces `edge_warning`. New params `edge_hostname`/`http` (defaulted; callers unaffected). All legs guarded — dry-run / rollback / up_to_date paths untouched. | Post-recreate the public hostname 524-timed-out at the CF edge despite a healthy container; `docker restart noctus-tunnel` was the manual fix. | 29/29 (+11) |
| **2 — noc-graph incremental** | `9d4780c0` | `noc_graph_cache.py`: per-bucket incremental rebuild. 7 sub-shas (`code/kb/harness/landscape/memory/cli/history`). Only the **code** bucket is skippable (it's the only expensive one — the AST walk = the 1–2 min — AND the only bucket fully independent of the others). On a doc-only commit the code `*` nodes + their `CONTAINS`/code-owned edges are reused, the cheap knowledge tier + global finalization (history decoration, R3, dedup, Louvain) re-run. New status `"incremental"`. **A full-vs-incremental parity test is the oracle** that locks the extractor-order mirror. | Every commit touching any graph-input surface paid a full ~1–2 min rebuild in the pre-commit hook — serialized dev velocity. (This batch's own merges were the live evidence — see Lessons §2.) | 11 new + 13 lazy-rebuild + 44 extractor regression, all green |
| **4 — task_branch robustness** | `da7513a5` | `task_branch.py`: **(A)** added all three union-merge ledgers (`worktree-salvage`/`vector-costs`/`auto-improvement.ndjson`) to `_BENIGN_REFRESH_PATTERNS` so the tool's own hook-churn no longer false-blocks `integrate`. **(B)** `_rebase_in_progress()` keys conflict detection off `.git/rebase-merge|rebase-apply` presence — a rebase *refused before starting* (hook chatter re-dirtied) now returns new status `"dirty_blocked"` (additive vocab), never a phantom `"conflict"` with empty `conflicted_files`. | `integrate` blocked on its own ledger churn, and reported phantom conflicts that a manual `git rebase` resolved cleanly. | 58/58 (+11) |
| **5 — IntegrationCard UI primitives** | `e1558e0a` | New `seed/lib/frontend/src/design-system/ui/{Badge,Button,Dialog,Input}.tsx` + `index.ts` barrel; `IntegrationCard.tsx` + `IntegrationCardModal.tsx` re-point to them. **Pure refactor** — identical rendered output/props/behavior. `Button` defaults `type="button"`. | DRY pre-stage of the inlined primitives (user-approved **ahead** of the N=3 trigger; we're at N=2 youtube+whatsapp). Adding instagram/meta/tiktok cards is now config-only. | tsc 0 · vitest 70/70 |

### Surface 3 — JSONB parity — **ABANDONED (already fixed in base)**
The social-wiring JSONB double-encode fix was **already in the base** (`f0861ea8` "fix(social-wiring): remove json.dumps double-encode on JSONB columns", merged into `a03e5ec2` as migration `010_undouble_encode_jsonb.sql` + the write-path change). The dispatched engineer correctly **added zero commits**; its worktree + branch were removed. No action for you. ⟶ This is Lesson §1.

## Full-gate verdict (regression-clean)
Full MCP suite on the integrated tree: **2742 passed**, 5 failed, 1 env-error (run with `--continue-on-collection-errors` to get past the worktree cache-path env-errors — see the pre-existing bug in Open follow-ups). **The 5 failures are PRE-EXISTING dev reds, NOT introduced by this batch** — confirmed by a differential: the identical 5 fail on clean `origin/dev@24e2d948` (which has none of this batch's changes), AND none of the 5 exercise this batch's files (they are: `test_compliance.py` ×3 = products/seed/detector scans · `test_engineer_brief_compose` graceful-degrade = cache-infra · `test_outline_typescript_corpus` baseline). This matches the known "MCP suite rotted to reds" history.
- **For the merge agent:** `test_outline_typescript_corpus` baseline is stale on dev AND this batch's new `design-system/ui/*.tsx` files will shift it further — regenerate the TS corpus baseline as part of the dev reconciliation (the outline-corpus-baseline coupling). The other 4 reds are dev's to fix, independent of this batch.

## Lessons from this session (rationale-bearing)

1. ⭐ **Pre-dispatch, verify the defect is LIVE in the dispatch *base* — not just absent from sibling-branch diffs.** My "check origin before dispatch" scan diffed `origin/dev..<sibling-branch>` (pending changes only), which is **blind to a defect already fixed in the base itself**. Surface #3 was pre-fixed in `a03e5ec2`; I still dispatched an engineer (paid the ~45–60k contextualization tax) and reserved migration `010` — the exact number the landed fix already used. Fix: before spending an engineer on a "fix X" slice, `git show <fork-base>:<file> | grep <defect-signature>` and/or run `auto_improvement_reconcile` so landed-but-unclosed drift self-closes. *(Durable: agent memory `feedback_predispatch_verify_defect_live_in_base`.)*

2. **The noc-graph full-rebuild-on-every-commit is real and expensive** — every `--no-ff` merge in this batch paid a multi-minute post-merge hook (full noc-graph rebuild + OpenAI embedding refresh w/ rate-limit retries). Surface 2 fixes exactly this; the slowness will drop once surface 2 reaches the live hooks (i.e. after this branch lands on dev).

3. **Cross-branch migration numbering needs reservation discipline.** `feat/yt-jsonb-fix` claimed social-wiring `009` + `010` while other branches were live. Parallel product work should reserve migration numbers centrally, or renumber-on-merge.

4. **Two-level branching held.** Architect branch off `origin/dev`; engineers off the **architect's** branch (not dev), merged into the architect branch, held. This isolated the batch from heavy live dev churn (10 active branches) — final cross-conflict scan: **zero file-level conflicts**.

## Watch-points for YOUR dev merge
- **`seed/lib/frontend/src/design-system/index.ts`** — a barrel I appended 4 exports to. No in-flight FE branch touches it today, but if one later appends exports expect a trivial append-conflict (keep both).
- **`task_branch` new status `"dirty_blocked"`** and **`noc_graph` new status `"incremental"`** — additive vocab; any caller pattern-matching the full status set should learn the new values.
- **`deploy_image` new params `edge_hostname`/`http`** — defaulted, callers unaffected.

## Open follow-ups (parked, named destinations)
- **scoped-improvement (engineer-surfaced, surface 2):** `noc_graph_cache._inject_r3_edges` reaches the live embeddings/keeper caches even on a tiny synthetic tree (~3.5 min before stubbing). Make R3 take an explicit cache handle so it's isolatable/cheaply testable. → log to auto-improvement + KB.
- **Lesson §1 codification:** fold a *verify-defect-live-in-base* leg into `dispatch_preflight` / `noc-branch-dispatch`. Memory written; KB/skill edit deferred (no hand-edits mid-batch).
- **pre-existing bug (found during this batch's full gate, NOT introduced here):** `cache_backend._git_common_dir()` falls back to `<repo_root>/.git` when its `git rev-parse --git-common-dir` subprocess fails. In a **worktree** that path is the `.git` *file* → `NotADirectoryError`. The subprocess flakes under full-suite collection load (many concurrent git calls), so `pytest` from a worktree intermittently can't collect cache-infra tests (`test_agent_context_cache`, `test_auto_improvement`, `test_codify_log`, `test_find_reusable_component`). In isolation they collect fine. **Fix:** make the fallback resolve the real common-dir (or fail loud) instead of producing a worktree `.git` path; retry/serialize the subprocess. Shared-core (`cache_backend.py`) → own slice. This is why this batch's full gate was run with `--continue-on-collection-errors` (the 2–4 env-collection-errors are unrelated to the batch's code).

## Decisions & rationale (quick index)
- **Asked** on surface #5 (N=2 = triage, not auto-formalize); user chose extract-now → pre-staged.
- **Stopped #3 immediately** on learning it was pre-fixed — no point burning tokens or manufacturing a guaranteed conflict.
- **Merged incrementally** (all slices file-disjoint, collision-class C1) but ran the **full gate once** at the end.
- **Manual `git worktree`** for engineer worktrees (not `task_branch start`) — `task_branch start` forks off `origin/dev`, but the user wanted engineers forked off **my** branch (two-level isolation from live dev churn).
- **No `wire_env`** — it re-points the primary's `node_modules`/`@noctusai` symlinks and would break the other active FE agents; the FE engineer consumed node_modules read-only instead.
- **No push to dev** — user mandate; the batch waits here for you.
