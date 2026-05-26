# PROJECT — harness-agents-skills

> **Status:** ✅ CHECKPOINT — P1–P3 shipped on `feat/harness-agents-skills` (4 commits, hook-green). This branch is PARKED as the reverse-checkpoint / rollback point. Live testing happens on a fresh `test/harness-agents-skills` worktree. P6 memory-prune DEFERRED until after go-live (then audit-and-confirm).
> **Decisions (resolved):** A3 (two persona homes + shared §1) · B1+B3 (tech-lead-mediated consult + agno collaborate lane) · full-set build, **commit-per-phase** (supersedes single-commit) · aggressive-live CLAUDE.md + original & moderate backups · skill-scout pre-merge pass with licensed-find escalation to tech-lead→user.
> **Intent:** methodology / harness-restructure — REFINE, not replace; KB stays home. **Reversibility:** per-phase commits on an isolated branch + the parked checkpoint + `backup/` poles.

---

## §1 Context (the pain, grounded)

The platform is robust but **over-invests in two always-on channels + one flat tool surface, and under-invests in the harness primitives built for exactly this**:

| Channel | Measured | Loaded |
|---|---|---|
| `CLAUDE.md` | 268 lines / ~11.6k words (~15k tok) | **every turn** |
| `MEMORY.md` index | 82.8KB / 314 lines / **270 files** | **every session** (already overflowing — warning fired) |
| `KNOWLEDGE-BASE/` | 123 files / 28.5k lines | on-demand ✅ |
| MCP tools | **121** across 6 namespaces | named, deferred |
| Custom subagents | **2** (`engineer-default`, `orchestrator-operator`) | on dispatch |
| Custom `.claude/skills/` | **0** (dir doesn't exist) | — |

**Root insight.** The senior-specialist roster the user wants ALREADY EXISTS — as the `dev_team/` agno **charters** (Leader, Solution-Architect, Backend, Frontend, Security, Code-Reviewer≈compliance, QA, DevOps, PM, UX, Tech-Writer; Opus/Sonnet-tiered; per-role tool allowlists). It runs in a **separate paid agno runtime** via `noctus.team.*` — NOT in the Claude Code harness where day-to-day deving happens. The "reinventing the wheel" feeling is real: we're one step from re-authoring those personas as `.claude/agents`. The fix = **adapt the existing charters onto the Claude Code chassis**, not write new ones.

**Methodology framing (ties this into the existing s1→s4 codification ladder):** keepers are the codification primitive for *code shapes*. **Skills + specialized agents are the codification primitive for *procedures* and *roles*.** Same ladder (discipline → KB doc → mechanical primitive), next rung. Moves knowledge from *"the agent must REMEMBER to apply"* → *"the harness INJECTS/ENFORCES at the right moment."*

## §2 User mandate (quoted)

- Tech Lead = **the conversational agent** (me). Owns ALL git: branch / dispatch / hold-PRs-for-dependency / merge / push / deploy / bless. The main brain.
- Senior specialist agents — software engineer, architect, compliance, security (+ existing roster) — **run only when their domain is needed**, **callable mid-flight for advice**, each **isolated in its own branch off `dev`**, **commit only their own branch**.
- Orchestration runs **on the branching system**. Background agents NEVER commit on `prod` / `prod-backup` / `main` / `dev` / other agents' trees — **only their own**. Only the Tech Lead does broad git.
- Agents **contain automated workflows** to speed daily work.
- **Use `.claude/skills/`** (native Claude Code skills).
- **Single commit** (easy revert).
- **DRY** — when a procedure is absorbed into a skill, **DELETE the duplicate** from its old home.
- Container agent is live → **validate this structure works BEFORE committing**; stay isolated.

## §3 Goal

Stand up a native Claude-Code **skills + specialist-agents** layer, orchestrated by the Tech-Lead-via-branching model, that (a) shrinks the always-on budget, (b) ends routing slips, (c) reuses the dev_team personas, (d) leaves **one home per fact** (absorb ⇒ delete).

## §3a DRY / one-home analysis (the seed-first analog)

Every piece of knowledge ends with **exactly one canonical home**; all other surfaces point. Absorb ⇒ delete.

| Knowledge | Today (home) | After (one home) | Deleted/trimmed |
|---|---|---|---|
| Trigger-phrase procedures | `CLAUDE.md §3` table + KB guides | **skill body** (KB stays the *depth*, skill is the *procedure*) | §3 rows → skill refs; KB guide trimmed to depth-only |
| §2 Map pattern blurbs | `CLAUDE.md §2` (paragraph each) | the KB doc's own header | §2 → one-line pointer |
| Over-long §1 rule bodies | `CLAUDE.md §1` (150–250 wd) | KB pattern (already exists) | §1 → ≤80-wd rule + pointer |
| Specialist personas | `dev_team/charters/*.md` (agno) | **DECISION NEEDED** (see §8.A) | resolve N=2 persona dup |
| Already-codified feedback memories | `MEMORY.md` + 270 files + KB + keepers | KB / keeper (the durable home) | prune the memory dup |

**Rule for this project:** no skill/agent may *restate* a KB body — it *points* to it and carries only the procedure/persona. A skill that copy-pastes KB = a new drift generator (the exact thing we're removing).

## §4 Architecture — three roles on the branching substrate

**Two agent archetypes** (maps cleanly onto Claude Code primitives + the user's constraints):

1. **Executors** (`backend-engineer`, `frontend-engineer`, generic `engineer-default`) — get a **worktree+branch off `dev`**, write code, **commit only their own branch**, never touch `dev`/`main`/`prod`/peers. Dispatched in parallel for **file-disjoint** slices. `model: sonnet` default, Opus-escalation per-dispatch. **No `Agent` tool** (execute, never orchestrate).
2. **Advisors / Reviewers** (`architect`, `security`, `compliance-reviewer`) — **read-only / propose-only consultants**. No branch (they don't write code) → no commit-ownership problem. `model: opus` (the decision seats, mirroring dev_team tiering). Invoked by the Tech Lead (a) in the design phase before dispatch, (b) to review an executor branch pre-merge, or (c) **mid-flight on behalf of an executor that surfaced a question**.

**Tech Lead = the conversational session (no agent file).** Sole git owner: branch / dispatch / hold-for-dependency / merge / push / deploy / bless. Acts as the **message bus** for cross-agent consultation.

**⚠️ Harness reality on "agents call each other mid-flight" (§8.B decision):** in Claude Code, non-orchestrator subagents do NOT get the `Agent` tool (engineer-default deliberately omits it — recursion/cost/collision). So true autonomous peer-to-peer calls are NOT native. Two honest options: **(B1)** Tech-Lead-mediated consult (executor surfaces question → TL dispatches advisor → relays) — clean, cheap, matches the existing dispatch model; **(B2)** grant advisors the `Agent` tool for limited peer-calling — closer to the user's words but reintroduces nested-context cost + the orchestration-stays-with-orchestrator tension; **(B3)** true self-organizing cross-talk = the **agno `collaborate`-mode sub-teams**, which already exist — keep that lane for single hard problems needing simultaneous lenses, use Claude-Code dispatch for parallel disjoint execution. **Recommendation: B1 + keep B3 (agno) for collaboration.**

## §5 Skills to build (`.claude/skills/<name>/SKILL.md`)

Each = thin **workflow** (the "automated workflow" ask): description (the trigger, lifted from §3) + body (the procedure + which MCP tools to call in sequence) + pointer to KB depth. Candidates (final set gated on §8):

| Skill | Triggers (from §3) | Wraps |
|---|---|---|
| `noc-contextualize` | "contextualize" | the CONTEXTUALIZE.md ramp |
| `noc-new-product` | "create/scaffold a product" | `scaffold_product` + new-product.md |
| `noc-absorb-product` | "absorb the X workspace" | 10-gate absorb procedure |
| `noc-ship` | "ship to main / bless / promote / deploy" | `release` → `deploy_pull`/`deploy_image` |
| `noc-branch-dispatch` | "branch + dispatch / run in parallel" | 10-step dispatch runbook + `dispatch_preflight` |
| `noc-self-branch` | "self-branch / branch yourself" | `task_branch` lifecycle |
| `noc-wiring-audit` | "wire / all-zeros / wiring audit" | `scan_wiring` 7-step |
| `noc-container-debug` | "container won't go healthy / rebuild" | containerization-operations §1 chain + flowchart |
| `noc-hygiene` | "what cleanup is urgent?" | `hound.scan` / `mole` / keeper sweep |
| (`codify` exists) | — | — |

## §6 Agents to build (`.claude/agents/<name>.md`)

Adapt from `dev_team/charters/*.md` (the persona text already exists + is three-way-synced).

| Agent | Archetype | Model | Tools (least-privilege) | Charter source |
|---|---|---|---|---|
| `architect` | Advisor | opus | Read, Grep, Glob, `mcp__noctusai__*` (read-only: outline/refs/scan/graph), **no Write/Edit** | `solution_architect.md` |
| `security` | Advisor | opus | Read, Grep, Glob, `mcp__noctusai__*` (keeper/scan), WebSearch (CVE) | `security_engineer.md` |
| `compliance-reviewer` | Advisor | opus | Read, Grep, Glob, `mcp__noctusai__*` (validate/scan/file_proposal) | `code_reviewer.md` |
| `backend-engineer` | Executor | sonnet | Bash, Read, Edit, Write, Grep, Glob, `mcp__noctusai__*` | `backend_engineer.md` |
| `frontend-engineer` | Executor | sonnet | Bash, Read, Edit, Write, Grep, Glob, `mcp__noctusai__*` | `frontend_engineer.md` |
| `engineer-default` | Executor | sonnet | (exists — keep) | — |
| `orchestrator-operator` | Operator | (exists — keep) | — | — |

Each agent body = mission + the **standard workflow it runs** + KB pointers (NOT copied KB) + the branching/commit-ownership contract (executors) or read-only contract (advisors).

## §7 Phases

- **P0 — plan approval** (this doc). ⏳
- **P1 — skills** (§5). Re-home from §3/§2 + KB; DELETE absorbed source.
- **P2 — agents** (§6). Adapt charters; resolve §8.A persona one-home.
- **P3 — CLAUDE.md trim** (§1 bodies → pointer, §2 → one-line, §3 → skill refs). Lossless-doc-refactor gates.
- **P4 — memory prune** (drop KB/keeper-duplicated feedback entries).
- **P5 — dogfood-validate** (§10) BEFORE any commit.
- **P6 — single commit** on explicit user go.

## §8 Open decisions (need user input)

- **A. Persona one-home (DRY).** dev_team charters vs `.claude/agents` = N=2 persona dup across **two runtimes**. Options: (A1) `.claude/agents` are thin = mission + "full charter: `dev_team/.../X.md`" pointer (one home, but charter is agno-flavored); (A2) extract a **shared persona core** both consume (most DRY, most work); (A3) accept-with-rationale: two homes, two runtimes, shared §1-equivalent (`shared.md` ≈ CLAUDE.md §1). **Lean: A3 short-term, A2 if it recurs.**
- **B. Mid-flight consult mechanism.** B1 (TL-mediated) / B2 (advisors get `Agent`) / B3 (agno collaborate). **Lean: B1 + B3.**
- **C. Skill set scope.** Build all of §5 now, or pilot 2–3 (`noc-self-branch` + `noc-ship` + `noc-wiring-audit`) to prove the before/after token shape first?
- **D. Trim aggressiveness.** How hard to cut CLAUDE.md §1 — pointer-only (aggressive) vs keep one-clause-why (moderate)?

## §9 Validation gate (P5, before commit — user's explicit "validate before committing")

1. Skills are discoverable (appear in skill list) + trigger on their phrases.
2. Agents dispatch (a throwaway dry-run dispatch of `architect` advisor + one executor on a no-op slice in a scratch worktree).
3. Always-on budget actually shrank — re-measure `CLAUDE.md` wc + `MEMORY.md` size.
4. Nothing broke: `cli.py --verify-kb-sync` green (no dangling pointers after the trim), `kb_sync` counts refresh.
5. No DRY regression: every absorbed source confirmed DELETED (grep proves the old text is gone, the pointer resolves).

## §10 Single-commit plan (user mandate)

All work is **additive `.claude/` files + subtractive trims** to CLAUDE.md/KB/MEMORY — file-disjoint from both live peers. One squashed commit on `feat/harness-agents-skills`; Tech-Lead integrates to `dev` only on explicit user go (worktree-explicit FF-push per §5b cross-tree-hazard, NOT MCP integrate while peers live). Tradeoff accepted: easy `git revert`, harder per-file audit.

## §11 Risks / tradeoffs

- **Fragmentation** if absorb⇒delete isn't enforced → §3a map + P5.5 grep gate is the antibody.
- **Skill-description quality** — the model must pick the right skill; §3 trigger phrases are good raw material.
- **Keep-list** — CLAUDE.md says "Skills keep-list: update-config/loop/schedule/security-review only" → this project EXPANDS it (a methodology decision, recorded here).
- **agno charters drift** if A3 chosen → note the two-home pair in accept-with-rationale.
- **Single commit** ⊥ the platform's commit-per-phase norm → explicitly user-overridden for reversibility.
