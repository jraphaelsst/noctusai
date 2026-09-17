# Claim vs evidence — never delete on a written claim about shared state

> **Rule.** When a tool is about to DESTROY shared state (remove a worktree, drop a stash,
> delete a branch, truncate a ledger), a *written claim* that the state is disposable is not
> sufficient. Check the state itself. If liveness cannot be established, REFUSE — unknown is
> not consent.

Born 2026-09-16/17: **five** distinct instances of the same shape landed within two days, one of
them destroying two engineers' in-flight work. Each tool asked a cheap question whose answer
*looked* authoritative, and acted irreversibly (or, for the fifth, silently mis-durably) on it.

---

## The shape

A destructive tool needs to know "is anyone still using this?". There are two kinds of answer:

| | source | property |
|---|---|---|
| **Claim** | a flag, a status field, a label, a name, an ancestry check | cheap, writable by anyone (including another automated tool), can be stale or wrong |
| **Evidence** | file mtime, a directory existing, rows present on the remote, a live process | costs a syscall or a fetch, describes what IS |

The failure is always the same: the tool reads a claim, treats it as evidence, and deletes.
The claim is usually *true most of the time* — which is why it got trusted, and why the bug
survives review.

## The five instances (all 2026-09-16/17, all in `mcp/noctusai/tools/noctus/dev/`)

1. **`0 commits ahead` read as "merged".** `cleanup_stale_worktrees force=True` removed 9
   worktrees, two of which had been created ~6 minutes earlier with engineers working in them.
   `git merge-base --is-ancestor` is trivially true for a fresh fork (a commit is its own
   ancestor), so "nothing unmerged" and "nothing ever written" are indistinguishable.
   **Evidence available and ignored:** the directory's age, and its files' mtimes.
2. **Pointer auto-flipped to a terminal status.** The guard added for (1) refused removal while
   the branch-tree pointer was non-terminal — but `session_end_sweep` had already auto-healed a
   live worktree's pointer to `shipped` ("branch integrated into dev"), so the guard concluded
   nobody was there while the session was still working. A guard reading a field that another
   automated tool rewrites is reading a claim, not evidence.
3. **The guard failed OPEN.** The same predicate returned "not blocking" when the pointer query
   yielded nothing — unknown branch, unreadable ledger, query error. Absence of a claim was
   read as permission to delete.
4. **Append-only ledgers labelled "benign refresh artifacts".** `project-history/*.ndjson` is on
   `_benign_stash.BENIGN_REFRESH_PATTERNS`, because those files ARE usually hook side-effects.
   They are also the durable ledgers agents append rows to. The auto-stash swept 25 unpushed
   rows into the shared stash; they survived only because the session that later dropped those
   entries recovered them first (`3789fefc`) and archived the dropped stashes.
5. **`REPO_ROOT`, bound once at MCP-server-boot, read as "the durable checkout".** Every
   `project-history/*.ndjson` writer's default root was `settings.REPO_ROOT` —
   `workspace.get_noctusai_home()`, which deliberately STOPS at a `.claude/worktrees/<slug>/`
   boundary so code-editing tools land in the caller's own worktree (correct for THAT job). A
   ledger writer trusting that same value as "where durable state lives" is a claim, not
   evidence: the evidence — is this path physically under `.claude/worktrees/`, an ephemeral
   tree torn down by the next sweep? — was never checked. `session_end_sweep` fell back to
   `REPO_ROOT` and wrote two summary rows into a worktree's own
   `project-history/worktree-salvage.ndjson`; `deliver_trailing_ledgers`'s own "primary checkout
   MUST be on `dev`" safety net also skipped (that worktree's HEAD was on a feature branch, not
   `dev`), so nothing pushed them either. Recovered only by a human noticing.

## A fifth failure axis: implicit resolution masquerading as a durability guarantee

Instances 1-4 are a tool reading a WRITTEN claim (a status field, an ancestry check) instead of
live evidence. Instance 5 is the same shape one layer down: a tool reading an IMPLICIT
resolution (a module constant computed once, from wherever the process happened to boot) as if
it were a structural guarantee ("this is the repo"), when the actual guarantee it needed
("this is somewhere durable, not a worktree") was never asserted. The fix is the same posture —
name what you actually need (durability, not "the resolver's default") and check for it
explicitly (`workspace.get_ledger_root()` — unwraps the worktree boundary instead of trusting
whatever the boundary-stopped resolver returned).

## How to apply

- **Name which kind of answer you have.** Before a destructive branch, write down whether the
  input is a claim or evidence. If it is a claim, find the corresponding evidence.
- **Evidence outranks an operator flag.** `force=True` may override a *cost* heuristic (this
  tree is old, this file is big). It must not override evidence of current activity. State the
  asymmetry explicitly in the tool's docstring and pin it with a test.
- **Fail closed on unknown.** A failed query, an unreadable path, a missing record ⇒ refuse and
  say why. Unknown liveness is not consent.
- **Two writers, one field ⇒ it is a claim.** If any automated tool can rewrite the field you
  are reading, you cannot treat it as ground truth. Either make the writer unable to write the
  disposable value while evidence contradicts it, or stop reading that field for this decision.
- **Prefer a reversible holding area that is not silently dropped.** A stash is loss-shaped: a
  later drop deletes it, and the shared stack means the drop may not be yours. For append-only
  files, a WIP commit is strictly better — `project-history/*.ndjson` is `merge=union` in
  `.gitattributes` precisely so a commit always rebases safely.
- **Every refusal reports its reason** in the result payload. A silent skip is the same defect
  class one level up (`KB § PATTERNS/common/drift-fix-on-contact.md` — silent-skip = silent
  error).
- **Salvage before delete stays mandatory** (`KB § PATTERNS/common/storage-hygiene.md § 2.3`).
  These guards reduce how often salvage is the only thing between a mistake and lost work; they
  do not replace it.

## Worked outcome

- `b297ad6b` — live-pointer + min-age guards, shared by `cleanup_stale_worktrees` and `mole`
  via `_worktree_staleness` (instance 1).
- `feat/worktree-liveness-not-just-ledger` — auto-heal may not write a terminal status while the
  worktree directory exists; filesystem mtime as liveness independent of the ledger; the
  fail-open closed (instances 2 and 3).
- `_benign_stash` / `task_branch` — ledgers get a `chore(ledger)` commit instead of a stash;
  caches and regenerated docs stay stashable (instance 4).
- `feat/ledger-writes-target-primary` — `workspace.get_ledger_root()` (unwraps the worktree
  boundary `get_noctusai_home()` deliberately stops at) + `settings.LEDGER_ROOT`; every
  `project-history/*.ndjson` writer's implicit default now resolves there, never to wherever
  the MCP server happened to boot (instance 5).

> Sibling rules: `KB § PATTERNS/common/methodology-execution-discipline.md` (verdict-channel
> integrity — the exit code you read must belong to what you are judging; same "is this answer
> actually about the thing I am deciding?" question, applied to test results rather than to
> shared state) · `KB § PATTERNS/common/storage-hygiene.md` (salvage-before-delete) ·
> `KB § PATTERNS/architect/branch-tree-tracking.md` (the pointer ledger these guards read).
