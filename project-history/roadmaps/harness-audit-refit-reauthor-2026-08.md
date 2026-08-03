# harness audit refit — re-author, don't merge — 2026-08

> **✅ RESOLVED 2026-08-03** on `feat/harness-audit-reauthor`. Both slices landed; `feat/harness-audit-refit` (`1c8ff8ec`) is fully superseded and safe to delete. Retrospective at the bottom — including the three places where re-authoring produced a *different and better* answer than merging would have, and the one place where merging would have shipped a regression.

## Goal

Land the useful half of `feat/harness-audit-refit` (authored ~2026-07-17, tip `1c8ff8ec`, **never merged**) by RE-AUTHORING it against the current methodology surfaces, rather than resolving a stale merge. This doc is the durable home so the work survives the branch — during the 2026-08-01 wrap-up every other unmerged branch turned out to be superseded and was closed; this is the only one carrying real, unlanded work.

## Why it was not merged

The branch conflicts hard with `CLAUDE.md`, `.claude/commands/contextualize.md` and `.claude/skills/noc-contextualize/SKILL.md` because §1 has gained roughly ten rules since it forked — prod-exposure-consent, parallelization-first, FE↔BE contract-first, dont-block-on-background, lying-loading-state, status-pagina-role-parity, hardcoded-list drift, per-branch-green, pipefail, and the MEMORY-router rule.

That makes the merge a trap in **both** directions: taking the branch's side DELETES those ten rules; taking ours discards the consolidation the branch exists to deliver. It also reverts `KB § CONTEXT/…` paths to the older flat form.

Per `KB § PATTERNS/common/lossless-doc-refactor.md` a doc-set change is methodology surgery and must be proven lossless, not asserted — and a two-week-stale three-way merge cannot prove anything. **Re-authoring is the cheaper and safer path**, because the branch's value is a *design* (the family-index shape), not a diff.

## What is actually worth recovering

The branch is 35 files / +426 / −89. It bundles at least four separable things — do NOT re-land them as one commit:

| # | Item | Notes | Independent? |
|---|---|---|---|
| 1 | **§1 family consolidation** — collapse CLAUDE.md's flat rule list into FAMILY index lines | The headline design. Must be re-authored against today's §1, including the ~10 newer rules. Gated by `check_claude_md_router`. | yes |
| 2 | **Pointer-gate closure** — `kb_sync.py` + `compliance.py` changes, with tests (`test_claude_md_router.py`, `test_kb_sync.py`, `test_memory_md_index.py`) | Mechanical, low-conflict, most likely to apply nearly as-is. **Start here** — it is the one piece that may still cherry-pick. | yes |
| 3 | **GC exhaust + protocol trims** | Independent of the doc refactor. | yes |
| 4 | **3 new skills** | Additive; conflicts only if a same-named skill has since landed — check before assuming. | yes |

## Slices

### 1. Salvage the mechanical half first

Cherry-pick or re-apply items 2–4 above. These are code + tests, not methodology prose, so they carry no lossless-proof burden. Verify: `python mcp/noctusai/cli.py --verify-kb-sync` and `--check-claude-md-router`, plus the MCP toolkit suite.

**Trigger:** any session with spare capacity. No dependency on slice 2.

### 2. Re-author the §1 family consolidation

Read the branch's `CLAUDE.md` as a **design reference only** — never merge it. Re-derive the family grouping over the CURRENT §1, prove losslessness rule-by-rule (every rule present before is present after, or its removal is explicitly ratified by the user), and land it in one commit with the gate.

**Trigger:** requires the user in the loop — §1 is the always-on router and consolidating it changes what every future session reads. Do not do this unattended.

**Estimate:** ~1 focused session with the user; the lossless proof, not the edit, is the work.

## Decision log

- **2026-07-31** — Triaged during the harness-cluster wrap-up; marked BLOCKED with the conflict analysis rather than merged. 6 sibling branches shipped, 2 blocked.
- **2026-08-01** — Wrap-up sweep. Confirmed still the ONLY branch with unlanded work: 12 stale worktrees removed, and `feat/n8n-backend-module`, `feat/status-pagina-dev-visibility-fanout`, `feat/erp-be-mount-auth-router` all verified superseded and closed. Worktree removed to reclaim disk; **branch `feat/harness-audit-refit` @ `1c8ff8ec` deliberately preserved** — it is the only copy of this work, and it is not on `origin`. Do not garbage-collect it without landing slices 1–2 first.

## Recovery

```
git log feat/harness-audit-refit          # tip 1c8ff8ec
git diff origin/dev...feat/harness-audit-refit
```

Its sibling work (`feat/mcp-hardening-batch` — connector monkeypatch gate, `scan_wiring` paths, ts-morph AST tool) shipped separately on 2026-07-31 and is already on `dev`.

---

## Retrospective — what re-authoring bought (2026-08-03)

Both slices landed in one commit-set (the rule-count gate had to ship with the consolidation that makes it pass — gate↔methodology-sync). The interesting part is not that it landed; it is the four places where re-authoring diverged from what a merge would have produced.

**1. The diagnosis got worse while the branch sat.** The branch measured §1 at 72 rules. On re-audit it was **79** — and the word budget had been raised 2500→3500 on 2026-07-22 to accommodate the growth, with a comment naming "a real trim pass" as the deferred follow-up. This consolidation *is* that follow-up: §1 79→52 rules, CLAUDE.md 2727→2005 words, and the word cap was **restored to 2500** rather than left ratcheted. That produced a new invariant, now in the pattern doc: *budgets are restored after a consolidation, not ratcheted.*

**2. The MEMORY.md recalibration would have been wrong.** The branch proposed 60 KB → 40 KB, reasoning that "the harness truncates ~50 KB". The real threshold is **~24.4 KB**, documented in `memory-index-topic-split.md` (landed 2026-07-30, *after* the branch forked), past which the read returns *nothing*. A 40 KB cap sits **above** that cliff — the gate would still have reported green through the exact silent failure it exists to prevent. Landed **20 KB**, with a test asserting the cap stays below the cliff. Merging would have shipped a less-wrong version of the same bug.

**3. One "fix" on the branch was a regression.** It rewrote `orchestrator-operator.md`'s citation of `branching-and-merging.md § 17.6` to `§18/§21`. But §17.6 is real — *"Engineer-brief Write-authorization for findings.md"* — and is exactly what the orchestrator inherits; §18 is wave-based dispatch, an unrelated topic. **Not applied.** A merge would have taken it silently.

**4. Losslessness was proven, not asserted.** The consolidation ran as a script that moves rule lines **byte-for-byte** into family docs and then asserts every one of the 79 originals survives exactly once (still in §1, or verbatim in exactly one family doc). Result: `79 originals · missing=0 · duplicated=0`. Per `lossless-doc-refactor.md`, that is the difference between a doc refactor and a doc rewrite.

### What landed

| Item | Outcome |
|---|---|
| Pointer-gate closure | `kb_sync` now scans `.claude/commands/` — the one 8-way surface it skipped. `codify.md`'s two broken refs (silent for weeks) fixed + regression-tested, including a negative test that reintroduces the exact bug. |
| §1 rule-COUNT ceiling | `check_claude_md_router` gains invariant 4 (cap 55, target 50). Negative-tested with 10 *individually well-formed* rules — only the count fires, proving it catches accumulation rather than shape. |
| §1 family consolidation | 79 → 52 rules across 5 family-index docs (cache 6 · orchestration 9 · knowledge-lifecycle 5 · doc-discipline 8 · learning-posture 4), members verbatim. |
| MEMORY.md recalibration | 60 → 20 KB, entry cap 500 → 300, + a test asserting the cap stays below the 24.4 KB cliff. |
| GC exhaust | `/gc` command + `methodology-gc.md`. |
| 3 skills | `noc-contract-first`, `noc-mcp-tool`, `noc-archive-absorb` (the last re-authored — its memory guidance described the pre-split flat catalogue). |

### Deliberately not carried

- The `§17.6 → §18/§21` citation change (item 3 above — a regression).
- The branch's `architect/orchestration-family-index.md` location; all five family docs live in `PATTERNS/common/` alongside `methodology-gc.md`.
- Assorted agent/command prose trims that no longer apply cleanly to surfaces that have since been rewritten. They carried no gate and no rule — reproducing them would have been churn, not value.
