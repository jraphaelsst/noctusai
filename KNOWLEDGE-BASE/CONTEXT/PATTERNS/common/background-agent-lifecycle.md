# Background-agent lifecycle - hand back, salvage, stop; and never touch a peer session

**The rule (owner, 2026-11-07).** A dispatched background agent ends when its purpose is done; the dispatcher stops it at once; the leader inherits whatever was left. Sessions that are not ours are never stopped unless the owner says so.

**Why.** The leader's footer showed 4 subagents and 23 shells "running" about 1h20m after each agent had handed back. The agents were idling on "Polling for HW-RUN DONE" and "Waiting for nnl2.out". `ListAgents` said "completed", but the harness holds a finished agent (and its shell tasks, which were no longer OS processes) until the leader calls `TaskStop`. Idle holders are footer noise, wake on stray messages and keep their worktree claims looking alive. Composes with `dont-block-on-background.md` (the leader must not idle-poll either).

## The four legs

1. **Agent side - the hand-back is the LAST act.** No polling, sleep loop, `until grep` wait or run-log wait after it (and none instead of it). Waiting on something you cannot finish (a hw-admission slot, a CI run, a peer)? Name that leftover in the hand-back and end. Standing text: `.claude/agents/product-engineer.md` §4.
2. **Dispatcher side - on every hand-back: salvage, then `TaskStop` that agent immediately**, not at session end. Salvage = work (commits/branch/pointer) + learnings, the legs in `learn-before-archive.md` "Stopping an agent or session is a teardown too" (landing via `feat/methodology-agent-stop-salvage`; link, do not copy). Procedure: `.claude/skills/noc-branch-dispatch/SKILL.md` step 5b.
3. **The leader takes over leftovers** (an unfinished verdict, a pending push, a queued run): it runs, files or tracks them itself (`release_steward action=request`, a pointer note, a reminder). Leftovers are never parked in an idle agent.
4. **Never stop another SESSION.** Peer sessions run in the owner's environment. "End idle agents" means YOUR OWN dispatched agents and shells only; stopping, steering or re-scoping a peer needs the owner's say-so. Informing a peer is allowed and encouraged (`orchestration-craft-canon.md` §6.13), and a notice is information, not a stop order: each session/agent decides how to proceed in its own environment and does not pause for the owner because of it. If the notice reveals a conflict or error, silence is not OK: reply to the sender/steward and resolve it together (`orchestration-craft-canon.md` §6.13).

## Waiting and ending (decision 2026-11-10: `project-history/assistant-chatbot/queue-lifecycle-decision.md`)

- **Waiting (live when D1 lands).** A subagent with a queued delivery hands back, names it as the leftover and ends; it never polls. A top-level session with a pending delivery keeps building and does ONE `release_steward action=mine` per 15 min, riding the owner's load-check cadence (no loop agent), plus at natural checkpoints.
- **Ending (not live until builds 3+5: rebased-twin cleanup fix, end predicate in `mine`).** A session/agent ends ITSELF only when the `mine` end predicate is true (all requests LANDED, plus DEPLOYED if asked, or ejected-with-transfer; no open `mq/*` ref; no unlanded rescue of its slug; no depended-on CI run in flight). Teardown goes LAST: it salvages its own worktrees through `task_branch landed confirm=True` as the final act, never while a CI run it depends on is in flight (a salvage once cancelled the CI it waited on). Worktrees of dead requesters go to the steward / mole sweep. Ejection handling: `release-steward.md` § 7a.

## Backstop - `claude-guard-background-agent-idle.py` (advisory, never stops anything)

- **Events:** `PostToolUse` (all tools) and `UserPromptSubmit`, registered in `.claude/settings.json`. A task-notification (the hand-back) wakes the leader into tool calls, so PostToolUse is the event that reliably runs while the leader is acting; it throttles to one scan per 45 s per session.
- **Data source (verified 2026-11-07 on 33 real transcripts):** `/private/tmp/claude-<uid>/<project>/<session-id>/tasks/<agentId>.output` is a symlink to `~/.claude/projects/<project>/<session-id>/subagents/agent-<agentId>.jsonl`; `agent-<agentId>.meta.json` beside it carries `"finished": true` once the run ended (running agents have no such key). The hand-back may be a `SubagentHandback` tool_use or a final text turn, so the meta flag, not the transcript tail, is the signal. Agents that kept working after hand-back (polling, run-log waits) show up as appended rows after the hand-back.
- **Report:** an agent of THIS session (the tasks dir is keyed by the payload's `session_id`; a peer is never seen) that is `finished`, quiet for 3 min and not already `TaskStop`ped in the leader transcript is named in `additionalContext`, once, re-reminded every 20 min. Hooks firing inside a subagent skip.
- **Fail open, fast (<2 s):** any error is a silent no-op with a stderr line. It is not `primary-write` (fail-closed, 8 s): a lifecycle advisory must never wedge the leader.
- **Telemetry:** one row per reported agent in `guard-events.ndjson` (gitignored, under the primary's .claude/cache) (`guard=background-agent-idle`, `agent_id`, `idle_s`); recurrence = `jq -r 'select(.guard=="background-agent-idle")' guard-events.ndjson | wc -l`. Falling to ~0 is the success measure; a persistent count means the dispatcher step is skipped.
- **Limits:** TaskStop outcomes are not observable beyond the leader transcript; a stopped agent is recognised only by its `TaskStop` line (the transcript path must be in the payload). Delivery of PostToolUse `additionalContext` to the leader is the documented hook contract but was not observable from inside this build; the stderr line is the fallback and the telemetry counts regardless.

## Background processes - they end themselves (owner decision 2026-11-14)

**Measured problem.** 8 cores / 8 GB, 5 GB of swap, load ~130: sessions left retry/poll loops (`until grep ...; sleep`), stuck deliverable checks and test runs whose owner went away. One leftover retry script ran 4 h unnoticed. The first design (an idle watcher: 45 min without CPU or output) was REJECTED by the owner: any lifetime cap or idle timer can kill long in-flight work. **There is no max lifetime, no idle timer and no auto-report of idle processes anywhere** (a test pins that).

**The rule.** A background process declares its purpose and an end condition at launch and ends itself when it is met; it salvages its own output and leaves nothing behind. Scope is only this session's own `run_in_background` shells and their child trees, never a session, never a peer's processes (same boundary as leg 4 above).

| Leg | Mechanism |
|---|---|
| Construction | `scripts/bg_run.py --purpose ".." --done ".." [--done-when "<shell check, exit 0 = done>"] -- <command>` (`--long-lived` for infrastructure: purpose only). Ends when the command exits OR `--done-when` succeeds; then tree-stops the command's process group (own session, so orphans re-parented to init are still found), verifies none survives, writes its own salvage record. A looping command without `--done-when` is refused by the wrapper itself. |
| Refusal at launch | PreToolUse guard `claude-guard-background-launch.py` -> `bg_launch_guard.py` on Bash with `run_in_background=true`: denies `while`/`until` loops, `sleep N`, `tail -f`, `watch`, `--watch`, and bare long runs (pytest, vitest, playwright, vite build, npm test/build, `hw_admission run`, `gh run watch`) unless wrapped with `--purpose` + `--done` (or `--long-lived`). Allowed without the wrapper: known infrastructure (`core.INFRA_PATTERNS`: steward `--merge-queue watch` / `--release-steward heartbeat`, MCP servers, dev servers, Claude app, IDEs, browsers) and anything neither open-ended nor long-running. No escape hatch. Fail-closed (`[noc-guard:background-launch]`). |
| Safety net | `noctus.dev.session_end_sweep` lists this session's still-running background processes (`background_processes`); `clean_wrap` is False and `wrap_blockers=["background_processes"]` until each is salvaged + stopped via `noctus.dev.bg_process action=stop`, or kept as declared long-lived (`action=declare`, purpose only, no lease). `clean_wrap=None` = unmeasured, never green. Whoever ends the session owns its leftovers; nobody inherits orphans. |
| Stop tool | `noctus.dev.bg_process` (`--bg-process`): `list` (dossier: pid tree, command, age, cwd, output file + tail, what it waits on; a hw-admission slot waiter is explained, not exempted) / `declare` / `undeclare` / `salvage` / `stop`. `stop` REFUSES to signal until a salvage record exists (output tail saved outside git, in the gitignored per-machine cache dir (bg-process/salvage below .claude/cache), reason, learnings; whoever stops records it), then TERM root-first (a `while true` shell cannot respawn), wait, KILL survivors, verify no orphans (`survivors` / `orphans_remaining`). Refuses a peer's pid, infrastructure, live declarations, and its own claude chain. |
| Telemetry | `guard-events.ndjson` rows (`guard=background-launch` denies; `guard=background-process` salvaged/stopped), salvage records (ndjson) and the wrapper run logs. |

**Ownership signals (verified 2026-11-14).** Hooks and the MCP server find their session's `claude` process by walking up from their own pid; background shells are its children; a detached shell counts only when its command carries `/<session_id>/`. "Parent is pid 1" alone is never an orphan test (the steward's watchers detach on purpose). Stdout of a task shell is often a socket or `/dev/null`, so the output file is mapped only when a task `.output` is open; otherwise the dossier says so.

**Limits.** The guard is regex scanning: a script that loops internally (`./poll.sh`) is not seen; the session-end net catches it. The wrapper cannot recover children it never started in its own session.

**Fix-on-contact (same change).** `claude-guard-background-agent-idle.py` re-reported agents whose `TaskStop` returned `No task found with ID`; that error result now counts as stopped.

Tests: `mcp/noctusai/tests/test_bg_process.py` (fake `ps` + fake kill; never a real signal).

## Construction + checks

| Leg | Where |
|---|---|
| Agent text | `.claude/agents/product-engineer.md` §4 (all executors inherit it) |
| Dispatcher text | `.claude/skills/noc-branch-dispatch/SKILL.md` step 5b |
| Backstop + telemetry | `scripts/hooks/claude-guard-background-agent-idle.py` -> `guard-events.ndjson` |
| Tests | `mcp/noctusai/tests/test_background_agent_lifecycle_hooks.py` (fixture tasks dirs + transcripts) · `test_bg_process.py` (background processes) |

The executor-dispatch guard was considered for appending an "end when done" clause to briefs and rejected: it denies/allows, it does not rewrite briefs, and the standing protocol every executor already references carries the clause once, in one place.

Related: `dont-block-on-background.md` · `orchestration-craft-canon.md` §6.13 (change propagation, the same fail-open pull-hook shape) · `background-engineer-safety-discipline.md`.
