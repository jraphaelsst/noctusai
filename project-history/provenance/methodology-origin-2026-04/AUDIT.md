# Methodology Consolidation — End-to-End Audit

> **Status.** Read-only audit. No file in `noctus-starter/`, no file in `dev-team.md`, and no file outside this one has been modified. This document captures findings + a proposed end-state + a phased implementation path. After your review, the next step is per-file proposals (option C from our earlier exchange).
>
> **Scope of the audit.** Every `.md` and `.sh` file in `noctus-starter/` (~4,400 lines) plus `dev-team.md`. Read end-to-end.
>
> **Decisions already locked** (from your reply):
>
> 1. The Agno dev-team **replaces** the single-assistant + keeper pair. The keeper's deterministic detectors survive as **a tool the Security agent calls**, not as an independent CLI.
> 2. The methodology's new home is `automations/`. `noctus-starter/` will be deleted (its contents absorbed). `dev-team.md` becomes a reference doc inside the KB.
> 3. **Stack-agnostic docs + one populated reference stack in `seed/`.** Recommended stack: FastAPI + Supabase + React + Vite + TanStack Query + Zustand + Tailwind — confirm before Phase 5. -> *human answer: confirmed*
> 4. Memory: hybrid — shared **team/project memory** for project state; **per-agent craft memory** for role-specific conventions. The team must always follow `CLAUDE.md` + KB; this is implemented as a `read_kb` tool plus terse charters in each agent's system prompt. -> *human answer: yes, but i want this kb read to be specific and localized, so agents don't read and get poluted with content it doesnt need* 
> 5. Refine BOTH `noctus-starter` AND `dev-team.md`.
> 6. Audit first (this document), then per-file proposals.
>
> **`dev-team.md` v0.2 answers** (from your edits in §5):
>
> - Team Leader = dedicated agent.
> - Add `incident_response_team` sub-team.
> - Per-project context injection = scope by project.
> - Memory = shared (refined to *hybrid* per #4 above).

---

## §0 Executive summary

`noctus-starter` is a strong methodology layer with three structural weaknesses for what you want to build:

- **It assumes one AI assistant.** Every behavioral rule is written for a singular "the assistant." With 11 Agno agents + 3 sub-teams, those rules need to be redistributed: behavioral charter into shared agent prompts, role-specific responsibilities into specialist prompts, orchestration responsibilities into the Leader.
- **It assumes the keeper is a separate observation-only tool.** With option (A) Replace, the keeper's deterministic detectors are a tool the Security agent calls; the LLM-authored review work goes to Code Reviewer + Security agents collaborating.
- **It is methodology-only.** `seed/` is empty stubs. Per your (C) decision, the reference stack should be filled — that's where the methodology becomes legible.

`dev-team.md` is a clean spec but **operates in a vacuum from the methodology**. It doesn't say how the team consults `CLAUDE.md` + KB, doesn't list concrete tools per agent, doesn't specify memory architecture, doesn't specify the interface to Claude Code, and doesn't yet have the `incident_response_team` you approved for v0.2.

The merge is straightforward: `dev-team.md` becomes the canonical role spec inside the KB; `noctus-starter` rules become the team's shared charter; the agno code under `automations/dev-team/` is the runtime; Claude Code is the user-facing CLI that dispatches to the team.

The cost shape is the one substantive trade you should price in: the team is more expensive per task than Claude Code alone, with `coordinate` mode O(subtasks) and `collaborate` mode O(members). The architecture in `dev-team.md §1.1` is correctly cost-aware. Lean charters + on-demand KB reads + Anthropic prompt caching keep it manageable; model tiering (Opus on Leader/Architect/Security/PM/Code-Reviewer; Sonnet on the rest) is the single biggest cost lever. -> *human note: great. But please create this model structure dynamic. This means that it's okay to orchestrate opus and sonnet for now, but in the future I'm gonna test codex and gemini also for evaluations and comparisons, so this models swap must be easy*

The rest of this document is the detail.

---

## §1 Audit of `noctus-starter/`

### §1.1 What's strong (keep)

- **The CLAUDE.md / KB outer-map / inner-map split.** This is the single best architectural decision in the repo. It's also the right pattern for the agno team (terse agent charters + on-demand KB reads).
- **Seed-as-skeleton metaphor.** `01-PHILOSOPHY.md` and `03-SEED-ARCHITECTURE.md` are internally consistent and load-bearing. The "named seam vs. structural fork" framing is genuinely good engineering culture.
- **Triage-at-decision-time** (`01-PHILOSOPHY.md § Triage at decision time`). Three explicit landings (formalize / refactor / accept-with-rationale) with recurrence flipping prior accepts is mature thinking — many teams settle for "approved exception" politics or pure rigor; this avoids both.
- **Recurrence rule with hard thresholds (N=2 / N=3+).** Concrete, enforceable, anti-drift. Pairs cleanly with the language-time replication-to-seed-symmetry trigger.
- **The five-layer testing discipline + no-self-monkeypatching three patterns** (`PATTERNS/testing.md`). The DI / boundary-mock / seed-real-data taxonomy with a litmus test is the strongest piece of writing in the repo.
- **Apply-inline-then-delete + end-of-work-summary protocol** (`PATTERNS/proposals-and-improvements.md § 4b § 4c`). Strong anti-drift discipline; specific enough to be enforceable.
- **§3a seed-first checklist** (`GUIDES/seed-first-design.md`). REQUIRED in every PROJECT.md is the right level of mandatory.
- **Phase 0 audits + expand-loudly rule** (`PATTERNS/project-execution.md § 2.5`). The 5-30 min vs. 2-8 hr asymmetry argument is correct and well-stated.
- **Three-way sync** (KB / `CLAUDE.md` / memory). Clear ordering rule (KB-first), automated check (`verify-kb-sync.sh`), and explicit non-automated discipline (memory parity).
- **Pre-commit hook with extension points** (`scripts/pre-commit`). Currently slim (KB sync only) but the extension points are wired and commented — easy to grow.
- **Three-location project rule** (`projects/<slug>/`, `products/<product>/projects/<slug>/`, `core/projects/<slug>/`). Solves the tension between "centralize for discoverability" and "co-locate for cohesion" cleanly.

### §1.2 What's redundant (consolidate)

The same content appears 3-4 times across files. Each repetition was added with a reason (different audience, different depth) but the result is drift risk + token cost.

| Concept | Lives in | Drift risk |
|---|---|---|
| The recurrence rule (N=2 / N=3+) | `01-PHILOSOPHY.md`, `CLAUDE.md §2`, `PATTERNS/project-execution.md § 2.7`, `PATTERNS/shared-library-conventions.md` | The thresholds match across all four; the prose around them does NOT match perfectly. One file says "TRIAGE TIME"; another says "triage decision required". Easy to drift. |
| No silent errors | `01-PHILOSOPHY.md § No silent errors`, `CLAUDE.md §2`, `PATTERNS/logging.md § No # silent-ok`, `PATTERNS/testing.md § Auth boundary` | Three different lenses (runtime, agent execution, communication) each repeat the rule. Fine if cross-referenced; currently re-stated. |
| Three-way sync | `01-PHILOSOPHY.md § Three-way sync`, `CLAUDE.md §2`, `PATTERNS/proposals-and-improvements.md § 6` | Ordering rule appears in two places with slightly different framing. |
| Apply-inline-then-delete | `CLAUDE.md §2`, `PATTERNS/proposals-and-improvements.md § 4b`, `PATTERNS/project-execution.md § 0` | Most consistent of the four; still re-stated three times. |
| End-of-work summary | `CLAUDE.md §1` AND `CLAUDE.md §2` AND `PATTERNS/proposals-and-improvements.md § 4c` | The shape and mandate are stated in three places. |
| Replication-to-seed symmetry | `CLAUDE.md §2`, `PATTERNS/project-execution.md § 3` | Both versions are long; the prose is ~70% identical. |

**Proposed consolidation pattern.** Each rule has **one canonical home** (the deepest KB file). Every other appearance becomes a **one-line pointer + the operative threshold/litmus**, never the full prose. The pre-commit hook already enforces pointer integrity.

### §1.3 What's missing or thin (enrich)

- **`02-LANDSCAPE.md`** is a template with placeholder rows. Per (C) it should be filled with the reference stack's example shape (a "Hello product" or two skeleton products).
- **`05-INFRASTRUCTURE.md`** is also a template. Per (C) it should describe the reference stack's deploy targets concretely (Hostinger VPS + Docker + Traefik, n8n, Supabase, etc., based on what `dev-team.md § 2.7` already implies you use).
- **`06-AGENTS.md`** describes the keeper-as-CLI shape. With option (A), it needs to be rewritten end-to-end to describe the agno team **and** the keeper-as-tool. About 50% of the prose carries over (the detector inventory, the regression-test-the-detector rule); the orchestration framing is replaced.
- **`KNOWLEDGE-BASE/INSTRUCTIONS/`** has only `00-MASTER.md` and is explicitly a stub. With agents being first-class, this folder should grow: `01-AGENTS.md` (Agno team architecture), `02-TOOLS.md` (tool catalog), `03-MEMORY.md` (memory architecture), `04-COSTS.md` (cost guide).
- **`seed/`** is empty stubs. Per (C), this is where the reference stack lives.
- **No agno integration anywhere.** No `dev-team/` folder, no python package, no entry point. Currently the methodology talks about agents abstractly; under (A) it must talk about *this specific* team.
- **`MEMORY.md` for the agno team** doesn't exist. Claude Code has its own auto-memory system (`/Users/rapha/.claude/projects/.../memory/`). The agno team needs a parallel memory store; the architecture for how they share or stay isolated is undefined.
- **No "when to call the team vs. Claude Code direct" guidance.** Trivial tasks (typo fix, one-line correction) shouldn't pay the team's overhead. Threshold needs to be specified.
- **`mcp/` is a stub.** Even within the existing methodology, no detector is implemented. With (A), the detectors need to be a Python package the Security agent imports — at least a minimal set.
- **Migration path for an existing repo** is mentioned in `README.md § To consolidate an existing project` but never elaborated. With this audit being exactly that path, the doc could be promoted into a real `GUIDES/migration.md`.

### §1.4 What's inconsistent (fix)

- **Voice.** Most docs are crisp; a few veer into evangelism (*"This workflow is not optional."*, *"non-negotiable."*, italic emphasis stacked). Once the agno team is the audience, terser is cheaper. Same content, fewer tokens, same enforceability — the rules don't get weaker by being calmer.
- **`CLAUDE.md` weight.** Currently ~22kb / 230+ lines. The doc itself recommends "kept lean on purpose" but is right at the line. Pulling repeated rule prose into KB-only homes (per §1.2) drops it ~30%.
- **References to specific tools.** `Supabase MCP apply_migration` appears in a few places (`PATTERNS/database.md`, `01-PHILOSOPHY.md`); it's appropriate when Supabase is the chosen DB but reads as stack-specific in a stack-agnostic doc. Resolution: keep the rule generic ("via the platform's migration tool"), put the Supabase-specific recipe in the reference-stack docs.
- **Some pointers reach forward.** *"When the keeper exists"* / *"When `templates/product-seed/` is populated"* / *"When products exist"* — these are honest but read as half-shipped. Once the reference stack lands and the agno team exists, most of these resolve.
- **`core/README.md` describes a folder shape that conflicts with `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`.** The `core/` README says core lives at root; the seed-architecture doc shows it as a peer to other products. The README explicitly notes the alternative ("In the NoctusAI codebase, core lives at `products/core/`") — which is fine but the structure-elsewhere assumes `core/` at root. Pick one shape for the consolidated repo and align all references.
- **`AGENT-CONTEXT.md` and `KNOWLEDGE-BASE/INDEX.md` partially overlap with `CLAUDE.md §3 The Map`.** Three pointers-into-KB tables, one in each. They're consistent today but easy to drift. Resolution: `AGENT-CONTEXT.md` becomes the prose onboarding (no table); `INDEX.md` becomes the catalog (the by-topic table); `CLAUDE.md §3` becomes the every-turn pointer (a strict subset of `INDEX.md`).
- **`templates/product-seed/`** is referenced in 3 places (`01-PHILOSOPHY.md`, `03-SEED-ARCHITECTURE.md`, `04-SHARED-LIBRARY.md`, `GUIDES/new-product.md`) but the folder doesn't exist. Currently a forward-reference; once the reference stack ships, populate it.

### §1.5 What's strong but underspecified for multi-agent execution

These rules are good; they need **execution-time clarification** for a team of agents (not a single assistant) to apply them deterministically.

- **End-of-work summary.** "Every reply concluding non-trivial work" — *which agent writes it?* Resolution: the Leader, in synthesis. Other agents return structured outputs to the Leader, which assembles the summary.
- **Apply-inline-then-delete.** *Which agent applies the proposal?* Resolution: the agent who built the phase (Backend / Frontend / DevOps), with Code Reviewer signing off. Tech Writer logs §11.
- **Phase 0 audit.** *Who runs it?* Resolution: Leader delegates to Architect; Architect uses `read_files` + `shell` tools.
- **Replication-to-seed-symmetry trigger (language time).** *Every agent that writes code needs to internalize this.* Resolution: it goes in the shared charter (loaded by every code-writing agent).
- **Three-way sync.** *Who keeps memory updated?* Resolution: Tech Writer for KB depth + `CLAUDE.md` pointer; the Leader writes/updates team memory.

---

## §2 Audit of `dev-team.md`

### §2.1 What's strong (keep)

- **Hybrid architecture (`coordinate` backbone + `collaborate` sub-teams).** The cost-vs-quality trade is correctly framed in §1.1 and §4.2.
- **11 roles with clear inputs/outputs/handoffs.** The decomposition tracks a real org and the input/output lines make orchestration tractable.
- **QA separated from developers.** The "Critical rule: QA must be a separate agent" framing in §2.9 prevents self-tested code, the most common failure mode in single-agent setups.
- **Sub-team membership stated per role.** Knowing who's in `design_review_team` vs. `code_review_team` upfront makes the wiring code in §4.1 self-evident.
- **Cost & latency considerations called out** (§4.2, §4.3). Most multi-agent specs ignore this; you didn't. Model tiering recommendation is the right tool.
- **Explicit "same agent instance reused across teams"** (§4.1 Note). Important detail — it preserves voice + memory continuity. Agno supports it cleanly.
- **v0.2 answers are decisive** (§5). Each unblocks an implementation choice.

### §2.2 What's missing (fill)

- **No reference to `CLAUDE.md` + KB.** Under (A), every agent in this team operates inside the methodology. The spec doesn't say *how*. Resolution: shared charter section + `read_kb` tool.
- **No tool catalog per agent.** §4.4 lists impressionistic tools ("file read/write, code execution"). For implementation we need a concrete list with names + scopes.
- **No memory architecture.** v0.2 answer "share" needs to be refined to (C) hybrid: shared **project memory** + per-agent **craft memory**. The shape, persistence, schema, TTL are all undefined.
- **No interface to Claude Code.** Spec is silent on how a user invokes the team. Resolution: a CLI entrypoint Claude Code calls (the lean route) OR an MCP server (richer integration but heavier).
- **No `incident_response_team` design** even though v0.2 says yes.
- **No keeper-as-tool spec.** The deterministic detectors from `06-AGENTS.md` belong inside the Security agent's tool surface; how is undefined.
- **No "when to call the team" threshold.** Some tasks aren't worth the team's overhead.
- **No Phase 0 / Phase 1 / phase-by-phase cadence.** The default workflow §1.3 jumps from intake → scoping → design → implementation. The methodology requires Phase 0 audits, live ticking, and pause-after-each-phase. The team has to honor those.
- **No "stop and ask the user" triggers.** When does the Leader pause execution? `noctus-starter` has clear rules (`PATTERNS/project-execution.md § 4` cadence + § 2.5 hard-stop classes). The team needs to inherit them.
- **No language-trigger discipline.** The replication-to-seed-symmetry rule fires at language time, in any agent's response. Every code-writing agent needs to internalize it.
- **No data-protection lens.** `PATTERNS/data-protection.md § The five questions` is mandatory in every PROJECT.md §3. Which agent runs the five questions? PM + Security split is the right answer; the spec doesn't say.

### §2.3 What's overlapping (clarify boundaries)

- **UX Designer + Frontend Engineer.** Both touch user-facing artifacts. Boundary: UX produces flows / wireframes / accessibility checklist (the spec); Frontend implements them in code. Stating this explicitly avoids a turf battle in execution.
- **Architect + Backend Engineer.** Both touch architecture. Boundary: Architect produces ADRs + contracts + schema definitions; Backend implements per the contract. Stating it explicitly stops Backend from re-deciding.
- **Code Reviewer + Security.** Both review. Boundary: Code Reviewer covers maintainability + idiomatic + standards; Security covers OWASP / auth bypass / secrets / CVEs / threat modeling. They sit together in `code_review_team` for parallel review, not redundant review.
- **PM + Architect.** PM owns *what* + *why*; Architect owns *how*. Today's spec is correct; an explicit "PM does NOT specify implementation; Architect does NOT change requirements" line forecloses scope drift.

### §2.4 Concerns to flag

- **DevOps Engineer §2.7 mentions specific tools** (Hostinger VPS, n8n, Traefik). This is project-leak. It belongs in `02-LANDSCAPE.md` / `05-INFRASTRUCTURE.md` (your platform's chosen infra) — not in the role spec, which should be portable across projects.
- **Team Leader's "detect when team is stuck"** is vague. Concrete triggers needed: agent timeout, repeated rejection from sub-team, contradictory outputs across two agents on the same question. Spec these or the Leader will paper over.
- **Per-project context injection** (v0.2 = "scope by project") needs a delivery mechanism. Resolution: each project's `PROJECT.md` + the relevant product's `MASTER-PROMPT.md` get loaded into the team's session memory at task start. Per-agent craft memory layers on top. Implementation in `tools/memory.py`.

---

## §3 Tensions to reconcile

These are the seven places where `noctus-starter` and `dev-team.md` collide once option (A) is locked. Each has a proposed resolution.

### §3.1 "Single assistant" framing vs. multi-agent team

`CLAUDE.md §1` opens with *"The AI assistant in this repo is a technical specialist..."*. With (A), the assistant **is** the team — but the user sees one face (the Leader's synthesis).

**Resolution.** Rewrite `CLAUDE.md §1` to *"The AI capability in this repo is a multi-agent team led by a coordinator. The Leader presents one face to the user. The behavioral rules in §2 apply to every agent."* Roles + behaviors described in `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` and `07-DEV-TEAM.md`.

### §3.2 "Keeper NEVER edits code" vs. "agents that DO edit code"

`06-AGENTS.md` is firm. The agno team writes code.

**Resolution.** Two distinct concepts, two distinct names. Keep "keeper" for the deterministic detector toolkit (still observation-only, still no LLM, still no code edits). Use "dev team" / "the team" for the agno multi-agent system that writes code, files proposals, runs Phase 0 audits, etc. The Security agent **uses** the keeper as a tool; Code Reviewer + QA agents **use** the keeper as evidence. Rewrite `06-AGENTS.md` to make this explicit.

### §3.3 End-of-work summary mandate vs. multiple agents

`PATTERNS/proposals-and-improvements.md § 4c` mandates the summary on every reply concluding non-trivial work. With multiple agents, who writes it?

**Resolution.** The Leader writes it as the final synthesis pass. Specialists return structured outputs (applied items, deferred items, verification results) to the Leader; Leader assembles the list-shaped summary in the user-facing reply. Specialists don't each write their own summary — that would be N parallel summaries, defeating the signal.

### §3.4 Three-way sync vs. four memory layers

Currently: KB / `CLAUDE.md` / persistent memory. With Agno added: KB / `CLAUDE.md` / Claude Code memory / Agno memory.

**Resolution.** Stay three-way by collapsing the persistent-memory layer to **one logical store** with two physical backings. Claude Code's memory + Agno's memory are sibling consumers of the *same* on-disk store under `automations/dev-team/memory/`. The Leader writes; both can read. Three-way sync rule remains "KB / CLAUDE.md / memory move together," with "memory" defined as that single store.

### §3.5 Replication-to-seed-symmetry trigger fires at LANGUAGE time

The rule fires the moment certain phrasings appear *in the agent's own response*. With one assistant, it's straightforward. With 11 agents, every code-writing agent needs the trigger internalized.

**Resolution.** The trigger is part of the **shared agent charter** loaded by Backend / Frontend / DevOps / Architect / Code Reviewer. Each of those agents' system prompts ends with a "language-time triggers" block listing the slip phrasings + the STOP-and-challenge protocol. Code Reviewer additionally checks for the trigger in other agents' outputs during sub-team review.

### §3.6 Phase 0 audit vs. team workflow

`PATTERNS/project-execution.md § 2.5` mandates Phase 0 audits before code lands. `dev-team.md §1.3 Default Workflow` jumps from scoping to design to implementation without an audit step.

**Resolution.** Add Phase 0 to `07-DEV-TEAM.md` workflow: Leader → Architect runs Phase 0 (read files, run commands, surface findings). Findings either confirm §6 or trigger expand-loudly. Only then does design / implementation start.

### §3.7 Apply-inline-then-delete + phase-end protocol vs. team execution

The protocol assumes one agent owns the phase end-to-end. With the team, multiple agents touch the phase.

**Resolution.** Phase ownership map:
- **During phase.** Backend / Frontend / DevOps capture improvement bullets in their respective domains, all writing to the same `PROJECT.md`'s `**Improvements:**` block (the file is the shared state).
- **End of phase.** Code Reviewer (lead of `code_review_team`) authors the bundled proposal from `PROPOSAL-TEMPLATE.md`. Security and QA collaborate. Backend / Frontend / DevOps apply inline. Tech Writer logs §11. Leader deletes the proposal file and writes the end-of-work summary.

---

## §4 Proposed end-state structure

```
automations/
├── CLAUDE.md                          ← rewritten: governs the whole repo; describes the team's behavioral charter
├── README.md                          ← rewritten: methodology + agno team + how to invoke
├── KNOWLEDGE-BASE/                    ← absorbed from noctus-starter, refined
│   ├── INDEX.md
│   ├── AGENT-CONTEXT.md               ← prose onboarding (no table)
│   ├── CONTEXT/
│   │   ├── 01-PHILOSOPHY.md           ← canonical home for behavioral rules; deduplicated
│   │   ├── 02-LANDSCAPE.md            ← filled with reference stack
│   │   ├── 03-SEED-ARCHITECTURE.md
│   │   ├── 04-SHARED-LIBRARY.md
│   │   ├── 05-INFRASTRUCTURE.md       ← filled with reference stack
│   │   ├── 06-AGENTS.md               ← rewritten: dev team architecture + keeper-as-tool
│   │   ├── 07-DEV-TEAM.md             ← NEW (absorbs current dev-team.md, expanded with v0.2 + tensions resolved)
│   │   ├── PATTERNS/                  ← unchanged structure; deduplicated (one canonical home per rule)
│   │   └── GUIDES/
│   │       ├── setup.md
│   │       ├── new-product.md
│   │       ├── seed-first-design.md
│   │       └── invoke-the-team.md     ← NEW: when to call the team vs. Claude Code direct
│   └── INSTRUCTIONS/
│       ├── 00-MASTER.md
│       ├── 01-AGENTS.md               ← NEW: agno-specific design notes
│       ├── 02-TOOLS.md                ← NEW: tool catalog
│       ├── 03-MEMORY.md               ← NEW: memory architecture
│       └── 04-COSTS.md                ← NEW: cost guide + tiering recommendation
├── seed/                              ← populated reference stack (FastAPI + Supabase + React + Vite + ...)
│   ├── backend/
│   │   ├── lib/                       ← auth, roles, invitations, email, llm/, testing/
│   │   └── framework/                 ← create_product_app(...), settings, deps, standard routers
│   └── frontend/
│       ├── lib/                       ← api, auth, hooks, design-system
│       └── framework/                 ← createProductApp, createProductLayout, createViteConfig
├── products/                          ← .gitkeep until first product
├── projects/                          ← .gitkeep until first cross-product project
├── core/                              ← .gitkeep OR removed if no control-plane planned (your call)
├── templates/
│   ├── PROJECT-TEMPLATE.md
│   └── PROPOSAL-TEMPLATE.md
├── scripts/
│   ├── install-hooks.sh
│   ├── pre-commit
│   └── verify-kb-sync.sh
├── mcp/
│   └── keeper/                        ← deterministic detectors (Python package the Security agent imports)
└── dev-team/                          ← NEW: agno python implementation
    ├── pyproject.toml
    ├── README.md
    ├── .env.example
    ├── src/
    │   └── dev_team/
    │       ├── __init__.py
    │       ├── cli.py                 ← entrypoint Claude Code calls
    │       ├── agents/
    │       │   ├── leader.py
    │       │   ├── pm.py
    │       │   ├── ux.py
    │       │   ├── architect.py
    │       │   ├── backend.py
    │       │   ├── frontend.py
    │       │   ├── devops.py
    │       │   ├── security.py        ← uses mcp/keeper as tool
    │       │   ├── qa.py
    │       │   ├── code_reviewer.py
    │       │   └── tech_writer.py
    │       ├── teams/
    │       │   ├── dev_team.py
    │       │   ├── design_review_team.py
    │       │   ├── code_review_team.py
    │       │   └── incident_response_team.py
    │       ├── tools/
    │       │   ├── kb.py              ← read_kb(path), search_kb(query)
    │       │   ├── filesystem.py      ← scoped read/write/edit
    │       │   ├── shell.py           ← bounded shell (build/test/lint)
    │       │   ├── keeper.py          ← wraps mcp/keeper deterministic detectors
    │       │   ├── recurrence.py      ← cross-product / service-line scans
    │       │   ├── proposals.py       ← file_proposal, list, accept/reject
    │       │   └── memory.py          ← shared project memory + per-agent craft memory
    │       ├── memory/
    │       │   ├── project/           ← per-project state
    │       │   └── agents/            ← per-agent craft memory
    │       ├── config/
    │       │   ├── models.py          ← model tier mapping per role
    │       │   └── settings.py
    │       └── prompts/
    │           ├── shared/             ← terse charter loaded by every agent
    │           └── agents/             ← per-agent role prompts
    └── tests/
```

Compared to the current layout the deltas are:

- `noctus-starter/` deleted; everything inside is hoisted to the repo root.
- `dev-team.md` (root) deleted; its content is absorbed into `KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md` + the agno code.
- `mcp/` keeps its place but `mcp/keeper/` is a real Python package (not a stub).
- `dev-team/` is the new home for the agno team.
- `KNOWLEDGE-BASE/INSTRUCTIONS/` grows from 1 file to 5.
- `KNOWLEDGE-BASE/CONTEXT/GUIDES/` adds `invoke-the-team.md`.

---

## §5 Implementation plan for the agno team

### §5.1 Charter architecture (how agents follow `CLAUDE.md` + KB)

Two layers per agent's system prompt:

**Layer 1 — shared charter (~1.5K tokens, identical for every agent).** Pulled from `CLAUDE.md §2` (behavioral rules, terse form). Includes:
- The #1 rule: seed-first.
- No quick fixes / no workarounds / no monkey-patching.
- No silent errors (the three shapes: runtime / agent / communication).
- No incomplete commits.
- The replication-to-seed-symmetry language-time trigger.
- Three-way sync (KB / `CLAUDE.md` / memory move together).
- Apply-inline-then-delete + end-of-work summary references (mandate stated; details on demand).
- A pointer to `read_kb(path)` for depth.

**Layer 2 — role prompt (~1-2K tokens, one per agent).** Mission + responsibilities + outputs + handoffs (from `dev-team.md §2.x`) + role-specific KB reading list (which KB files are mandatory pre-reads for this role) + role-specific behavioral details.

Total per agent: ~3K tokens of system prompt. Cached. With 11 agents, full-team activation is ~33K tokens of cached input — substantial but not punitive at cache-read prices (~10% of base input).

### §5.2 Tool catalog per agent

| Agent | Tools |
|---|---|
| Team Leader | `read_kb`, `read_memory`, `write_memory`, `delegate(specialist, task)`, `invoke_subteam(team_name, task)` |
| Product Manager | `read_kb`, `read_memory`, `write_memory`, `web_search` (competitive research), `read_files` (existing PROJECT.md / MASTER-PROMPT.md) |
| UX Designer | `read_kb`, `read_memory`, `write_memory`, `web_search` (design references), `read_files` |
| Solution Architect | `read_kb`, `read_memory`, `write_memory`, `read_files`, `recurrence_scan` (helpers, service-lines, blocks), `keeper_validate` (read-only) |
| Backend Engineer | `read_kb`, `read_memory`, `write_memory`, `read_files`, `write_files`, `edit_files`, `shell` (bounded: pytest, ruff, mypy, build), `recurrence_scan` |
| Frontend Engineer | `read_kb`, `read_memory`, `write_memory`, `read_files`, `write_files`, `edit_files`, `shell` (bounded: vitest, build, lint), `recurrence_scan` |
| DevOps Engineer | `read_kb`, `read_memory`, `write_memory`, `read_files`, `write_files`, `edit_files`, `shell` (bounded: docker, compose, terraform plan) |
| Security Engineer | `read_kb`, `read_memory`, `write_memory`, `read_files`, `keeper_validate` + `keeper_review`, `web_search` (CVE lookups), `recurrence_scan` |
| QA Engineer | `read_kb`, `read_memory`, `write_memory`, `read_files`, `write_files`, `edit_files`, `shell` (bounded: test runners), `recurrence_scan` |
| Code Reviewer | `read_kb`, `read_memory`, `write_memory`, `read_files`, `recurrence_scan`, `keeper_validate` (read-only) |
| Technical Writer | `read_kb`, `read_memory`, `write_memory`, `read_files`, `write_files`, `edit_files` (scoped to `*.md` + `KNOWLEDGE-BASE/`) |

Notes:
- `write_memory` is gated: PM/UX/Architect write **decisions**; engineers write **implementation notes**; Code Reviewer writes **review patterns**; QA writes **test patterns**. Schema enforced by `tools/memory.py`.
- `shell` is bounded: an allowlist of commands per agent (pytest for QA/Backend/Frontend; docker for DevOps; etc.). No unrestricted shell.
- `keeper_validate` and `keeper_review` are wrappers around `mcp/keeper/` — the deterministic detectors. Read-only outputs.
- `web_search` is rate-limited and scoped (not all agents need it — the table reflects who genuinely benefits).

### §5.3 Memory architecture (hybrid)

**Shared project memory.** Lives at `dev-team/memory/project/<project-slug>/`. Files:
- `state.json` — current phase, current §6 task, last verification result.
- `decisions.md` — append-only log of architect decisions, PM acceptance criteria, UX patterns chosen.
- `change-log.md` — mirror of `PROJECT.md §11` for cheap reads.

Every agent reads it at task start; Leader writes it; Architect / PM / UX append decisions through `write_memory`.

**Per-agent craft memory.** Lives at `dev-team/memory/agents/<agent-name>/`. Files:
- `<agent>.md` — terse craft notes the agent has accumulated. Architect's preferred ADR shapes; QA's go-to test-fixture patterns; Code Reviewer's recurring review comments; etc.

Agents read only their own; each appends through `write_memory(scope="self", ...)`.

**Three-way sync rule** extends to: KB / `CLAUDE.md` / `dev-team/memory/`. The pre-commit hook stays the same (KB ↔ `CLAUDE.md`); memory parity is the Leader's discipline at end-of-work.

### §5.4 Interface to Claude Code

Two options, ordered by preference:

**Option A (recommended) — CLI entrypoint.** `dev-team/src/dev_team/cli.py` exposes `python -m dev_team run "<task>"`. Claude Code shells out via Bash. Cheapest integration, fewest moving parts. The team's stdout is the user-facing summary; Claude Code relays it.

**Option B — MCP server.** `dev-team` exposes an MCP server with `dispatch_to_team(task)` as the primary tool. Claude Code loads it via `.mcp.json`. Heavier but allows mid-execution tool calls back into Claude Code's session.

Lean toward (A) for v1; (B) is future work.

### §5.5 When to call the team vs. Claude Code direct

A `GUIDES/invoke-the-team.md` doc establishes the threshold. Rough rules:

- **Trivial / one-shot.** Single-file edit, typo fix, format change, doc tweak, one-line bug fix. → **Claude Code direct.** Don't pay team overhead.
- **Single-domain task with clear scope.** New endpoint, new component, single test fixture, isolated refactor. → **Claude Code direct** unless cross-cutting concerns surface.
- **Multi-file, multi-domain, or unclear scope.** New feature, schema change, new product, security review, deploy change. → **Team**, starting with PM intake.
- **Architecture decision or design review.** ADR, schema review, threat model. → **Team** with `design_review_team` invoked.
- **PR review.** → **Team** with `code_review_team` invoked.
- **Production incident.** → **Team** with `incident_response_team` (once specced).

The Leader can also short-circuit: if a task arrives that's clearly trivial, it returns *"this is a one-line fix; doing it inline"* and applies + summarizes without invoking sub-teams.

### §5.6 `incident_response_team` design (resolves v0.2 #2)

**Mode.** `collaborate`.
**Members.** DevOps Engineer (lead), Security Engineer, Backend Engineer (default), Frontend Engineer (added when the incident touches the UI).
**When invoked.** Production incident, alert page, runbook execution, post-mortem authoring.
**Goal.** Triage → mitigate → root-cause → document, with a short feedback loop to the on-call human.
**Output.** Incident timeline, root-cause analysis, remediation PR(s), runbook update, post-mortem in `projects/<slug>-incident-<date>/PROJECT.md`.
**Cost note.** Collaborate mode for a 3-4 member team during an incident is fine — the question is restoration speed, not token cost.

### §5.7 Cost & latency model (concrete)

For your bookkeeping:

- **Per task overhead** when invoked through Claude Code: ~1 Claude Code turn (your existing cost) + ~1-3 Leader turns + N specialist turns + (optional) sub-team collaborate burst.
- **Coordinate-mode task** (single-domain): Leader (1 turn) + Specialist (1-3 turns). With Sonnet on the specialist + Opus on the Leader: roughly $0.03-$0.08 / task at current Anthropic pricing (verify with current rates — pricing changes).
- **Collaborate-mode burst** (sub-team review): each member contributes 1-2 turns. 3-member sub-team (`code_review_team`): ~6-12 specialist turns. With model tiering: roughly $0.10-$0.25 / review.
- **Full-team task** (intake → design → design-review → implementation → code-review): ~30-60 turns total. ~$0.50-$1.50 / feature at current pricing.
- **Prompt caching** drops cached input cost ~10x. Critical to enable. Each agent's system prompt + role prompt should hit cache after the first call.
- **Model tiering** (per `dev-team.md §4.3`): Opus on Leader / PM / Architect / Security / Code Reviewer; Sonnet on Backend / Frontend / DevOps / QA / Tech Writer / UX. Drops average task cost ~40-60%.

Net vs. Claude Code direct on the same task: **2-4x more expensive** for non-trivial work, with the trade being multi-lens review + structured project artifacts. Trivial work should NOT route to the team.

---

## §6 Remaining open questions (need your answer before implementation)

1. **Reference stack — confirm.** Recommended: FastAPI + Supabase + React + Vite + TanStack Query + Zustand + Tailwind + Pydantic v2 + ruff + mypy + pytest + vitest. Is this the stack? Substitute anything?
2. **`core/` — keep or drop.** The starter ships it as an empty placeholder for "control-plane when one exists." Keep as `.gitkeep` placeholder, or drop entirely until you actually build a control-plane?
3. **Memory backend.** SQLite (portable, zero-deps, queryable) or plain Markdown/JSON files (human-readable, git-friendly)? My lean: Markdown for `decisions.md` / `change-log.md` (human-readable) + SQLite for `state.json`-equivalent structured queries (or a single SQLite file storing both). What's your preference?
4. **Agno + provider choice.** Anthropic-only initially? Or do you want to mix in OpenAI / Google for cost optimization on Backend / Frontend / Tech Writer agents? (Agno supports it; it adds a second API key + a second bill.)
5. **Keeper detector scope for v1.** The full inventory in `06-AGENTS.md` is ~15 detectors. For an initial implementation, I'd ship a minimal set: silent errors, no-self-monkeypatch, KB-pointer-resolves, project-has-§3a, mock-schema-validation. The rest grow over time. Agree with the minimal v1 set, or want a different cut?
6. **Migration shape.** Two ways to absorb `noctus-starter/` into `automations/`:
   - **(A) `git mv` everything one-by-one** — preserves history per file but creates a noisy commit.
   - **(B) `git rm -r noctus-starter && git add` the new structure** — clean commit but loses per-file history.
   I'd do (A) for `KNOWLEDGE-BASE/`, `templates/`, `scripts/`, `mcp/`, `seed/`, `.gitignore` (history matters), and (B) for the placeholder directories (`products/`, `projects/`, `core/` — only `.gitkeep`s).
7. **Claude Code interface — A or B.** CLI entrypoint (recommended) or MCP server? Or both, with CLI first?
8. **Reference-stack seed scope for Phase 5.** Minimal viable reference stack (just app factory + auth + 1 sample router on each side) or fuller (auth + roles + invitations + notifications + design system + LLM client)? Fuller takes longer; minimal lands faster but means the methodology stays half-illustrated.
9. **`incident_response_team` membership default.** I proposed DevOps (lead) + Security + Backend (default), with Frontend added situationally. Confirm or revise.
10. **`mcp/keeper/` vs. embedded inside `dev-team/`.** Keeper as a standalone Python package under `mcp/keeper/` (importable by anything, including future non-team consumers) OR embedded as `dev-team/src/dev_team/keeper/` (one package, simpler). My lean: standalone under `mcp/keeper/` — it's reusable and the existing methodology already sites it there.

---

## §7 Recommended next steps (the per-file proposal queue)

Once you approve the audit, the next pass is option (C) — per-file proposals filed as a real project.

**Project slug.** `methodology-restructure`.
**Location.** `projects/methodology-restructure/PROJECT.md`.
**Phase 0.** Already done — this audit IS Phase 0. Findings summarized in §1-§5 above; this audit moves into the project folder as a reference artifact.
**Phases (suggested cadence — phase-by-phase per `PATTERNS/project-execution.md § 4`):**

- **Phase 1 — Hoist `noctus-starter/` to repo root.** `git mv` per §6.6. Update internal pointers (every doc that references `noctus-starter/...` becomes the relative root). Verify KB sync, install hooks, run the verifier. *Output: clean repo without `noctus-starter/`, all pointers green.*
- **Phase 2 — Refine `CLAUDE.md`.** Rewrite §1 (single assistant → team-with-Leader). Tighten §2 (deduplicate against KB; pull repeated rule prose into pointers). Update §3 The Map. Trim ~30%.
- **Phase 3 — Refine `06-AGENTS.md` + add `07-DEV-TEAM.md`.** Rewrite `06-AGENTS.md` to describe team architecture + keeper-as-tool. Move dev-team.md content into `07-DEV-TEAM.md` with v0.2 + tension resolutions integrated. Delete root-level `dev-team.md`.
- **Phase 4 — Deduplicate KB content.** Per §1.2 — recurrence rule, no-silent-errors, three-way-sync, apply-inline-then-delete, end-of-work-summary, replication-to-seed-symmetry each get one canonical home + pointers everywhere else.
- **Phase 5 — Populate `seed/` with the reference stack.** Backend skeleton (FastAPI app factory + dep factories + standard routers + auth/roles/invitations/notifications). Frontend skeleton (createProductApp + createProductLayout + createViteConfig + design-system primitives). Tests landed with implementation per the methodology. Update `02-LANDSCAPE.md` + `04-SHARED-LIBRARY.md` with concrete entries.
- **Phase 6 — Implement `mcp/keeper/`.** Minimal v1 detector set per §6.5. Each detector ships colocated with regression tests per `PATTERNS/testing.md § Regression-test-the-detector`. CLI exposed for human use. Python module exposed for the Security agent's tool import.
- **Phase 7 — Scaffold `dev-team/` Python package.** `pyproject.toml`, `cli.py`, agents/, teams/, tools/, prompts/, memory/, config/. Each agent gets its terse charter + role prompt. Tools are real implementations (not stubs). Tests with deterministic mock LLM responses for the orchestration topology.
- **Phase 8 — Wire memory architecture.** `tools/memory.py` with shared/per-agent split. Schema for `decisions.md`, `change-log.md`, `state.json`. Three-way sync extended.
- **Phase 9 — Spec + implement `incident_response_team`.**
- **Phase 10 — Update root `README.md` + `GUIDES/invoke-the-team.md`.** End-user docs for "how to use this repo" and "when to call the team vs. Claude Code direct."
- **Phase 11 — Final verification.** Full keeper run. KB sync. Test suites. End-of-work summary in §11.

Each phase ships its own bundled proposal per `PATTERNS/proposals-and-improvements.md § 4b`, applied inline + deleted in the same session.

---

## §8 What I will NOT do without explicit greenlight

Per your instruction, **nothing in `noctus-starter/` or `dev-team.md` has been altered**. This audit is the only file written. The next step requires your explicit approval on:

- The end-state structure in §4.
- The implementation plan in §5.
- Answers to the open questions in §6.

Once those are settled, I'll create `projects/methodology-restructure/PROJECT.md` from `templates/PROJECT-TEMPLATE.md` (after Phase 1 hoists the templates to repo root), move this audit into that project folder as a reference artifact, and execute phase-by-phase per the methodology.

---

*End of audit.*
