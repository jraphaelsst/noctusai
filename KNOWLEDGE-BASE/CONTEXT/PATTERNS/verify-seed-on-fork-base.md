# Verify-the-Seed-Ships-It Binds to the Engineers' Fork Base

> **The architect's dispatch-time `verify-the-seed-ships-it` check must run against the engineers' actual fork base (`origin/main`), NOT against the architect's working tree.**
>
> Agent worktree-isolation forks from `origin/main`. Unmerged feature-branch lifts are present in the architect's working tree but invisible to every dispatched engineer. A working-tree-grep "the seed ships it" can be true for the architect and false for the engineer at the same instant.

---

## 1. The rule (R2)

Before dispatching any brief that wraps ∨ consumes a seed symbol, the architect verifies the symbol exists on the engineers' **actual fork base**:

```bash
git ls-tree origin/main -- <seed path>      # the base the worktree forks from
# ¬:  ls seed/lib/backend/.../<path>         # the architect's working tree
```

`git ls-tree origin/main` answers the only question that matters at dispatch: *does the code the brief tells the engineer to wrap exist in the tree the engineer's worktree will actually open?* `ls` in the working tree answers a different question — *does it exist where I am standing?* — and the two diverge whenever the architect is mid-project on an unmerged feature branch.

## 2. Why — the evidence

The connector-MCP project verified `noctusai_lib.integrations.meta` against the primary working tree (`feat/social-wiring-absorption`, which **had** the absorbed `meta` package) and dispatched META + DOCS-CONSUME to wrap it. Both engineers' worktrees forked stale `origin/main` — **pre-absorption, no `meta`**. Both engineers correctly STOPPED (verify-the-seed-ships-it firing engineer-side). Cost: a full re-dispatch wave + an integration-branch rebase to a base that actually carried the lib.

The engineer-side check (Phase 0, `feedback_verify_seed_ships_it`) caught it — but only after the dispatch round-trip was already spent. The architect-side dispatch-time check (`feedback_verify_seed_ships_it_at_dispatch_time`) would have caught it 30 s earlier — **if it had been bound to the fork base instead of the working tree.** R2 is the binding correction: same check, correct tree.

## 3. How to apply

- The dispatch-time check is `git ls-tree origin/main -- <seed path>`, never the working tree, never `ls`, never a `Read` of the working copy.
- If the symbol is absent on `origin/main` but present on the feature branch: the brief is **not dispatchable as written**. Either (a) phase-push the prerequisite to `origin/main` first (see § 4), or (b) carry an explicit worktree-base reset directive in the brief preamble (`KB § PATTERNS/branching-and-merging.md § 16.7`) so the engineer rebases onto the branch tip.
- This binds into the engineer-default worktree-base preamble: every dispatch brief that wraps a seed symbol pairs the §16.7 worktree-base verification with the `git ls-tree origin/main` precondition.

**The conflation R2 closes:** "the seed ships X" is two independent facts — *does X exist in some tree the architect can see* (working tree) ∧ *does X exist in the tree the engineer will fork* (`origin/main`). The dispatch-time check must assert the second. The first is necessary but not sufficient.

## 4. The structural cure

R2 is a *detection* rule; the *cure* is keeping `origin/main` current so the fork base is never stale. That is the phased-push policy: `KB § PATTERNS/phased-push-policy.md` (R4). When `origin/main` carries every closed project, `git ls-tree origin/main` and the working tree agree, and the entire class of fork-base mismatch evaporates. R2 detects the gap; R4 closes it structurally. The connector-MCP project proved the loop end-to-end: the fork-base mismatch (R2) was permanently fixed once the phased-push (R4) caught `origin/main` up to the absorbed lib.

## 5. Anti-patterns

- **Grepping the working tree because "the seed obviously ships it — I can see it right here."** You can see it; the engineer's `origin/main`-forked worktree cannot. Specificity of your view ≠ correctness of the engineer's.
- **Treating "dispatch-time verify ✓" as transitive across trees.** A verify that ran in the wrong tree is not a verify — it is a silent error wearing a checkmark.
- **Resetting the engineer's worktree to a SHA that does not exist on `origin/main` without pushing first.** The reset directive only works if the target is reachable; pair R2 with the push-first variant of §16.7.

## 6. Relationship to other rules

- **Amends / extends *verify-the-seed-ships-it-at-dispatch-time*** (memory `feedback_verify_seed_ships_it_at_dispatch_time`) — same check, bound to the correct tree.
- **Engineer-side sibling: *verify-the-seed-ships-it*** (CLAUDE.md §1) — the Phase 0 backstop that caught META/DOCS-CONSUME after the round-trip R2 prevents.
- **Cured by R4** (`KB § PATTERNS/phased-push-policy.md`) — keeping `origin/main` current removes the gap R2 detects.
- **Instance of *codebase is source of truth*** — the authoritative tree is the one the consumer (here: the engineer's worktree) actually opens.
- **Companion: `KB § PATTERNS/branching-and-merging.md § 16.7`** — the worktree-base verification preamble; R2 adds the seed-symbol precondition to it.

s1 (META/DOCS-CONSUME both STOPPED, user flagged the dispatch slip) → s2 (memory `feedback_verify_seed_on_fork_base`) → **s3 (this doc + CLAUDE.md pointer + INDEX.md)**.

---

**Memory:** `feedback_verify_seed_on_fork_base`. **CLAUDE.md:** §1 *Verify seed on fork base* / *Verify the seed ships it* pointers. **Companion:** `KB § PATTERNS/branching-and-merging.md § 16.7`, `KB § PATTERNS/phased-push-policy.md` (the cure).
