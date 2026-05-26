# Agent Context Architecture — 4-layer model + owns_kb + cache

**What it is.** How `.claude/agents/<name>.md` is shaped so a dispatched specialist arrives **pre-contextualized for its domain** without paying for every dispatch in auto-load tokens. Mirrors the CLAUDE.md (router) ↔ KB (depth) pattern: the agent file is the **specialist index**, KB holds the **depth**, and a forthcoming cache holds the **compact extract**. Codified 2026-05-26.

**Why.** Three forces shape the design:

1. **Dispatch is expensive.** Subagent-heavy workflows can hit ~7× the tokens of a single-thread session — every Agent invocation re-loads CLAUDE.md + the agent's `.md` body + any triggered skills (with full bodies). The agent file IS the per-dispatch system prompt; bytes there compound across every parallel branch.
2. **A fat charter drifts.** The dev_team source charters (~75-120 lines each) are rich but duplicate KB content — three places to keep in sync (charter ↔ KB ↔ memory) and only one keeper currently covering them. The router pattern (CLAUDE.md §1 = one-line rule + `→` pointer per rule) demonstrated that **a lean index over canonical depth** stays fresh by construction.
3. **The user mandate.** *"Transfer part of the knowledge base into the agents contexts itself, so they are well contextualized without having to search for context every time they are dispatched"* — interpreted as **routing in the agent file, depth in KB, on-demand pulls via Read or (Phase B) cache lookup.** Not inline duplication.

## The 4 layers

```
L0  CLAUDE.md §1                                ← auto-loaded ONCE per session
    universal common-ground                       (zero per-dispatch duplication)
       │
L1  .claude/agents/<name>.md                    ← auto-loaded per dispatch
    specialist INDEX (~45-65 lines)              · frontmatter + owns_kb
                                                  · `> Inherits CLAUDE.md §1` opener
                                                  · Mission (≤2 lines)
                                                  · Domain rules: rule + → pointer
                                                  · Depth pointers (echoes owns_kb)
       │
L2  KB § <domain>/...                            ← loaded ON-DEMAND via Read
    depth bodies                                  (or Phase B cache lookup)
       │
L3  per-dispatch brief                           ← architect inlines per call
    tight files + acceptance                      (already codified — engineer-default §11)
```

The cache boundary (L0 + L1 = stable / cacheable; L2 + L3 = variable) maps directly to Claude Code's globally-cacheable system prompt vs per-turn content split — staying lean on L1 keeps the cache hot.

## owns_kb: contract

**Every L1 agent file declares its domain territory in frontmatter.** The territory is **full-domain** — `PATTERNS/`, `GUIDES/`, `INTEGRATIONS/`, and `CONTEXT/<domain>/` paths the agent is the canonical owner of. A new KB doc landing under an owned path **MUST** appear as a pointer in the agent body the same commit (keeper-enforced).

```yaml
---
name: backend-engineer
description: ...
tools: ...
model: sonnet
owns_kb:
  - CONTEXT/PATTERNS/backend.md
  - CONTEXT/PATTERNS/database-rls.md
  - CONTEXT/PATTERNS/pydantic-strict-http.md
  - CONTEXT/PATTERNS/seed-fake-real-adapter.md
  - CONTEXT/backend/01-CORE.md
  - CONTEXT/backend/04-DATABASE.md
  - CONTEXT/GUIDES/new-product.md
  - CONTEXT/INTEGRATIONS/oauth-patterns.md
---
```

Rules:
- **Exclusive ownership** — each KB path appears in **exactly one** agent's owns_kb (with one carve-out below). Shared/multi-domain content stays in `CONTEXT/PATTERNS/` un-owned (universal — every agent is expected to know it).
- **Shared-multi-domain carve-out** — a KB doc genuinely needed by ≥2 specialists declares `agent_owners: [...]` in its own frontmatter (Phase B; until then, paths claimed by ≥2 agents fail the keeper with a "needs shared-multi-domain declaration" message).
- **Body-pointer mirror** — every owns_kb path appears at least once in the body as a `KB § <path>` pointer (keeper-enforced; otherwise the declaration is dead).
- **`engineer-default.md` exempt** — it's the protocol meta-doc, not a specialist; owns no KB.

## Keeper enforcement (3 legs, mirroring the keeper-pattern-cache contract)

**Leg 1 — `check_agent_kb_alignment` (Phase A, this commit).** For each `.claude/agents/<name>.md` with `owns_kb:`:
- (a) every declared path **exists** on disk.
- (b) every declared path is **referenced** in the agent body as a `KB § <path>` pointer.
- (c) no path is **double-claimed** by two agents (until shared-multi-domain frontmatter ships).
- (d) every `CONTEXT/<domain>/`, `CONTEXT/PATTERNS/*.md`, `CONTEXT/GUIDES/*.md`, `CONTEXT/INTEGRATIONS/*.md` is **claimed** by ≥1 agent OR lives in a small unowned-allowlist (universal-content register at the top of `compliance.py`).

Severity `high`. Wires into `check_all_products` + `cli.py --validate` + pre-commit (via the existing harness-keeper sweep).

**Leg 2 — Agent-context cache + freshness keeper (Phase B — SHIPPED 2026-05-26).** Sibling of `.claude/cache/keeper-patterns.sqlite`. See **§ Agent-context cache** below for the final API + the third-sibling [[scoped-auto-improvement]] cache.

**Leg 3 — `kb_sync` pre-commit pointer-resolvability (existing, applies automatically).** The existing CLAUDE.md §4 sync rule already blocks unresolved `KB § …` pointers. The new agent-file pointers ride this rail for free.

## Agent-context cache (Phase B — SHIPPED 2026-05-26)

**The pattern.** `.claude/cache/agent-context.sqlite` (gitignored) — local mirror of each agent's body + a compact extract of every owned KB doc. At dispatch time, the architect (or any tool) queries `noctus.dev.agent_context(agent="backend-engineer")` and gets a single round-trip with the agent body + owned-KB highlights, instead of N Read calls. Implementation: `mcp/noctusai/tools/noctus/dev/agent_context_cache.py` (core) + `agent_context.py` (MCP wrappers) + `check_agent_context_cache_freshness` keeper + pre-commit refresh + CLI `--refresh-agent-context-cache` / `--agent-context <name>` / `--check-agent-context-cache-freshness`. The third-in-family sibling cache [[scoped-auto-improvement]] ships alongside.

**Mirror contract** (analog of the keeper-pattern-cache's "memory should always be the keeper mirror"):

| Leg | Mechanism |
|---|---|
| Eager pre-commit refresh | `scripts/hooks/pre-commit`: if any `.claude/agents/*.md` OR any owned KB path is staged → `cli.py --refresh-agent-context-cache` runs before the commit lands. |
| Lazy query-time refresh | `agent_context_cache.lookup()` compares `cache_meta.agent_<name>_sha` vs live `sha256(<agent>.md + concat(owned_kb))`; mismatch → rebuilds + answers. |
| Loud freshness gate | `check_agent_context_cache_freshness` (severity high): cache missing / unreadable / stale → fails `validate`. Sibling of `check_keeper_cache_freshness`. |

**Schema sketch** (final shape lands in Phase B):

```sql
CREATE TABLE agent_context (
  agent_name      TEXT NOT NULL,        -- 'backend-engineer'
  section_kind    TEXT NOT NULL,        -- 'body' | 'domain-rule' | 'owned-kb-extract' | 'pointer'
  section_path    TEXT,                 -- KB path for owned-kb-extract; NULL for agent-body
  section_value   TEXT NOT NULL,        -- the body / rule / extract
  source_sha      TEXT NOT NULL,        -- sha256 of the source file
  cached_at       TEXT NOT NULL
);
CREATE INDEX idx_agent_section ON agent_context(agent_name, section_kind);

CREATE TABLE cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL                   -- per-agent source_sha, populated_at
);
```

**Why defer implementation.** Phase A establishes the methodology authority + owns_kb declarations — the cache is a derivative artifact of those declarations. Shipping the cache without stable owns_kb risks a Phase-A-rewrites-the-cache loop.

## Drift-fix-on-contact composition

The agent-context architecture composes with [[drift-fix-on-contact]] in two specific shapes:

1. **A domain pointer broken on-contact** (a `KB § <owned>` pointer 404s when an agent tries to follow it) ⇒ the agent **pauses, resolves the pointer (fix KB or fix agent body), surfaces if blocked, continues paused work**. Silent-skip = silent error.
2. **A new KB lesson landing under owned territory without an agent-body pointer** is itself drift — keeper blocks on commit; the author resolves on-contact by adding the pointer line same commit.

## Anti-patterns

- **Bake KB body INTO agent file.** The fat-charter trap — duplicates depth, drift factory, expensive auto-load. The agent file is an INDEX; KB is the body.
- **Inline universal-rules duplication.** Re-stating CLAUDE.md §1 in every agent. CLAUDE.md is already auto-loaded — duplication is pure cost.
- **`owns_kb` without body pointers.** Declaration-only ownership is dead — the keeper requires the path appears in the body.
- **Author-without-keeper-lookup.** Authoring a gated doc without first running `--keeper-pattern-lookup` (cf. [[keeper-check-before-docing]]) puts you on the slow path: author → get gated → patch → re-stage. Query upfront, **before** doc'ing, so the keeper doesn't gate you.
- **Cross-domain pointer creep.** An agent body that pointers heavily into another agent's owned territory is a routing-failure tell — escalate to the architect for either an ownership transfer or a shared-multi-domain declaration.

## Composes with

[[keeper-pattern-cache]] (sibling cache pattern; the agent-context cache is its analog) · [[keeper-check-before-docing]] (the cache-query-upfront discipline applies here — query keepers BEFORE authoring a new agent file so you don't get gated) · [[claude-md-router-discipline]] (CLAUDE.md §1 = the L0 common-ground; this pattern is its L1 sibling) · [[methodology-codification-pipeline]] (s4 keepers are the source of truth the cache mirrors) · [[parallelization-first-orchestration]] (lean L1 keeps every parallel-dispatch wall-clock low) · [[drift-fix-on-contact]] (on-contact rule for broken pointers + un-pointed owned KB) · [[dispatch-engineer-tuning]] (the cost-rationale parent for the lean-index choice).
