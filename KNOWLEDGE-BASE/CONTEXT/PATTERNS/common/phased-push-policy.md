# Phased-Push Policy for Large Commit Backlogs

> **Long-lived feature branches accumulate large unmerged-to-`main` backlogs. Merge/push to `main` in phased increments at project/wave-close boundaries — never one massive N-projects push — and only when 100% sure. Each increment is human-gated: the architect PRESENTS, the user gives go/no-go, the architect executes.**
>
> This is the structural fix for the root cause that cost the connector-MCP project two full re-dispatch waves: stale `origin/main` ⇒ stale engineer fork bases.

---

## 1. The problem

Long-lived feature branches accumulate huge unmerged-to-`main` backlogs (`feat/social-wiring-absorption` reached 50+ commits / ≥11 closed projects unmerged). Because Agent worktree-isolation forks from `origin/main`, every engineer dispatched while the backlog sits inherits a fork base that lacks the in-flight work. The result is recurring base-mismatch (the R2 / §16.7 class of failure) — the connector-MCP project paid for it with two complete re-dispatch waves. The backlog itself is the hazard; "merge it all later" is the anti-pattern that grows it.

## 2. The policy (R4)

(a) **Phased increments.** Feature-branch work merges/pushes to `main` in increments **at project/wave-close boundaries** — never one massive N-projects blob push.

(b) **100%-sure gate.** A push happens **only when 100% sure** for that increment = full verification green: touched-product builds ∧ pytest ∧ `verify-kb-sync` ∧ the increment's own success criteria.

(c) **Bounded backlog.** Accumulating ≥1 *closed* project unmerged is the signal to phase-push — ¬ "later." A closed-but-unmerged project is debt, not a deferred convenience.

(d) **Merge-debt monitor.** `scripts/merge-debt-monitor.sh` (custodial sibling of disk-usage-monitor / `mole` / `hound`) emits `origin/main`-behind-by N-commits / M-closed-projects + a `next_action` (exit 0/1/2/3 + `--json`), wired as a **pre-dispatch gate** (the architect does not dispatch into a tree whose fork base is N closed-projects stale without a conscious decision) ∧ a **project-close gate**. Bash-3.x-compatible per the `mole` `mapfile`-silent-no-op lesson.

## 3. The human-gated protocol

The architect FF-pushes `main` to verified checkpoints **one increment at a time**. For EACH increment the architect **PRESENTS**:

- the exact `git push` command,
- the commit range / content,
- verification evidence: FF-safety ancestor check ∧ `verify-kb-sync` ∧ closed/archived-project provenance ∧ seed-lib collect-clean.

The **user gives explicit go/no-go** for that specific increment. The user never executes git themselves. The architect executes the push **only on an explicit "go" for that specific increment**.

**A direct-to-`main` push without a presented + approved per-increment gate is forbidden** — harness-classifier-enforced ∧ policy. General delegation ≠ per-push authorization: a single 59-commit FF was correctly blocked 2026-05-18 precisely because it was not a presented + approved per-increment gate.

## 4. Why — the evidence

User-directed, frustration-flagged: *"bumped into it more times than I can count"* … *"phased … only pushed when 100% sure … present me the push and i give it a go or not. Doc this."* The policy was proven end-to-end on its first real use the same day: `origin/main` caught up A→B→C→D via four verified, presented, user-approved FFs; backlog → 0; the `W2-BASE-E1` fork-base mismatch (R2) was **permanently fixed** because `origin/main` finally carried the absorbed connector lib. R4 is the structural cure for the gap R2 detects.

## 5. How to apply

- `bash scripts/merge-debt-monitor.sh` before any dispatch-heavy work ∧ at every project close. Treat a non-zero exit / `next_action` as a gate, not advice.
- At each project/wave close, assemble the increment, run the full 100%-sure verification, then PRESENT {push command + range + evidence} and wait for the explicit per-increment "go."
- Never batch closed projects "to push them together later" — each closed project is its own increment signal.
- The push is the literal last step of project close (see `KB § PATTERNS/architect/project-execution.md § 2.10`) — committed ∧ green first, presented second, executed only on go.

## 6. Relationship to other rules

- **Cures R2** (`KB § PATTERNS/common/verify-seed-on-fork-base.md`) — keeping `origin/main` current removes the fork-base-mismatch class entirely.
- **Pairs with the worktree-base preamble** (`KB § PATTERNS/architect/branching-and-merging.md § 16.7`) — R4 prevents the stale base; the preamble recovers from it when prevention has not yet propagated.
- **Amends *project-close push gate*** (`KB § PATTERNS/architect/project-execution.md § 2.10`) — the project-close push is now per-increment + presented + user-gated, not a blanket close action.
- **Custodial-monitor family** — sibling of `disk-usage-monitor` / `mole` / `hound`: a script emitting state + `next_action`, wired as a pre-dispatch + close gate. Same shape, different resource (merge debt vs disk vs storage vs code hygiene).

s1 (user frustration-flagged the recurring stale-base cost) → s2 (memory `feedback_phased_push_policy`) → **s3 (this doc + CLAUDE.md pointer + INDEX.md)** → s4 (`scripts/merge-debt-monitor.sh` + its tests — the gate-as-tooling already shipped; the *protocol* stays judgment-/human-gated at s3 because the per-increment go/no-go is intentionally non-automatable).

## 7. Anti-patterns

- **One massive N-projects push at branch end.** The exact backlog-growing move R4 forbids; engineers fork stale the whole time.
- **Pushing without the per-increment present + go.** General delegation is not per-push authorization; a 59-commit FF was correctly blocked for this.
- **Treating the merge-debt monitor as advisory.** It is a gate. ≥1 closed project unmerged is a stop-and-phase-push signal, not a "noted."
- **`--force` / blanket FF to "clear the divergence."** Destroys the per-increment verification contract; never substitutes for the presented, verified, approved increment.

---

**Memory:** `feedback_phased_push_policy`. **CLAUDE.md:** §1 *Phased-push policy* pointer. **Tooling:** `scripts/merge-debt-monitor.sh`. **Companion:** `KB § PATTERNS/common/verify-seed-on-fork-base.md` (the gap this cures), `KB § PATTERNS/architect/project-execution.md § 2.10` (project-close gate), `KB § PATTERNS/architect/branching-and-merging.md § 16.7`.
