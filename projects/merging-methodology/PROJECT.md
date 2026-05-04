# merging-methodology — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update §11.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Filed → Phase 1 (foundational principle) ready
- **Owner / stakeholder:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § PATTERNS/branching-and-merging.md` (branching half — shipped 2026-05-03; this project fills the §10 TBD stub), `wish_develop_merging_methodology.md` (the wish this project resolves), `KB § PATTERNS/project-execution.md § 2.7 Recurrence rule` + `§ 2.11 Phase enrichment loop` (the methodology-evolution mechanics this project sits on top of), `feedback_branching_methodology.md`, `feedback_orchestrator_role.md`.
- **Project slug:** `merging-methodology` — cross-cutting / platform methodology project per `KB § PATTERNS/project-execution.md §1`. Lives at root `projects/<slug>/`.
- **Branch:** `merging-methodology` (per new "branch this → file → implement" trigger order; `KB § PATTERNS/branching-and-merging.md § 13`).

---

## 1. Context & Purpose

The branching methodology shipped earlier today (`KB § PATTERNS/branching-and-merging.md` + extension) covers everything EXCEPT what to do when the fast-forward push fails. When `origin/main` has moved past your branch base — because multiple agents pushed concurrently, or your branch sat unpushed long enough that main moved — you cannot fast-forward. You must MERGE. That's the gap this project fills.

User directive 2026-05-03, verbatim:
> *"and we'll also keep the git merge as a safety net :) when our methodology fails to commit, we'll have learned a new thing from that fix. So we don't fail again that same way in the future, yea? Doc this thought please... nice to have this as one foundational principle. please doc this so we have the lessons and the reasoning about it, for future knowledge. branch this merging methodology, please"*

Two threads in that directive:

1. **The merging methodology itself.** Concrete: how to handle non-fast-forward integration, multi-branch convergence, PR review flow, conflict resolution, long-running branch maintenance, recovery from bad merges. Phases 2-7 of this project.
2. **The foundational principle that motivates it.** Generalized: "safety nets capture failures; failures become learnings; methodology evolves through them." `git merge` is a safety net — when our methodology has a gap, `git merge` keeps the system working while we learn. Then we update the methodology to close the gap. Phase 1 of this project. Lives in `KB § 01-PHILOSOPHY.md` because it's a methodology-evolution principle, not a methodology rule.

The win: the §10 TBD stub in `KB § PATTERNS/branching-and-merging.md` gets filled in, the wish `wish_develop_merging_methodology.md` gets retired, and the platform's methodology-evolution loop gets a foundational principle to anchor on.

---

## 2. Confirmed constraints

- **`git merge` stays as the safety net.** *User directive: "and we'll also keep the git merge as a safety net :)"* The methodology is the discipline layer ON TOP of `git merge`; it does NOT replace `git merge`. When auto-merge handles a non-conflicting integration, that's the safety net working — no methodology call needed. The methodology activates for the cases auto-merge can't resolve (same-line conflicts, multi-branch ordering, PR review flow). *(Drives §3 principle 1.)*
- **Methodology evolves through safety-net-caught failures.** *User directive: "when our methodology fails to commit, we'll have learned a new thing from that fix. So we don't fail again that same way in the future, yea?"* Failures with safety nets become learnings; methodology that incorporates them stops repeating those failures. Foundational principle, lands in `KB § 01-PHILOSOPHY.md`. *(Drives §6 Phase 1.)*
- **Branch-per-project + orchestrator-merges already in place.** This project itself ships via the new methodology — branch first, file project, implement, push branch, orchestrator-merges. *(Drives §6 commit cadence.)*

---

## 3. Design principles

1. **Build on `git merge`, don't replace it.** The mechanical tool is the safety net floor. The methodology is process discipline ON TOP — for ordering, for review, for conflict resolution, for the cases mechanics alone can't handle. Never recommend bespoke merge logic that bypasses `git merge`.
2. **Failures are part of methodology design, not a sign of failure.** The methodology is incomplete by design. Safety nets exist precisely to keep the system working while we learn. A methodology that never fails has either calcified or isn't being used hard enough. (Foundational — covered in Phase 1.)
3. **One sub-area per phase.** The merging methodology covers 5+ sub-areas (non-FF, multi-branch, conflict resolution, long-running branches, recovery). Each gets its own phase + commit, so the work is reviewable in pieces and partial-progress is durable.
4. **Document failure modes alongside happy paths.** Each sub-area's section includes both the recipe for the normal case AND the failure modes (and how to recover via the safety net). This way the doc is itself a learning artifact when the methodology fails.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** N/A — this is platform-level methodology, not product code.
2. **Is the data source product-specific?** N/A.
3. **Is the placement product-specific?** N/A.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** No — this is methodology / KB territory.
6. **Default-on or opt-in?** **Default-on once landed.** Methodology rules apply platform-wide; opt-out doesn't make sense.

**Litmus — per-product code count this design requires:** [x] **0 lines** in any `products/<x>/` tree. All work lands in `KNOWLEDGE-BASE/`, `CLAUDE/`, agent memory.

**Phase plan implications:** §6 phases work in KB + CLAUDE auto-loaded surfaces. **No phase walks through products.** Correct shape.

---

## 4. Scope

**In scope:**

- Phase 1 — Foundational principle "Safety nets capture failures; failures become learnings; methodology evolves" → `KB § 01-PHILOSOPHY.md` + CLAUDE.md (or topical) + memory entry. Three-way sync.
- Phase 2 — Non-fast-forward integration: `git fetch + git pull --rebase` vs. `git merge origin/main`; when to choose which; conflict-free path.
- Phase 3 — Multi-branch convergence: when N branches all want to land on main; ordering rules; who-merges-first negotiation; especially relevant for parallel projects under seed-workspace.
- Phase 4 — Conflict resolution discipline: how to read a 3-way merge cleanly; which side wins for which file types (KB doc, MCP tool registrations, migration files); how to avoid losing commits in interactive merges; when to abort and re-strategize.
- Phase 5 — Long-running branch maintenance: rebase cadence (daily? on-each-main-push?); integration debt thresholds; when to abandon a branch and re-do.
- Phase 6 — Recovery from bad merges: `git reflog`, `git reset --hard ORIG_HEAD`, when to ask for help.
- Phase 7 — Project close: fill in `KB § PATTERNS/branching-and-merging.md § 10` (or split into sibling `KB § PATTERNS/merging.md`); retire wish entry; project folder delete; orchestrator merge to main.

**Out of scope (for now — with reason):**

- **GitHub Actions / CI integration with merge gates.** Out of scope; this project covers the local + remote workflow, not CI policy. Future project if needed.
- **Tooling automation around merging** (e.g. an MCP tool that helps resolve conflicts). Methodology first; tooling later if the methodology surfaces a high-volume need.
- **Multi-repo or submodule merging.** Single-repo monorepo is our scope.
- **Forge migration** (GitHub → GitLab → Forgejo etc.). The methodology should work tool-agnostically (per `KB § PATTERNS/branching-and-merging.md § 12 GitHub PR model`); migration plans are separate concerns.

---

## 5. Architecture / Data Model

*Process-oriented project — no data model. Architecture = where each piece lands.*

### 5.1 Doc placement

- **Foundational principle** (Phase 1): `KB § 01-PHILOSOPHY.md` (new section near the existing methodology-evolution rules — "Triage at decision time", "DRY — recurrence rule", "No silent errors"). Plus: bullet in `CLAUDE.md` §1 (universal rules) since it's foundational; memory entry `feedback_safety_nets_become_learnings.md`.
- **Merging methodology body** (Phases 2-6): default — extend `KB § PATTERNS/branching-and-merging.md` §10 inline. If the cumulative content exceeds ~200 lines, split into a sibling `KB § PATTERNS/merging.md` with `branching-and-merging.md §10` becoming a one-line pointer. Decision deferred to Phase 7 close based on actual length.
- **CLAUDE/projects.md**: amend the branching bullet OR add a separate merging bullet, depending on body length.
- **Memory**: `feedback_merging_methodology.md` lands; `wish_develop_merging_methodology.md` deletes; MEMORY.md updated.

### 5.2 The §10 → split decision

If the merging body lands ≤200 lines: keep inline in `KB § PATTERNS/branching-and-merging.md §10`. The doc remains "branching (and merging)" — one home.

If >200 lines: split into `KB § PATTERNS/merging.md` (new file). Update `KB § INDEX.md`. The branching doc's §10 becomes a 2-line stub: "See sibling doc `merging.md`. Quick recipe: …".

Decision criterion: readability + KB integrity. We'll know by Phase 6.

---

## 6. Implementation phases

Branched-project workflow per `KB § PATTERNS/branching-and-merging.md § 11`: phase commits go to the `merging-methodology` branch; final commit + push lands on branch; orchestrator-merges branch tip to main at project close.

### Phase 0 — File this project ✅

- [x] Branch `merging-methodology` created from origin/main.
- [x] `projects/merging-methodology/PROJECT.md` filed.
- [x] `projects/merging-methodology/proposals/.gitkeep` created.
- [x] Initial commit on branch.

**Improvements:** none identified — filing pass was straightforward execution of the new "branch this → file → implement" trigger order.

### Phase 1 — Foundational principle: Safety nets capture failures; failures become learnings; methodology evolves ✅

Three-way sync — KB (philosophy) + CLAUDE.md universal-rules + memory.

- [x] Add new universal rule to `KB § 01-PHILOSOPHY.md` titled "Safety nets capture failures; failures become learnings; methodology evolves." Inserted between "Estimate off evidence" and "DRY" — adjacent to the methodology-evolution mechanics (Triage, recurrence, three-way sync).
- [x] Add bullet to `CLAUDE.md §1` (universal rules — auto-loaded). Inserted between "Triage at decision time" and "No silent errors" — coherent ordering: triage → safety-nets-evolve → no-silent-errors → three-way-sync.
- [x] Add memory entry `feedback_safety_nets_become_learnings.md` with frontmatter + rule + Why + How to apply + 3 real instances + anti-patterns + companion rules.
- [x] Update `MEMORY.md` index — new "### Foundational principles" section above "### Code quality / engineering."
- [x] Run `bash scripts/verify-kb-sync.sh` + `python scripts/update-kb-counts.py --check` — both green.
- [x] Commit: `docs(kb+claude+memory): foundational principle — safety nets capture failures; failures become learnings; methodology evolves [merging-methodology Phase 1]`.

**Improvements:** none identified — Phase 1 was a clean three-way sync of a single foundational principle. No mid-flight discoveries. The principle's own anti-patterns section absorbed the failure-modes I would have flagged.

### Phase 2 — Non-fast-forward integration

When the fast-forward push fails (origin/main moved past your branch base):

- [ ] Document the choice point: rebase your branch onto new origin/main vs. merge origin/main into your branch. Rules for when to use each.
- [ ] Document the conflict-free path (auto-merge handles the divergence) — the common case.
- [ ] Document the conflict path (handed off to Phase 4 conflict-resolution).
- [ ] Tests / examples: walked through with the actual recent commits on this repo (`7ef0f16` → `db29d44` → `21d84a4` parallel-agent train as a real example).
- [ ] Commit: `docs(kb): merging methodology §X — non-fast-forward integration [merging-methodology Phase 2]`.

**Improvements:** _(captured live during Phase 2)_

### Phase 3 — Multi-branch convergence

When N branches all want to land on main:

- [ ] Document ordering rules: who merges first?
- [ ] Document the queue / serialization pattern: branches don't merge in parallel; they queue.
- [ ] Document branch-of-branch (chained branches) when one project's branch depends on another project's branch.
- [ ] Especially relevant for parallel projects under seed-workspace.
- [ ] Commit: `docs(kb): merging methodology §Y — multi-branch convergence [merging-methodology Phase 3]`.

**Improvements:** _(captured live during Phase 3)_

### Phase 4 — Conflict resolution discipline

The hardest section. Same-line conflicts; manual resolution.

- [ ] Document how to read a 3-way merge: ours / theirs / base, when to use which.
- [ ] Document file-type-specific resolution heuristics: KB docs (concatenate sections), MCP tool registrations (alphabetic merge), migration files (NEVER conflict — sequence numbers prevent it; if conflict, both are wrong), test files (union), config (manual).
- [ ] Document interactive merges: when to abort and re-strategize.
- [ ] Document avoiding lost commits: always use `git merge` (default merge commit), never `git rebase --skip` without reading the diff first.
- [ ] Recovery anti-patterns to avoid.
- [ ] Commit: `docs(kb): merging methodology §Z — conflict resolution discipline [merging-methodology Phase 4]`.

**Improvements:** _(captured live during Phase 4)_

### Phase 5 — Long-running branch maintenance

When a branch sits unpushed-to-main for >1 day:

- [ ] Document rebase cadence: daily? on-each-main-push? user-triggered?
- [ ] Integration debt thresholds: when does a branch become more cost than benefit?
- [ ] When to abandon a branch and re-do.
- [ ] Commit: `docs(kb): merging methodology §W — long-running branch maintenance [merging-methodology Phase 5]`.

**Improvements:** _(captured live during Phase 5)_

### Phase 6 — Recovery from bad merges

When a merge goes wrong:

- [ ] Document `git reflog` discipline (always check before destructive commands).
- [ ] Document `git reset --hard ORIG_HEAD` as the canonical undo.
- [ ] Document when to ask for help (humans are the safety net for the methodology, just as `git merge` is the safety net for the rules).
- [ ] Commit: `docs(kb): merging methodology §V — recovery from bad merges [merging-methodology Phase 6]`.

**Improvements:** _(captured live during Phase 6)_

### Phase 7 — Project close

- [ ] Decide: split into `KB § PATTERNS/merging.md` (if >200 lines) or keep inline in `branching-and-merging.md §10`. Per §5.2.
- [ ] Update `KB § INDEX.md` if a new top-level pattern doc was created.
- [ ] Update `CLAUDE/projects.md` (amend branching bullet OR add merging bullet).
- [ ] Update `feedback_branching_methodology.md` to remove "merging methodology TBD" — replace with pointer to live merging doc.
- [ ] Add `feedback_merging_methodology.md`.
- [ ] Delete `wish_develop_merging_methodology.md` + remove from MEMORY.md.
- [ ] Update §10 in `KB § PATTERNS/branching-and-merging.md`: remove TBD framing; either inline content or pointer to sibling doc.
- [ ] Final verification: `verify-kb-sync.sh` green, `update-kb-counts.py --check` green, no broken pointers anywhere.
- [ ] `git rm -r projects/merging-methodology/`.
- [ ] Final commit: `chore(projects): merging-methodology close — folder delete (project close) [merging-methodology close]`.
- [ ] Push branch (if not already): `git push -u origin merging-methodology`.
- [ ] **Orchestrator** (CLI agent) takes fresh-eyes pass per `KB § PATTERNS/branching-and-merging.md § 12`.
- [ ] Orchestrator fast-forward push: `git push origin merging-methodology:main`.

---

## 7. Open questions

- **Inline vs. split (§5.2)?** Recommendation: **decide at Phase 7** based on actual line count. Default to inline; split only if readability suffers.
- **CLAUDE/projects.md: amend branching bullet OR add merging bullet?** Recommendation: **amend** if length permits; the two methodologies are tightly coupled. Add separate bullet only if the combined bullet exceeds ~200 words and harms readability.
- **Does §6 Phase 4 (conflict resolution) need worked examples from real conflicts in this repo?** Recommendation: **yes** — find one or two recent same-line conflicts in git log (or simulate one) to walk through. Concrete > abstract.

---

## 8. Dependencies & blockers

- **Branching methodology in place** — ✅ shipped (`KB § PATTERNS/branching-and-merging.md`).
- **Phase enrichment loop in place** — ✅ shipped (lets each phase log its learnings durably).
- **No external blockers.** This is documentation work, no code dependencies.

---

## 9. Success criteria

- [ ] `KB § 01-PHILOSOPHY.md` carries the "Safety nets capture failures; methodology evolves" foundational principle.
- [ ] `KB § PATTERNS/branching-and-merging.md §10` is filled in (or split to sibling) with all 5 sub-areas covered.
- [ ] `wish_develop_merging_methodology.md` deleted from agent memory.
- [ ] `feedback_merging_methodology.md` exists and is indexed in `MEMORY.md`.
- [ ] `feedback_branching_methodology.md` updated (no longer says "TBD").
- [ ] `CLAUDE.md §1` carries the foundational principle bullet; `CLAUDE/projects.md` carries the merging methodology pointer.
- [ ] `verify-kb-sync.sh` + `update-kb-counts.py --check` green.
- [ ] All 7 phases shipped on branch `merging-methodology`; orchestrator fast-forward push to main lands clean.
- [ ] Project folder deleted on close.

---

## 10. How to use this plan

```bash
# Phase 1 — foundational principle (3-way sync)
# Edit KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md (add new section)
# Edit CLAUDE.md (add §1 bullet)
# Create ~/.claude/projects/.../memory/feedback_safety_nets_become_learnings.md
# Update MEMORY.md
bash scripts/verify-kb-sync.sh
python scripts/update-kb-counts.py --check
git add KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md CLAUDE.md
git commit -m "docs(kb+claude+memory): foundational principle — safety nets capture failures; failures become learnings; methodology evolves [merging-methodology Phase 1]"

# Phase 2-6 — write each sub-area, commit per phase
# (Detail per phase as the work happens.)

# Phase 7 — close
git rm -r projects/merging-methodology/
git commit -m "chore(projects): merging-methodology close — folder delete (project close) [merging-methodology close]"
git push -u origin merging-methodology
# Orchestrator pass:
git diff origin/main..origin/merging-methodology --stat
git log origin/main..origin/merging-methodology --pretty="%h %an %s"
bash scripts/verify-kb-sync.sh
python scripts/update-kb-counts.py --check
# If clean:
git push origin merging-methodology:main
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Project filed by claude-opus-4-7 after user directive: "branch this merging methodology, please." Two threads: (a) the merging methodology body itself (Phases 2-7), (b) foundational principle "safety nets capture failures; failures become learnings; methodology evolves" (Phase 1) — user emphasized this is foundational, lands in KB philosophy. Branched first per new "branch this → file → implement" trigger order. Single-session execution intended; cadence phase-by-phase. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

- **Folder `projects/merging-methodology/` deleted on close** per the apply-inline-then-delete methodology.
- **Final orchestrator push to main** must include only this project's commits (`[merging-methodology ...]` bracketed). Verify authorship via `git log origin/main..origin/merging-methodology --pretty="%h %an %s"` before fast-forward push.
- **Wish memory entry deleted at close** — `wish_develop_merging_methodology.md` and its MEMORY.md index line removed in Phase 7.
- **No new untracked files** introduced by this project.
