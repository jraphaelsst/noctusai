# Dispatch-engineer tuning — making background engineers fast & cheap

**What this is.** The measured cold-start cost of a dispatched engineer subagent + the levers that cut it. Born 2026-05-25 from a live audit: read a *running* engineer's first-message token usage and found ~65k tokens loaded **before any useful work**, most of it waste. Sibling of `KB § PATTERNS/architect/branching-dispatch.md` (the dispatch RUNBOOK — this is the per-engine *efficiency* layer), `KB § PATTERNS/common/self-branching-mode.md` (§5a worktree env), `KB § PATTERNS/common/agent-reading-discipline.md` (narrow-read).

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
| `engineer-seed.md` | 3k | ✅ |
| MCP-server instructions + brief | ~2k | ✅ |

The **deferred-tool list** looked like the cheapest waste to kill — every engineer is handed the names of `mcp__docker__*`, `mcp__cloudflare__*`, `mcp__n8n__*`, `mcp__waha__*`, `mcp__supabase__*`, all `claude_ai_*` connectors (**104 names!**), Chrome, Stripe, Figma, Gmail… ~300 tools it never invokes. **⚠️ MEASURED CORRECTION (2026-05-25, §3): a per-agent `tools:` allowlist does NOT remove these.** The deferred-name list is **session/connector-global** — a function of the *connected* MCP servers (`.mcp.json`) + the user's claude.ai account connectors — independent of any agent's `tools:`. A scoped engineer's first delta still carried 295 names (docker 19 · cloudflare 26 · claude_ai_* 104 · waha/n8n/supabase 38 · noctusai 126). So cutting this bloat is a **session/account lever** (disable unused connectors — see L7), NOT a per-agent one. `engineer-seed.md` having shipped without a `tools:` allowlist was still worth fixing — for **least-privilege/safety**, not tokens.

---

## 2 · The levers (status as of 2026-05-25)

| # | Lever | Mechanism | Win | Status |
|---|---|---|---|---|
| **L1** | **Scope `tools:`** on `engineer-seed.md` | allowlist `Bash, Read, Edit, Write, Grep, Glob, mcp__noctusai__*` **gates INVOCATION** to file/search/shell + the noctusai toolkit (`mcp__<server>__*` wildcard works). **⚠️ Measured (§3): does NOT remove the deferred-tool *names* from injected context** — 295 names persist regardless | **least-privilege/safety, ~0 token saving** (NOT ~12k as first asserted): engineer can't invoke WhatsApp / delete CF DNS / run docker / **dispatch** (no `Agent` tool ⇒ "engineers execute, never dispatch") | ✅ shipped (for safety) |
| **L2** | **`model: sonnet`** default + Opus-on-demand | frontmatter sets the subagent default; the Agent/Task `model: opus` param overrides per-dispatch | biggest **wall-clock** lever — mechanical, fully-specified briefs don't need Opus latency; architect (Opus) plans, engineer (Sonnet) executes | ✅ shipped (reversible — see §4) |
| **L3** | **Worktree env pre-wire** | `noctus.dev.task_branch action=start wire_env=True` symlinks PRIMARY `node_modules` + re-points `@noctusai/{lib,seed}` at the worktree (§5a recipe) | engineer can `vite build`/`vitest` in its own worktree instead of the slow hand-wire dance (was *the* biggest time-sink building ResourceManager) | ✅ shipped |
| **L4** | **Scoped verification** | brief Acceptance names the narrowest check (one test file / one product build / one grep); the full compliance gate is the **architect's** single integration-time run on a clean tree | saves 5-6 min × every engineer in a wave | ✅ codified in `engineer-seed.md §6a` |
| **L5** | **Tight, concrete briefs** | exact `Files-to-modify` + a grep/test Acceptance line removes the engineer's exploration phase | the real speed win — exploration, not model speed, dominates a loose dispatch | ✅ standing (`engineer-seed.md §11`) |
| **L6** | **Stale-worktree hygiene** | `noctus.dev.mole` / `noctus.dev.cleanup_stale_worktrees` (dry-run default; never touches locked/active/uncommitted) | 28 stale worktrees = 2.6 GB clutter slowing creation + disk; sweep between waves | 🔁 run between waves |
| **L7** | **Disable unused claude.ai connectors** (the REAL deferred-bloat cut) | the ~10k deferred-name bloat is dominated by **104 `claude_ai_*` connector names** (Ahrefs/Canva/Daloopa/DevRev/Docusign/Figma/Gamma/Harvey/Moody's/Postman/S&P/Udemy/Windsor/Cloudinary/Atlassian/Clarify…) — none used in noc dev. These come from the **user's claude.ai account connector settings**, not the repo → turning off the unused ones at the account/workspace level drops them from *every* session's deferred list (main + all subagents) | ~the only lever that actually shrinks the deferred bloat (L1 can't — it's session/connector-global) | ⏳ **user action** (account-level, surfaced) |

**Not adopted (with rationale):**
- **Project-level `disallowedTools: ["mcp__docker__*", …]`** — would also blind the *main* session (architect legitimately drives docker/n8n/waha/supabase) **and** (per the L1 measurement) likely wouldn't strip the deferred *names* anyway. The connector-disable (L7) is the right cut for the unused `claude_ai_*` chunk. ❌
- **`model: haiku`** — Haiku doesn't support Tool Search ⇒ loads *all* tools upfront, defeating L1. Sonnet is the floor. ❌
- **Trim `CLAUDE.md`/`MEMORY.md` auto-load** — biggest single chunk (~41k) but (a) `CLAUDE.md` is the shared router; trimming is lossless-doc-refactor *surgery* affecting the main session too (`KB § PATTERNS/common/lossless-doc-refactor.md`), and (b) there is no reliable per-agent opt-out of `MEMORY.md` in `.md` frontmatter without `autoMemoryEnabled:false` globally (which hurts the architect's recall). Deferred as a separate, deliberate effort — **named here so it's non-silent**. ⏳

---

## 3 · How to verify a tuning change worked

After a tuning change, dispatch one engineer and read its first-message `usage` (§1 method) — **measure, don't assume** (this section exists because an asserted win was measured false). What 2026-05-25 actually found, scoped engineer `adf5aaaee` (Sonnet) vs unscoped `ae6ef9672` (Opus):
- **`model`** correctly flipped to `claude-sonnet-4-6` (frontmatter applied). ✅ L2 works.
- **deferred-name list did NOT shrink** — `grep -m1 -oE '"addedNames":\[[^]]*\]'` on the transcript still showed **295 names** incl. docker/cloudflare/`claude_ai_*` despite the `tools:` allowlist. ❌ L1 is not a token lever.
- `cache_creation` ~53k→~51k (≈2k, within noise of differing brief sizes) — confirms the deferred bloat persisted.
Greppable one-liners (extract only the number, never dump the JSONL): `grep -m1 -oE '"cache_creation_input_tokens":[0-9]+' <f>` ; `grep -m1 -oE '"model":"claude-[a-z0-9-]+"' <f>`. Agent `.md` files are read **at spawn** ⇒ edits apply to the *next* dispatch even before commit.

---

## 4 · The one reversible decision: engineer model

`model: sonnet` is a **reversible default**, surfaced loudly because the platform values quality (*"quality is the constraint"*). The safety design:
- **Default Sonnet** for the mechanical, fully-specified majority (the engineer-seed contract: execute, never plan).
- **Architect escalates** a genuinely ambiguous / architectural / judgment-heavy slice to Opus at dispatch (`model: opus` on the Agent call). This is a brief-scoping decision the architect owns — hard work must not ride Sonnet *silently*.
- **Flip the floor** by changing one frontmatter line (`model:` in `engineer-seed.md`) — e.g. back to `opus`, or `inherit` to track the parent.

If engineer output quality drops on mechanical work, that's a **brief-tightness** signal (L5) before it's a model signal — under-specified briefs fail on any model.

---

## 5 · Provenance

Audit + L1/L2/L4 shipped 2026-05-25 (this session). L3 (`wire_env`) shipped same session by a parallel engineer. **Lesson (the reason this doc trusts measurement over docs):** claude-code-guide asserted a `tools:` allowlist *removes* non-allowed tools from injected context (a real token cut). Dogfooding the very change disproved it — the deferred-name list is session/connector-global and persisted (295 names) under the scoped agent (CC v2.1.150). The asserted ~12k L1 token win was **false**; L1's real value is least-privilege. *Measure the dispatch you just tuned; an LLM's "this saves tokens" is a hypothesis, not a result.* Re-measure if the harness version or connected-MCP-server/connector set changes (`.mcp.json` had `noctusai, docker, n8n, waha, supabase` + client-injected `claude_ai_*`/chrome connectors — the `claude_ai_*` 104 are the bloat's bulk, cut via L7).
