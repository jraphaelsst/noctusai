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

## 4a · Cache-first reflex — what makes the dispatch worth doing

A dispatched engineer that opens `grep` / `Read` / `Glob` before a single MCP cache call has paid the full cold-start tax (§1) AND the platform's embedding-refresh cost (every pre-commit / post-merge / post-checkout / pre-push) for nothing — the engineer is rediscovering, not consuming, the index the caches exist to be.

The cache-first discipline is therefore **in the standing protocol**, not in each brief:

- `engineer-seed.md §0` is the top-of-protocol reflex (cache before grep/Read; depth at `KB § PATTERNS/common/cache-as-agent-tool.md`).
- Every executor specialist's L1 (`backend-engineer` / `frontend-engineer` / `devops-engineer`) and every advisor's L1 (`architect` / `compliance-reviewer` / `security`) carries the same rule as a domain-bullet, and `cache-as-agent-tool.md` is in each `owns_kb:` so the agent-context cache pulls the depth into the engineer's compact bundle at spawn.

**Brief-author rule (the corollary).** If you find yourself writing *"use `noctus.graph.report` for orientation"* or *"start with `kb_search`…"* in a brief, **the agent definition is the surface to fix, not the brief**. The whole point of the agent layer is to make these reflexes default by construction — re-spelling them per dispatch is the brief defeating itself. Symptom: the same cache-first reminder copied across 3+ briefs ⇒ the rule belongs in `.claude/agents/<lens>.md` (or the standing protocol if cross-lens), not in brief boilerplate.

**Future keeper** (s1 → s3 once recurrence flips it). A `check_dispatched_engineer_cache_first_reflex` keeper could audit engineer transcripts (the `/tmp/.../tasks/<agentId>.output` JSONL) for the first tool call: if the engineer opens `Bash grep` / `Glob` / a whole-file `Read` of an unfamiliar path BEFORE any `mcp__noctusai__noctus_dev_*_search` / `mcp__noctusai__noctus_graph_*`, surface a `scoped-improvement:` candidate. Not yet codified — surfaced here as the natural next mechanization once we have N≥2 measured drift instances.

## 4b · Brief template safety section — surface-and-resume tool names

Every engineer brief SHOULD include the following safety footer so the engineer knows the
surface round-trip is one tool call away (not a manual process):

```
## Safety rules (non-negotiable)
- Worktree isolation: stay in YOUR worktree, never the primary checkout.
- Stage-only: `git add <explicit paths>` — never `-A` or `.`.
- No commit, no push — architect-only.
- 🔴 NEVER `--no-verify`. If a hook fails or you hit a genuine blocker:
    call `noctus.dev.surface_to_tech_lead(reason, proposal_md, current_state_md, attempted_resolution_md)`
    print the returned `exit_marker_msg` as your FINAL output line and stop.
    Tech-lead responds via `noctus.dev.respond_and_resume` +
    `noctus.dev.dispatch_resume_brief` — the round-trip is cheap + lossless.
    KB § PATTERNS/common/surface-and-resume-tooling.md.
```

The tool names (`surface_to_tech_lead` / `respond_and_resume` / `dispatch_resume_brief`)
are what make the round-trip ergonomic. Without them in the brief, engineers may not know
the tools exist. Brief author rule: include this block OR reference `engineer-seed §1c`
(which now contains the same pointer). Don't spell out the tool names PER dispatch — point
to the standing protocol instead to stay DRY.

---

## 4c · Mandatory brief language for safety (closing the `--no-verify` commit loophole)

§4b above describes the **mechanics** (which tools the engineer uses to surface). This section pins the **verbatim language** the brief MUST carry so the engineer can't claim "the brief didn't say." The standing protocol (`engineer-seed.md §9` Bash safety + the 5-rationalization catalog at `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`) IS the contract; the brief language is the audit trail that the tech-lead surfaced it at dispatch time.

**Verbatim phrase the brief MUST contain** (copy as-is into every engineer brief):

> **NEVER use `--no-verify` (commit OR push). NEVER `--force`. If a hook fails or any safety gate refuses (even a known false-positive), STOP and surface as a surface-note (`kind="surface"`); return blocked. The "commit-only is harmless" rationalization is forbidden.** Tech-lead resolves.

That single block routes to the 5 rationalization anti-patterns + the surface protocol + ea7514e7 worked example at `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` via the standing protocol. Brief authors MAY add slice-specific overrides (e.g., "this slice IS authorized to commit `--no-verify` for the KB-autostage-hook bypass per `engineer-seed.md §2`; rationale must be in commit message") — but the verbatim block stays as the baseline.

**Why the dual coverage (commit AND push) is load-bearing.** Pre-commit hooks fire on `git commit`, NOT on `git push`. Bypassing commit = bypassing every keeper (`kb_sync` · `check_claude_md_router` · `check_eight_way_sync` · keeper-pattern-cache refresh). The "commit-only is the smaller bypass" intuition has the direction backwards: a `commit --no-verify` skips strictly more guarantees than a `push --no-verify` does. The `ea7514e7` build-learn-cache codification slip (2026-05-29, see `bypass-rationalization-anti-patterns.md § 3`) is the canonical evidence — agent rationalized "commit-only, not push, so it's fine" and silently shipped a `--no-verify` commit to its worktree branch, which was then pushed unverified.

**Why mandatory in the brief AND in the agent.** The standing protocol (`engineer-seed.md §9`) IS the contract. The brief carries it for two reasons: (a) **audit trail** — `git log --grep "NEVER use --no-verify"` shows the tech-lead surfaced the discipline at every dispatch, closing the "I didn't know" silent-error shape; (b) **future keeper detection** — a `check_dispatch_brief_carries_safety_language` keeper (s4 candidate, deferred to N≥2 measured brief drift) scans the briefs for the verbatim string. Born 2026-05-29 after the `ea7514e7` post-hoc-detected slip forced the rule's codification.

**Composes with:** §4b above (mechanics — `surface_to_tech_lead` round-trip) · `engineer-seed.md §9 Bash safety` (standing protocol — the contract IS) · `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` (the 5 rationalization shapes + surface protocol + ea7514e7 worked example) · `KB § PATTERNS/common/drift-fix-on-contact.md` (Roles split sibling) · `KB § PATTERNS/common/dispatch-with-project-and-notes.md` (surface-note infra the engineer uses).

## 5 · Provenance

Audit + L1/L2/L4 shipped 2026-05-25 (this session). L3 (`wire_env`) shipped same session by a parallel engineer. **Lesson (the reason this doc trusts measurement over docs):** claude-code-guide asserted a `tools:` allowlist *removes* non-allowed tools from injected context (a real token cut). Dogfooding the very change disproved it — the deferred-name list is session/connector-global and persisted (295 names) under the scoped agent (CC v2.1.150). The asserted ~12k L1 token win was **false**; L1's real value is least-privilege. *Measure the dispatch you just tuned; an LLM's "this saves tokens" is a hypothesis, not a result.* Re-measure if the harness version or connected-MCP-server/connector set changes (`.mcp.json` had `noctusai, docker, n8n, waha, supabase` + client-injected `claude_ai_*`/chrome connectors — the `claude_ai_*` 104 are the bloat's bulk, cut via L7).
