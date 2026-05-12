# Two-Session Architect/Operator — Pattern

> **What this is.** A working agreement for splitting one Claude Code workspace into **two concurrent sessions** that play distinct roles:
> - **Session A — Architect** (conversation, ideation, KB/CLAUDE.md edits, user-facing decisions, memory writes).
> - **Session B — Operator** (autonomous orchestration: dispatch engineer subagents, validate worktrees, commit, cherry-pick, push, archive, run hound/mole).
>
> Both sessions run in the same noc repository (or sibling workspace). They coordinate through a lightweight file-based mailbox at the repo root — `dispatcher-inbox.md` (architect → operator) and optionally `dispatcher-outbox.md` (operator → architect). Both mailbox files are **gitignored** — transient coordination state, not history.
>
> **What this is NOT.** A replacement for the branching-first orchestration pattern (`KB § PATTERNS/branching-and-merging.md § 16-18`). It is an *organizational layer above it* — the architect still plans, the engineers still build in isolated worktrees, but the **handoff to git mechanics** moves from the architect's session to the operator's session. The architect's session stops touching git directly; it appends task entries to the inbox.
>
> **Cross-references.** `KB § 01-PHILOSOPHY.md § Branching-first orchestration` + `§ Roles: Architect + Engineers`, `KB § PATTERNS/branching-and-merging.md § 17-18`, `KB § PATTERNS/project-execution.md § 2.10 Commit per phase, push at project close`, memory `feedback_branching_first_orchestration.md` + `feedback_orchestrator_role.md`.

---

## 1. Overview — why two sessions

The branching-first pattern already chunks orchestration into **architect (orchestrator)** + **engineers (subagents)**. The architect plans, dispatches engineers in a single tool-use turn, evaluates findings, and FF-merges branches at phase close. While engineers are running in their isolated worktrees, the architect stays available to the user for ideation.

In practice, two things happen that strain one session:

1. **The architect's session accumulates git mechanics tail-work** — cherry-picks, FF-merges, pushes, project-close archiving, hound/mole sweeps. These are *autonomous*, *mechanical*, and *interrupt the user-facing conversation*. They also fill context that should be spent on user ideation.
2. **The user wants to keep talking while the operator chews.** A 20-minute cherry-pick batch + push verification + archive sweep is dead time for the conversation. The user thinks-with the architect; they don't think-with the cherry-picker.

The two-session split:

- **Session A — Architect.** Stays with the user. Plans, dispatches, evaluates engineer findings *as content* (not as git artifacts), edits KB/CLAUDE.md when methodology evolves same-session, writes memory entries, surfaces decisions. **Never touches git directly.**
- **Session B — Operator.** Runs autonomously (or on `/loop`). Watches `dispatcher-inbox.md`. Picks up tasks top-down, executes them, writes outcomes to `dispatcher-outbox.md`, clears the inbox entry. Owns ALL git operations.

The architect gains uninterrupted conversation time. The operator gains focused autonomous execution without context pollution from user chat.

### When to use the two-session split

Use it when:

- **Tempo is high** — multiple dispatches per hour, each with cherry-pick + FF-merge tail-work.
- **Conversation is active** — the user is ideating, designing, or interrogating during a build batch.
- **Methodology is evolving same-session** — KB/CLAUDE.md edits + memory writes happen alongside engineer dispatches; mixing the two in one session pollutes both.
- **Wave-based dispatch is in play** — Wave N+1 gates on Wave N FF-merge (`KB § PATTERNS/branching-and-merging.md § 18`); the operator owns that gate so the architect doesn't context-switch into git on every wave boundary.
- **Project close is imminent** — final commit + push + folder deletion is *the literal last step* and benefits from a dedicated session to run uninterrupted.

### When single-session is fine

- **Trivial direct fixes** (single file, single commit, no dispatch).
- **Pure conversation / pure planning** (no engineers in flight, no merges pending).
- **The user prefers one window** — the split has a setup cost; not worth it for a 15-minute session.
- **No methodology evolution mid-batch** — single-session has lower coordination overhead when the architect isn't editing KB/memory.

The tempo threshold (rough rule of thumb): if you'd otherwise be flipping between "let me cherry-pick that real quick" and "back to the design question" more than **3 times in an hour**, split.

---

## 2. Roles — exact ownership map

### 2.1 Architect Session (A)

**Owns:**
- Conversation with the user (ideation, design, interrogation, sign-off).
- Project planning and PROJECT.md authoring/revision.
- Engineer dispatch *briefs* (the architect writes the brief; the operator may execute the dispatch — see §2.3 for the split).
- Reading engineer findings as **content** (slips, lessons, surprises) and folding them into methodology.
- KB / CLAUDE.md / `CLAUDE/<topic>.md` edits when methodology evolves same-session.
- **Memory writes** — `feedback_*.md` files + MEMORY.md index entries.
- Triage decisions (formalize / refactor / accept-with-rationale).
- Surfacing decisions and open questions to the user.

**Never touches:**
- `git add` / `git commit` / `git push` / `git cherry-pick` / `git merge` / `git branch -m` / `git worktree add` / `git worktree remove`.
- Project archival (folder deletion at close).
- `noctus.hound.scan` sweeps run as autonomous tail-work (architect may *request* them via the inbox; operator runs them).
- `noctus.dev.archive` invocations.
- `bash scripts/mole.sh sweep --force`.

**Authority over memory:** architect writes; operator may read. This prevents clobbering. If the operator surfaces a finding worth memorializing, it routes through the outbox; the architect reads + writes the memory entry.

### 2.2 Operator Session (B)

**Owns:**
- Watching `dispatcher-inbox.md` (manual re-read at each turn, or `/loop` interval).
- ALL git operations: `add`, `commit`, `push`, `cherry-pick`, `merge --ff-only`, `branch -m`, `worktree add/remove`, tag operations. **Post-cherry-pick MUST cleanup the source worktree** (`git worktree unlock` if needed, `git worktree remove --force`, `git branch -D`) — see `KB § PATTERNS/storage-hygiene.md § 4.4`. Cherry-pick that leaves the source worktree on disk is incomplete work (the 2026-05-12 THE-P11 incident traced 9 GB of accumulation to this gap).
- Engineer dispatch *execution* when the architect's brief is in the inbox (the operator opens the Task tool-use, hands the brief verbatim, collects the report, writes outcome to outbox).
- Worktree validation (post-engineer-finish: confirm branch exists, diff matches brief, no surprise files).
- Project close mechanics — final commit, folder deletion, FF-to-main, push.
- Tail-work sweeps — `noctus.hound.scan` between waves, `bash scripts/mole.sh scan` pre-dispatch, `bash scripts/disk-usage-monitor.sh`, stale worktree cleanup.
- KB sync verification — `bash scripts/verify-kb-sync.sh` after the architect edits KB.
- End-of-session verification — `pytest` / `vite build` per the §1 universal rule "Finish the session — verify, don't assume".

**Never touches:**
- The user-facing conversation. The operator does NOT message the user with design questions; it routes them through the outbox so the architect surfaces them.
- KB / CLAUDE.md / memory writes. (Operator may read; only the architect writes — clobber prevention.)
- PROJECT.md *design* edits. Operator may update §11 Change Log entries that record git mechanics (commits, merges, archives); design changes are architect-only.
- Triage decisions. Operator flags candidates via outbox; architect decides.

**Authority over engineers:** when the inbox contains a dispatch brief, the operator IS the orchestrator for that brief. It dispatches, evaluates the engineer's report, and either (a) merges + reports success to outbox, or (b) reports a gap to outbox for architect to absorb.

### 2.3 The dispatch brief — who writes, who executes

Two valid shapes:

**Shape 1 — Architect writes, Operator executes (default).**
The architect drafts a focused brief (per `KB § PATTERNS/branching-and-merging.md § 17.6`) including the §17.6 Write-authorization paragraph, posts it as an inbox entry with `Type: dispatch`. The operator picks up the brief, runs `git worktree add`, opens the Task tool, hands the brief verbatim, collects the report, validates the worktree, cherry-picks/FF-merges, writes outcome to outbox.

**Shape 2 — Architect writes AND executes (single-session fallback).**
When the architect is between user turns and the dispatch is small (≤2 engineers, ≤200 LoC each), the architect may dispatch directly. The operator skips that dispatch. This is the *graceful degradation* shape — useful when the operator is mid-task or the architect just wants to keep momentum.

Shape 1 is the default. Shape 2 is the carve-out; logged in outbox as "self-dispatched" so the operator knows not to duplicate.

---

## 3. Coordination — inbox and outbox files

### 3.1 File locations

- **Inbox:** `dispatcher-inbox.md` at repo root.
- **Outbox:** `dispatcher-outbox.md` at repo root (optional but recommended).

Both **gitignored** (see §5). They are transient coordination state, not history. Project artifacts (PROJECT.md, findings.md, §11 Change Log) remain the durable record.

### 3.2 Inbox format

```markdown
# Dispatcher Inbox

Architect (Session A) appends tasks at the bottom of "Pending"; Operator (Session B)
consumes top-down and moves entries to "Completed (last 24h)" on completion.

## Pending

### 2026-05-11T14:32 — DISPATCH-ENGINEER-K-DOC-SPLIT
- Type: dispatch
- Brief: <inline brief OR path to brief file>
- Worktree: .claude/worktrees/agent-engineer-k/
- Branch: doc-split-2026-05-11
- Acceptance: 5 files staged on branch, no commit; report 5-question rubric inline.

### 2026-05-11T14:50 — CHERRY-PICK-FROM-ENGINEER-M
- Type: cherry-pick
- Source branch: engineer-m-foo
- Source SHA: 1a2b3c4
- Target branch: main
- Acceptance: FF clean, push, report tip SHA.

### 2026-05-11T15:10 — ARCHIVE-PROJECT-CLOSE
- Type: archive
- Project: projects/foo-bar/
- Acceptance: noctus.dev.archive; final commit + push; folder deleted on main.

## Completed (last 24h)

### 2026-05-11T13:05 — HOUND-SCAN-PRE-DISPATCH ✅
- Type: other
- Action: noctus.hound.scan; next_action=absorption
- Outcome: queue empty; safe to dispatch.
```

**Format rules:**
- Each entry is a level-3 heading: `### YYYY-MM-DDTHH:MM — <SHORT-NAME>`.
- Required fields: `Type:`, `Acceptance:`.
- `Type:` ∈ `dispatch | cherry-pick | merge | push | archive | hound-scan | mole-sweep | kb-verify | other`.
- Operator appends ` ✅` (or ` ❌` + reason) to the heading when moving to Completed.
- Operator may consume any pending entry; default order is top-down by timestamp.

### 3.3 Outbox format

```markdown
# Dispatcher Outbox

Operator (Session B) appends outcomes here; Architect (Session A) reads at next turn.

## Recent

### 2026-05-11T14:48 — DISPATCH-ENGINEER-K-DOC-SPLIT ✅
- Engineer reported: 5 files staged on doc-split-2026-05-11.
- Diff summary: 1 KB pattern (new), 1 INDEX row, 1 CLAUDE.md row, 1 PROJECT.md (new), 1 inbox template (new).
- Worktree validated: clean stage, no surprise files.
- Action taken: none yet — awaiting architect sign-off before cherry-pick (acceptance said "no commit").
- Question for architect: <if any>

### 2026-05-11T15:02 — CHERRY-PICK-FROM-ENGINEER-M ✅
- Cherry-picked 1a2b3c4 onto main.
- Pushed origin/main; new tip 5d6e7f8.
- Verification: `pytest mcp/noctusai/tests/` green (47 passed).
```

**Format rules:**
- Same heading shape as inbox.
- Operator includes enough context that the architect can absorb without re-running diff: file count, line count, key paths, test outcome.
- Surface questions/decisions for the architect inline; do NOT take design decisions autonomously.

### 3.4 Lifecycle

1. Architect appends to inbox `## Pending`.
2. Operator reads inbox (manual at each turn, or `/loop` polls).
3. Operator picks top-most pending entry, executes, validates.
4. Operator appends outcome to outbox `## Recent`.
5. Operator moves inbox entry from `## Pending` to `## Completed (last 24h)` with status icon.
6. Architect reads outbox at next conversation turn, absorbs outcome, decides next action.

Stale entries: anything older than 24h in `## Completed (last 24h)` is rolled out (deleted, or moved to a per-day archive section if the user wants).

---

## 4. Git ownership — strict separation

The operator owns ALL git operations. The architect runs **zero** git commands.

This is non-negotiable for collision prevention. Two sessions racing on `git add` / `git commit` / `git push` in the same repo can:
- Stage files from each other's working tree (`git add .` is the worst offender — already banned platform-wide; the two-session rule makes it structurally impossible for the architect to repeat the mistake).
- Lose commits to non-fast-forward push contention.
- Create accidental octopus merges.

The architect's discipline: **never type `git ...` in Session A.** Every git intent becomes an inbox entry.

### 4.1 What the architect does instead

| Architect intent | Inbox entry type |
|---|---|
| "Commit Phase 3 work" | `commit` (Phase 3 staged files; brief lists them) |
| "Push the project-close branch" | `push` (branch name; verify-clean expectation) |
| "FF-merge engineer K's branch" | `cherry-pick` or `merge` (source branch, target) |
| "Set up worktree for parallel batch" | `worktree-add` (path + branch base) |
| "Archive this project" | `archive` (project folder path) |
| "Clean stale worktrees" | `mole-sweep` (or `worktree-prune`) |

The architect drafts the brief in conversation with the user; the operator executes mechanically.

### 4.2 Same-session carve-out (rare)

The architect MAY run git in two narrow cases:
1. **Reading-only**: `git status`, `git log`, `git diff`, `git branch --show-current`. These are inspections, not state changes.
2. **The operator is unreachable AND a project-close gate is hot.** Logged in the outbox as "architect-side override — operator unavailable" so the next operator turn doesn't duplicate.

Anything else routes through the inbox. If it feels urgent, add the entry and move on; the operator picks it up next turn.

---

## 5. Memory + KB ownership

### 5.1 Memory

- **Architect writes** memory entries (`feedback_*.md` + MEMORY.md index).
- **Operator may read** memory to align behavior with established rules.
- Operator-spotted methodology gap → outbox entry → architect drafts the memory write.

Why architect-only writes: memory is the durable rule layer. Two writers race on MEMORY.md index lines. The architect is the broad-context session that already evaluates methodology evolution; concentrating writes there preserves coherence.

### 5.2 KB + CLAUDE.md

- **Architect writes** KB pages, CLAUDE.md, `CLAUDE/<topic>.md`.
- **Operator runs `bash scripts/verify-kb-sync.sh`** when architect signals (via outbox-direction request, or pre-commit hook fires anyway).
- Operator-spotted KB drift → outbox entry → architect edits.

### 5.3 Three-way sync (KB / CLAUDE.md / memory)

Three-way sync (`KB § 01-PHILOSOPHY.md § Docs stay in sync`) stays in the architect's hands end-to-end. The operator's only role is running the verifier script and FF-merging the resulting commit.

---

## 6. MCP tool ownership

Both sessions use MCP tools. Coordinate via task list + inbox/outbox to avoid stepping on each other.

**Architect-typical:**
- `noctus.dev.agent_context` (session bootstrap).
- `noctus.dev.product_context`, `noctus.dev.refs`, `noctus.dev.outline*`, `noctus.dev.scan_*` (analysis).
- `noctus.dev.scaffold_product`, `noctus.dev.scaffold_migration` (creation gestures — the architect plans; if the actual `git add` after scaffold matters, the architect *plans* the scaffold and the operator runs the tool when staging matters).
- `noctus.dev.file_proposal`, `noctus.dev.set_proposal_status` (proposal lifecycle).
- `noctus.dev.improvements`, `noctus.dev.phase_learning_log/query/consume`.

**Operator-typical:**
- `noctus.hound.scan` (pre/post-dispatch hygiene gates).
- `noctus.dev.archive` (project close).
- `noctus.dev.validate` / `noctus.dev.validate_product` (post-merge verification).
- `noctus.dev.status`, `noctus.dev.review`, `noctus.dev.review_session`.
- Supabase MCP for migration deploy at project close (rare; architect plans, operator runs).

**Shared (either session):**
- Read-only tools: `list_products`, `get_product`, `inspect_product`, `available_ports`, etc.

When in doubt: read-only tools either session; state-changing tools (scaffold, archive, file_proposal status change) prefer the side that owns the parent gesture (architect plans → operator executes if staging matters; architect runs directly if no git touch needed).

---

## 7. Anti-patterns

- **Concurrent `git push` from both sessions.** Banned by the git-ownership rule (§4); the inbox is the single funnel.
- **Architect editing the outbox.** The outbox is the operator's report channel; architect read-only. If the architect wants to capture something, it goes in PROJECT.md §11 or memory.
- **Both sessions editing the outbox.** Same shape as the git-ownership collision — operator-only writes; architect read-only.
- **Operator surfacing design decisions directly to the user.** Operator routes through outbox; architect surfaces. Skipping this conflates the two voices and breaks the user's mental model.
- **Inbox-as-PROJECT.md.** Inbox entries are gestures (commit, merge, dispatch); they are not the project record. The PROJECT.md remains the durable artifact.
- **Memory clobbers from operator.** Operator never writes `feedback_*.md`. If it really matters, surface to outbox; architect writes.
- **Stale inbox.** Operator must clear (move-to-Completed or delete) consumed entries. A growing inbox = the operator is behind; the architect notices via outbox quietude and pauses dispatches.
- **Both sessions running `noctus.dev.archive` on the same project.** The operator-only rule covers archive; architect must not.
- **Operator dispatches without architect brief.** Operator is a mechanic, not a planner. If the inbox is empty, operator runs hound/mole/verify sweeps or idles.
- **Architect runs git "just this once."** Single carve-out (§4.2 — read-only or operator-unreachable). Beyond that, the discipline degrades fast.

---

## 8. Setup recipe

Two terminal windows, two Claude Code sessions, same repo (or sibling workspace), same branch by default.

### 8.1 Launch architect session

```bash
cd /Users/<you>/Documents/repository/NoctusAI/noctusai/
claude
```

Then in the session:
- Tell Claude: *"You are the **Architect** (Session A). Read `KB § PATTERNS/two-session-architect-operator.md`. Never run git directly; route all git intents through `dispatcher-inbox.md`. Stay with me for conversation, planning, and KB/memory edits."*

### 8.2 Launch operator session

In a second terminal:
```bash
cd /Users/<you>/Documents/repository/NoctusAI/noctusai/
claude
```

Then in the session:
- Tell Claude: *"You are the **Operator** (Session B). Read `KB § PATTERNS/two-session-architect-operator.md`. Watch `dispatcher-inbox.md`; consume entries top-down; write outcomes to `dispatcher-outbox.md`. You own ALL git operations. Run hound/mole/verify sweeps when idle."*

### 8.3 Bootstrap the inbox/outbox

If they don't exist yet (operator can do this):
```bash
# Operator (one-time):
test -f dispatcher-inbox.md || cp templates/dispatcher-inbox-template.md dispatcher-inbox.md
test -f dispatcher-outbox.md || printf '# Dispatcher Outbox\n\n## Recent\n' > dispatcher-outbox.md
```

(The repo-root `dispatcher-inbox.md` shipped with this pattern serves as both the working file AND the canonical shape — gitignored, so the first launch already has the structure.)

### 8.4 First handoff smoke test

- Architect: append a no-op entry to inbox:
  ```markdown
  ### 2026-05-11T15:00 — SMOKE-TEST
  - Type: other
  - Action: confirm operator reads inbox and writes outbox.
  - Acceptance: outbox contains echo entry within one operator turn.
  ```
- Operator: reads inbox, appends echo to outbox, moves entry to Completed.
- Architect: reads outbox, confirms the loop works. Proceed with real work.

---

## 9. The `/loop` autonomous variant

The operator can be launched in `/loop` mode (see Skill `/loop`) to poll the inbox autonomously without architect prompting.

**Setup:**
- Operator session: `/loop 2m read dispatcher-inbox.md and execute any pending entries; write outcomes to dispatcher-outbox.md; idle if nothing pending`.

**Behavior:**
- Every 2 minutes the operator re-reads the inbox.
- Executes pending entries.
- Idles (reports "no pending") when the inbox is clear.

**When to use `/loop`:**
- Long architect-side conversations where dispatches are intermittent.
- Overnight / lunch-break batches (architect drafts a queue, operator chews through it on its own pace).

**When to skip `/loop`:**
- High-tempo bursts where the operator should react *immediately* on inbox append (manual turn is faster than 2-minute poll).
- Anything destructive — the operator should never `/loop` over `mole-sweep --force` or `archive` unless the architect explicitly authorizes per-entry.

**Safety:** the `/loop` operator MUST treat each entry as authoritative-on-arrival; if an entry says "ASK FIRST" (or `Auto-execute: ask-first`), the operator routes to outbox and waits. No autonomous destructive ops without an explicit `Auto-execute: yes` flag in the inbox entry.

---

## 10. Decision rubric — pilot vs defer

Five questions for the user before adopting:

1. **Tempo check.** In the last working day, did you flip between "code mechanics" and "design conversation" more than 3 times per hour? *(If yes → pilot; if no → defer.)*
2. **Conversation pressure.** Are there ideation/design topics waiting in queue *right now* that the architect could be working on if it weren't doing cherry-picks? *(If yes → pilot.)*
3. **Wave-based dispatch usage.** Are you running multi-wave dispatches where each wave gates on FF-merge? *(If yes → pilot — the operator owns the gate.)*
4. **Two-window comfort.** Are you comfortable monitoring two Claude Code sessions at once? *(If no → defer — single-session is fine for solo focus.)*
5. **Setup-cost tolerance.** Are you willing to invest ~10 minutes on the first day to write the bootstrap prompts, run the smoke test, and verify the loop? *(If no → defer until tempo justifies it.)*

**3+ "yes" → pilot now. ≤2 "yes" → defer; revisit when tempo climbs.**

---

## 11. Relation to single-session-autonomous-subagent (Option D)

A sibling pattern — **Option D, autonomous-operator-via-subagent** — sketches the single-session variant where the architect dispatches a long-running "operator subagent" inside the same Claude Code session, rather than a second top-level Claude window. The trade-offs:

| Dimension | Two-session (this pattern) | Single-session autonomous subagent (Option D) |
|---|---|---|
| Concurrency | True — two top-level Claudes run independently | Bounded by the architect session's turn lifecycle |
| Setup cost | ~10 min (two windows, two bootstrap prompts) | ~2 min (one window, one dispatch) |
| Conversation latency | None — architect stays available throughout | Architect blocks while subagent runs |
| Git collision risk | Mitigated by strict §4 ownership rule | Naturally serialized — subagent runs inside one session |
| Best for | High-tempo + active conversation + multi-wave | Trivial tail-work where architect doesn't need to talk |

Use this pattern when the conversation pressure (rubric Q2) dominates. Use Option D when the architect just wants to hand off a small mechanical batch without leaving the window. The two patterns are **not mutually exclusive** — same workspace, same architect can choose per-batch.

---

## 12. Living-document note

This pattern is **methodology-in-pilot** as of 2026-05-11. The first real run is the user's call (see §10 rubric). Findings — slips, mistakes, lessons, surprises — go into `projects/two-session-architect-operator-pattern/findings.md` as the pilot runs. The pattern evolves with the findings; expect amendments to:

- Inbox/outbox format (after 1-2 batches, the shape will tighten).
- Carve-out rules (the strict git ownership may soften slightly if the smoke-test edge cases warrant).
- `/loop` cadence (2 minutes is a first guess; may move to 1m or 5m).

When the pilot proves the pattern, three-way sync the working agreement: this KB page (already created), CLAUDE.md §3 routing row (already pointing here), memory entry (new — `feedback_two_session_architect_operator.md`).
