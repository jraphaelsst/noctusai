# Dispatch-engineer tuning — making background engineers fast & cheap

**What this is.** The measured cold-start cost of a dispatched engineer subagent + the levers that cut it. Born 2026-05-25 from a live audit: read a *running* engineer's first-message token usage and found ~65k tokens loaded **before any useful work**, most of it waste. Sibling of `KB § PATTERNS/branching-dispatch.md` (the dispatch RUNBOOK — this is the per-engine *efficiency* layer), `KB § PATTERNS/self-branching-mode.md` (§5a worktree env), `KB § PATTERNS/agent-reading-discipline.md` (narrow-read).

> **One-liner:** an engineer should boot with **its files + the noctusai toolkit + a tight brief — nothing else**. Every other token at spawn (400 unused tool names, the whole skill list, a model heavier than the task) is pure latency you pay on every dispatch.

---

## 1 · The cold-start tax (measured, not estimated)

Method (repeatable — **the audit IS the tool**): a background subagent's transcript is at `/private/tmp/.../<sessionId>/tasks/<agentId>.output` (JSONL). Its **first assistant message** carries `usage.cache_creation_input_tokens + input_tokens + cache_read_input_tokens` = the boot context. Read it; that's ground truth, not a guess.

Live engineer (`ae6ef9672df957715`, 2026-05-25) booted at **~65k tokens** before its first action:

| Loaded at spawn | ~tok | Engineer needs it? |
|---|---|---|
| `CLAUDE.md` (auto, 86 KB) | 21.6k | partially (router) |
| `MEMORY.md` (auto, ~77 KB) | ~19k | mostly ❌ |
| **deferred-tool list (~400 names)** | ~8–12k | ❌ — only `mcp__noctusai__*` ever called |
| skill listing (12 skills) | ~1.5k | ❌ |
| `engineer-default.md` | 3k | ✅ |
| MCP-server instructions + brief | ~2k | ✅ |

The **deferred-tool list** is the cheapest waste to kill and the highest-confidence win: every engineer was handed the names of `mcp__docker__*`, `mcp__cloudflare__*`, `mcp__n8n__*`, `mcp__waha__*`, `mcp__supabase__*`, all `claude_ai_*` connectors, Chrome, Stripe, Figma, Gmail… ~400 tools it never invokes. Root: `engineer-default.md` shipped **without a `tools:` allowlist** ⇒ inherited *all tools* (the agent registry literally read "Tools: All tools"). `orchestrator-operator` was already scoped — engineer-default just never got it.

---

## 2 · The levers (status as of 2026-05-25)

| # | Lever | Mechanism | Win | Status |
|---|---|---|---|---|
| **L1** | **Scope `tools:`** on `engineer-default.md` | allowlist `Bash, Read, Edit, Write, Grep, Glob, mcp__noctusai__*` ⇒ non-allowed MCP servers' tools are **removed from injected context** (confirmed: real token cut, not just invocation-gating; `mcp__<server>__*` wildcard works) | ~8–12k tok/dispatch + least-privilege (engineer can't send WhatsApp / delete CF DNS / run docker) + no `Agent` tool ⇒ enforces "engineers execute, never dispatch" | ✅ shipped |
| **L2** | **`model: sonnet`** default + Opus-on-demand | frontmatter sets the subagent default; the Agent/Task `model: opus` param overrides per-dispatch | biggest **wall-clock** lever — mechanical, fully-specified briefs don't need Opus latency; architect (Opus) plans, engineer (Sonnet) executes | ✅ shipped (reversible — see §4) |
| **L3** | **Worktree env pre-wire** | `noctus.dev.task_branch action=start wire_env=True` symlinks PRIMARY `node_modules` + re-points `@noctusai/{lib,seed}` at the worktree (§5a recipe) | engineer can `vite build`/`vitest` in its own worktree instead of the slow hand-wire dance (was *the* biggest time-sink building ResourceManager) | ✅ shipped |
| **L4** | **Scoped verification** | brief Acceptance names the narrowest check (one test file / one product build / one grep); the full compliance gate is the **architect's** single integration-time run on a clean tree | saves 5-6 min × every engineer in a wave | ✅ codified in `engineer-default.md §6a` |
| **L5** | **Tight, concrete briefs** | exact `Files-to-modify` + a grep/test Acceptance line removes the engineer's exploration phase | the real speed win — exploration, not model speed, dominates a loose dispatch | ✅ standing (`engineer-default.md §11`) |
| **L6** | **Stale-worktree hygiene** | `noctus.dev.mole` / `noctus.dev.cleanup_stale_worktrees` (dry-run default; never touches locked/active/uncommitted) | 28 stale worktrees = 2.6 GB clutter slowing creation + disk; sweep between waves | 🔁 run between waves |

**Not adopted (with rationale):**
- **Project-level `disallowedTools: ["mcp__docker__*", …]`** — would also blind the *main* session (architect legitimately drives docker/n8n/waha/supabase). Per-agent `tools:` allowlist is the scalpel; project-level deny is the sledgehammer. ❌
- **`model: haiku`** — Haiku doesn't support Tool Search ⇒ loads *all* tools upfront, defeating L1. Sonnet is the floor. ❌
- **Trim `CLAUDE.md`/`MEMORY.md` auto-load** — biggest single chunk (~41k) but (a) `CLAUDE.md` is the shared router; trimming is lossless-doc-refactor *surgery* affecting the main session too (`KB § PATTERNS/lossless-doc-refactor.md`), and (b) there is no reliable per-agent opt-out of `MEMORY.md` in `.md` frontmatter without `autoMemoryEnabled:false` globally (which hurts the architect's recall). Deferred as a separate, deliberate effort — **named here so it's non-silent**. ⏳

---

## 3 · How to verify a tuning change worked

After editing `engineer-default.md`, dispatch one engineer and read its first-message `usage` (§1 method). The `deferred_tools_delta` attachment should list **only** `mcp__noctusai__*` + core file tools, not the ~400-name set. Expected drop: 65k → ~50k boot (the ~12-15k of deferred-tool + skill bloat). `model` shows in the transcript's `message.model`. (Agent `.md` files are read **at spawn** ⇒ edits apply to the *next* dispatch even before commit.)

---

## 4 · The one reversible decision: engineer model

`model: sonnet` is a **reversible default**, surfaced loudly because the platform values quality (*"quality is the constraint"*). The safety design:
- **Default Sonnet** for the mechanical, fully-specified majority (the engineer-default contract: execute, never plan).
- **Architect escalates** a genuinely ambiguous / architectural / judgment-heavy slice to Opus at dispatch (`model: opus` on the Agent call). This is a brief-scoping decision the architect owns — hard work must not ride Sonnet *silently*.
- **Flip the floor** by changing one frontmatter line (`model:` in `engineer-default.md`) — e.g. back to `opus`, or `inherit` to track the parent.

If engineer output quality drops on mechanical work, that's a **brief-tightness** signal (L5) before it's a model signal — under-specified briefs fail on any model.

---

## 5 · Provenance

Audit + L1/L2/L4 shipped 2026-05-25 (this session). L3 (`wire_env`) shipped same session by a parallel engineer. Confirmed Claude Code mechanics (tools-allowlist token removal, `mcp__server__*` wildcard, `model:` frontmatter + per-dispatch override, Tool Search) via claude-code-guide, Claude Code v2.1+. Re-measure if the harness version or connected-MCP-server set changes (the deferred list is a function of connected servers — `.mcp.json` had `noctusai, docker, n8n, waha, supabase` + client-injected `claude_ai_*`/chrome connectors).
