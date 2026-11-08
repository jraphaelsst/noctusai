# Background-agent lifecycle - hand back, salvage, stop; and never touch a peer session

**The rule (owner, 2026-11-07).** A dispatched background agent ends when its purpose is done; the dispatcher stops it at once; the leader inherits whatever was left. Sessions that are not ours are never stopped unless the owner says so.

**Why.** The leader's footer showed 4 subagents and 23 shells "running" about 1h20m after each agent had handed back. The agents were idling on "Polling for HW-RUN DONE" and "Waiting for nnl2.out". `ListAgents` said "completed", but the harness holds a finished agent (and its shell tasks, which were no longer OS processes) until the leader calls `TaskStop`. Idle holders are footer noise, wake on stray messages and keep their worktree claims looking alive. Composes with `dont-block-on-background.md` (the leader must not idle-poll either).

## The four legs

1. **Agent side - the hand-back is the LAST act.** No polling, sleep loop, `until grep` wait or run-log wait after it (and none instead of it). Waiting on something you cannot finish (a hw-admission slot, a CI run, a peer)? Name that leftover in the hand-back and end. Standing text: `.claude/agents/engineer-seed.md` §4.
2. **Dispatcher side - on every hand-back: salvage, then `TaskStop` that agent immediately**, not at session end. Salvage = work (commits/branch/pointer) + learnings, the legs in `learn-before-archive.md` "Stopping an agent or session is a teardown too" (landing via `feat/methodology-agent-stop-salvage`; link, do not copy). Procedure: `.claude/skills/noc-branch-dispatch/SKILL.md` step 5b.
3. **The leader takes over leftovers** (an unfinished verdict, a pending push, a queued run): it runs, files or tracks them itself (`release_steward action=request`, a pointer note, a reminder). Leftovers are never parked in an idle agent.
4. **Never stop another SESSION.** Peer sessions run in the owner's environment. "End idle agents" means YOUR OWN dispatched agents and shells only; stopping, steering or re-scoping a peer needs the owner's say-so. Informing a peer is allowed and encouraged (`orchestration-craft-canon.md` §6.13), and a notice is information, not a stop order: each session/agent decides how to proceed in its own environment and does not pause for the owner because of it. If the notice reveals a conflict or error, silence is not OK: reply to the sender/steward and resolve it together (`orchestration-craft-canon.md` §6.13).

## Backstop - `claude-guard-background-agent-idle.py` (advisory, never stops anything)

- **Events:** `PostToolUse` (all tools) and `UserPromptSubmit`, registered in `.claude/settings.json`. A task-notification (the hand-back) wakes the leader into tool calls, so PostToolUse is the event that reliably runs while the leader is acting; it throttles to one scan per 45 s per session.
- **Data source (verified 2026-11-07 on 33 real transcripts):** `/private/tmp/claude-<uid>/<project>/<session-id>/tasks/<agentId>.output` is a symlink to `~/.claude/projects/<project>/<session-id>/subagents/agent-<agentId>.jsonl`; `agent-<agentId>.meta.json` beside it carries `"finished": true` once the run ended (running agents have no such key). The hand-back may be a `SubagentHandback` tool_use or a final text turn, so the meta flag, not the transcript tail, is the signal. Agents that kept working after hand-back (polling, run-log waits) show up as appended rows after the hand-back.
- **Report:** an agent of THIS session (the tasks dir is keyed by the payload's `session_id`; a peer is never seen) that is `finished`, quiet for 3 min and not already `TaskStop`ped in the leader transcript is named in `additionalContext`, once, re-reminded every 20 min. Hooks firing inside a subagent skip.
- **Fail open, fast (<2 s):** any error is a silent no-op with a stderr line. It is not `primary-write` (fail-closed, 8 s): a lifecycle advisory must never wedge the leader.
- **Telemetry:** one row per reported agent in `guard-events.ndjson` (gitignored, under the primary's .claude/cache) (`guard=background-agent-idle`, `agent_id`, `idle_s`); recurrence = `jq -r 'select(.guard=="background-agent-idle")' guard-events.ndjson | wc -l`. Falling to ~0 is the success measure; a persistent count means the dispatcher step is skipped.
- **Limits:** TaskStop outcomes are not observable beyond the leader transcript; a stopped agent is recognised only by its `TaskStop` line (the transcript path must be in the payload). Delivery of PostToolUse `additionalContext` to the leader is the documented hook contract but was not observable from inside this build; the stderr line is the fallback and the telemetry counts regardless.

## Construction + checks

| Leg | Where |
|---|---|
| Agent text | `.claude/agents/engineer-seed.md` §4 (all executors inherit it) |
| Dispatcher text | `.claude/skills/noc-branch-dispatch/SKILL.md` step 5b |
| Backstop + telemetry | `scripts/hooks/claude-guard-background-agent-idle.py` -> `guard-events.ndjson` |
| Tests | `mcp/noctusai/tests/test_background_agent_lifecycle_hooks.py` (fixture tasks dirs + transcripts) |

The executor-dispatch guard was considered for appending an "end when done" clause to briefs and rejected: it denies/allows, it does not rewrite briefs, and the standing protocol every executor already references carries the clause once, in one place.

Related: `dont-block-on-background.md` · `orchestration-craft-canon.md` §6.13 (change propagation, the same fail-open pull-hook shape) · `background-engineer-safety-discipline.md`.
