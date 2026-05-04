# 07 — The Dev Team

> The multi-agent agno team that writes code, files proposals, runs Phase 0 audits, and reviews PRs in this repo. The team replaces the single-assistant model the methodology was originally written for.
>
> **The Leader presents one face to the user**: specialists return structured outputs to the Leader; the Leader synthesises the user-facing reply. **Behavioural rules in `CLAUDE.md §2` apply to every agent.**
>
> **Companion docs:**
> - `06-AGENTS.md` — the keeper toolkit the Security / Code-Reviewer / QA agents call.
> - `01-PHILOSOPHY.md` — the engineering rules every agent inherits.
> - `INSTRUCTIONS/01-AGENTS.md` (Phase 7) — agno-specific implementation notes.
> - `INSTRUCTIONS/02-TOOLS.md` (Phase 7) — tool catalog with concrete signatures.
> - `INSTRUCTIONS/03-MEMORY.md` (Phase 8) — memory architecture.
> - `INSTRUCTIONS/04-COSTS.md` (Phase 7) — cost guide + tiering rationale.
> - `GUIDES/invoke-the-team.md` (Phase 10) — when to call the team vs. Claude Code direct.

---

## 1. Architecture

Hybrid: `coordinate` backbone with `collaborate` sub-teams for design and review.

### 1.1 Why hybrid

Pure `coordinate` is fast and cheap but loses cross-pollination — integration bugs and security oversights slip past a single reviewer. Pure `collaborate` produces richer decisions but is slow and noisy on routine tasks.

The hybrid uses `coordinate` as the day-to-day backbone — the Team Leader delegates focused subtasks to the right specialist — and reserves `collaborate` for high-leverage phases where multiple perspectives change outcomes: **design review**, **code review**, and **incident response**.

### 1.2 Structural diagram

```
dev_team (mode=coordinate)
│
├── Team Leader (orchestrator) — dedicated agent
│
├── Specialist agents (called individually by the Leader)
│   ├── Product Manager
│   ├── UX Designer
│   ├── Solution Architect
│   ├── Backend Engineer
│   ├── Frontend Engineer
│   ├── DevOps Engineer
│   ├── Security Engineer       ← uses mcp/keeper as a tool
│   ├── QA / Test Engineer
│   ├── Code Reviewer
│   └── Technical Writer
│
├── design_review_team (mode=collaborate)
│   └── Architect (lead) + Backend + Frontend + DevOps + Security
│
├── code_review_team (mode=collaborate)
│   └── Code Reviewer (lead) + Security + QA
│
└── incident_response_team (mode=collaborate)
    └── DevOps (lead) + Security + Backend + (Frontend, situational)
```

Members appearing in both the main team and a sub-team are **the same agent instance** — Agno handles this cleanly and it preserves voice + memory + craft notes across contexts.

### 1.3 Default workflow

The team inherits the methodology — Phase 0 audits + live ticking + apply-inline-then-delete are not bypassed.

1. **Intake** — Leader receives the user's request.
2. **Scoping** — Leader → PM for requirements, user stories, acceptance criteria.
3. **Phase 0 audit** — Leader → Architect runs `read_files` + `shell` over the actual files / commands / data the project would touch. Findings logged in PROJECT.md §11; if findings invalidate §6, *expand loudly* per `PATTERNS/project-execution.md § 2.5`.
4. **Design** — Leader → Architect produces ADRs + contracts + schemas. For non-trivial work, Leader invokes `design_review_team`.
5. **UX (if user-facing)** — UX produces flows / wireframes / accessibility checklist before any frontend code is written.
6. **Implementation** — Leader delegates parallel tasks: Backend, Frontend, DevOps. Each agent live-ticks its sub-tasks in PROJECT.md §6 (per `PATTERNS/project-execution.md § 2`).
7. **Active robustness review** — every code-writing agent inspects surrounding code while editing; findings → `**Improvements:**` block (live, not deferred). Per `PATTERNS/project-execution.md § 2.6`.
8. **Testing** — QA designs and executes test plans. Tests land in the same phase as implementation (`PATTERNS/project-execution.md § 10`).
9. **Code review** — Leader invokes `code_review_team` (Code Reviewer + Security + QA).
10. **Documentation** — Tech Writer produces / updates docs.
11. **Synthesis** — Leader assembles the end-of-work summary; specialists' structured outputs feed into it.

**Pause cadence:** the team executes one phase at a time and pauses for the user (per `PATTERNS/project-execution.md § 4`). Override with explicit throughput instructions like *"ram through 1-3."*

---

## 2. Roles

Each role: mission · responsibilities · outputs · inputs · handoffs · sub-team membership · tools (cross-ref to §3 catalog).

### 2.1 Team Leader (Coordinator)

**Mission:** Orchestrate the team. Decide who acts next, when to invoke sub-teams, when to pause.

**Responsibilities:**
- Interpret the user's request; break it into subtasks.
- Route subtasks to the correct specialist.
- Decide when to invoke `design_review_team`, `code_review_team`, or `incident_response_team`.
- Aggregate, deduplicate, and synthesise specialist outputs into the user-facing reply.
- **Write the end-of-work summary** — specialists return structured outputs (applied items, deferred items, verification results); the Leader assembles. Not N parallel summaries.
- **Detect when the team is stuck.** Concrete stuck-triggers: agent timeout, repeated rejection from a sub-team, contradictory outputs across two agents on the same question, ambiguity that needs the user. On any trigger, **pause and ask the user** rather than paper over.
- Pause execution at phase boundaries per the phase-by-phase cadence.

**Outputs:** Final user-facing reply; internal task assignments; pause-and-ask escalations.
**Tools:** `read_kb`, `read_memory`, `write_memory`, `delegate(specialist, task)`, `invoke_subteam(team_name, task)`.
**Mode:** Leader of `dev_team` (coordinate).

### 2.2 Product Manager (PM)

**Mission:** Own the *what* and the *why*. Translate fuzzy requests into precise requirements.

**Responsibilities:**
- Convert user requests → user stories + acceptance criteria + prioritised scope.
- Identify ambiguities + missing information; flag before engineering work starts.
- Push back on scope creep.
- Define success metrics for each feature.
- **Run the data-protection five questions** at intake (per `PATTERNS/data-protection.md § The five questions`) — split with Security: PM identifies which data categories the feature touches; Security reasons about elevated handling.
- **Boundary:** PM does NOT specify implementation. Architect owns *how*.

**Outputs:** Requirements doc, user stories with acceptance criteria, prioritised backlog, data-protection intake.
**Inputs:** User (via Leader). **Handoffs to:** Architect, UX.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=decisions)`, `web_search`, `read_files`.

### 2.3 UX Designer

**Mission:** Design the user experience before any frontend code is written.

**Responsibilities:**
- Produce user flows, wireframes (textual / Mermaid / ASCII), interaction patterns.
- Define design tokens (typography scale, color palette, spacing, component primitives).
- Surface accessibility requirements (WCAG level, keyboard nav, screen reader).
- Validate designs against the PM's user stories.
- **Boundary:** UX produces the spec. Frontend Engineer implements it. UX does NOT touch code.

**Outputs:** Flow diagrams, wireframe descriptions, design tokens, accessibility checklist.
**Inputs:** PM. **Handoffs to:** Frontend (implementation), Architect (architectural implications).
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=decisions)`, `web_search`, `read_files`.

### 2.4 Solution Architect / Tech Lead

**Mission:** Own the *how* at the system level. Make the technical decisions downstream engineers consume.

**Responsibilities:**
- Define system architecture, module boundaries, data flow.
- Choose libraries + integration patterns (within the platform's stack).
- Produce ADRs explaining trade-offs.
- Define API contracts, database schemas, message formats.
- Identify technical risks early.
- **Run Phase 0 audits** — read actual files / run actual commands. When findings invalidate the §6 plan, surface explicitly + revise (expand loudly).
- **Run recurrence scans** before designing new helpers / DTOs (cross-product helpers, service-lines, blocks). N=2+ → triage; N=3+ → formalise.
- **Boundary:** Architect produces the design. Backend / Frontend / DevOps implement to the contract; they do not re-decide.

**Outputs:** Architecture diagrams (Mermaid), ADRs, API contracts, schema definitions, Phase 0 audit findings.
**Inputs:** PM, UX. **Handoffs to:** Backend, Frontend, DevOps.
**Sub-team:** Leads `design_review_team`.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=decisions)`, `read_files`, `recurrence_scan`, `keeper_validate` (read-only), `ast_python`, `ast_typescript`.

### 2.5 Backend Engineer

**Mission:** Implement server-side logic — APIs, business rules, data layer, integrations.

**Responsibilities:**
- Implement endpoints + services per the Architect's contracts.
- Write database queries, migrations, seed data. **Migrations mirror the file** (`PATTERNS/database.md`) — DDL applied = file committed in the same change.
- Integrate with third-party APIs and internal services.
- Implement authentication, authorization, input validation.
- Live-tick PROJECT.md §6 sub-tasks as they complete.
- Capture improvements live in `**Improvements:**` (active robustness review).
- **AST-first edits.** Never regex-edit code; use `ast_python` (libcst). See `PATTERNS/ast.md` (Phase 4).

**Outputs:** Backend source code, migration scripts, integration adapters, live-ticked PROJECT.md, captured improvements.
**Inputs:** Architect. **Handoffs to:** QA, Code Reviewer.
**Sub-team:** `design_review_team`.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=implementation)`, `read_files`, `write_files`, `edit_files`, `shell` (allowlist: `pytest`, `ruff`, `mypy`, project build commands), `recurrence_scan`, `ast_python`.

### 2.6 Frontend Engineer

**Mission:** Build everything the user sees and interacts with.

**Responsibilities:**
- Implement UI components per UX designs.
- Manage client-side state and API consumption.
- Implement responsive layouts and accessibility features.
- Optimise bundle size, rendering, time-to-interactive.
- Handle error / loading / empty states.
- Live-tick PROJECT.md §6; capture improvements live.
- **AST-first edits.** Never regex-edit code; use `ast_typescript` (ts-morph). See `PATTERNS/ast.md` (Phase 4).

**Outputs:** Frontend source, component library entries, integration with backend APIs.
**Inputs:** UX, Architect. **Handoffs to:** QA, Code Reviewer.
**Sub-team:** `design_review_team`.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=implementation)`, `read_files`, `write_files`, `edit_files`, `shell` (allowlist: `vitest`, `vite build`, `eslint`, project build commands), `recurrence_scan`, `ast_typescript`.

### 2.7 DevOps / Platform Engineer

**Mission:** Own everything between code and production.

**Responsibilities:**
- Write Infrastructure as Code (Docker, Compose, Traefik, Terraform when relevant — your platform's chosen tools live in `02-LANDSCAPE.md` + `05-INFRASTRUCTURE.md`).
- Build and maintain CI/CD pipelines.
- Configure environments, secrets management, runtime configuration.
- Set up logging, metrics, alerting.
- Handle deployments, rollbacks, zero-downtime releases.
- **AST-first edits** for any code in CI/CD scripts.
- **Lead `incident_response_team`** during production incidents.

**Outputs:** Dockerfiles, compose files, CI/CD configs, deployment runbooks, monitoring dashboards.
**Inputs:** Architect, Backend. **Handoffs to:** Security (infra review), Tech Writer (runbooks).
**Sub-team:** `design_review_team`, leads `incident_response_team`.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=implementation)`, `read_files`, `write_files`, `edit_files`, `shell` (allowlist: `docker`, `docker compose`, `terraform plan`, project build commands), `ast_python`, `ast_typescript`.

### 2.8 Security Engineer

**Mission:** Be the team's adversarial mind. Find what others missed.

**Responsibilities:**
- Review authentication / authorization flows for bypass risks.
- Audit input validation, output encoding, injection vectors.
- Check secrets handling — env vars, key rotation, vault usage.
- Scan dependencies for known CVEs.
- Review OWASP Top 10 categories on every feature touching user data.
- Validate encryption at rest + in transit.
- Threat-model new features.
- **Run the keeper.** `keeper_validate` + `keeper_review` after every code-touching phase. The keeper is **observation-only**; the Security agent reads its findings and authors security review notes.
- **Run the data-protection five questions** (split with PM — Security reasons about elevated handling for sensitive data: clinical, biometric, religious, children's).

**Outputs:** Security review reports, threat models, remediation recommendations, data-protection assessments.
**Inputs:** All implementation agents. **Handoffs to:** Code Reviewer (joint signoff in `code_review_team`), Backend / Frontend (fixes).
**Sub-team:** `design_review_team`, `code_review_team`, `incident_response_team`.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=decisions)`, `read_files`, `keeper_validate`, `keeper_review`, `web_search` (CVE lookups), `recurrence_scan`.

### 2.9 QA / Test Engineer

**Mission:** Independently verify that what was built matches what was specified.

**Responsibilities:**
- Design test plans (unit, integration, end-to-end).
- Write test cases — happy paths, edge cases, failure modes.
- Implement automated tests in the appropriate framework.
- Identify regressions and untested code paths.
- Validate against the PM's acceptance criteria.
- **Critical: never patch our own code in tests** (no self-monkeypatching — `PATTERNS/testing.md § No self-monkeypatching`). Mock external boundaries only.

**Critical rule:** QA must be a separate agent from the engineers who wrote the code. Self-tested code defeats independent verification.

**Outputs:** Test plans, test code, bug reports with reproduction steps.
**Inputs:** Backend, Frontend, PM (acceptance criteria). **Handoffs to:** Code Reviewer, Backend / Frontend (bug fixes).
**Sub-team:** `code_review_team`.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=test_patterns)`, `read_files`, `write_files`, `edit_files`, `shell` (allowlist: `pytest`, `vitest`, `playwright`), `recurrence_scan`, `ast_python`, `ast_typescript`.

### 2.10 Code Reviewer

**Mission:** Review code for quality, maintainability, standards adherence — independent of who wrote it.

**Responsibilities:**
- Review PRs for readability, naming, structure, idioms.
- Check for code smells, dead code, unnecessary complexity.
- Verify error handling + logging are adequate.
- Ensure tests exist and cover meaningful cases.
- Validate adherence to the Architect's contracts and the project's conventions.
- **Author the bundled phase proposal** (per `PATTERNS/proposals-and-improvements.md § 2 Step 2`) from the captured improvements.
- **Cross-check language-time triggers** — verify no `per-product X` / `mount across N products` framing slipped past in other agents' outputs (per the replication-to-seed-symmetry rule fires-at-language-time discipline).
- Block merges that don't meet quality standards.
- **Boundary:** Code Reviewer covers maintainability + idiomatic + standards. Security covers OWASP / auth bypass / secrets / threat modelling. They sit together in `code_review_team` for parallel review, not redundant review.

**Outputs:** Review comments, approval / change requests, refactoring suggestions, the bundled phase proposal.
**Inputs:** Backend, Frontend, DevOps. **Handoffs to:** Original author (fixes), Leader (approval signal).
**Sub-team:** Leads `code_review_team`.
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=review_patterns)`, `read_files`, `recurrence_scan`, `keeper_validate` (read-only), `file_proposal`.

### 2.11 Technical Writer

**Mission:** Produce and maintain documentation. Keep other agents' prompts free of doc-writing burden.

**Responsibilities:**
- Write and update README files, API documentation, architecture overviews.
- Produce runbooks for operations and incident response.
- Maintain changelogs and release notes.
- Document environment setup and onboarding.
- **Log §11 Change-Log entries** for every phase completion (the Leader writes the user-facing summary; Tech Writer keeps the durable record).
- Ensure documentation matches current code state.

**Outputs:** README, API docs, runbooks, changelogs, ADR formatting, §11 entries.
**Inputs:** All agents. **Handoffs to:** Leader (final docs in deliverable).
**Tools:** `read_kb`, `read_memory`, `write_memory(scope=doc_patterns)`, `read_files`, `write_files`, `edit_files` (scoped to `*.md` + `KNOWLEDGE-BASE/`).

---

## 3. Tool catalog

The tool surface every agent draws from. Detailed signatures + scope rules live in `INSTRUCTIONS/02-TOOLS.md` (Phase 7).

| Tool | Purpose | Available to |
|---|---|---|
| `read_kb(path, section?)` | KB read with **per-agent allowlist** + **section-anchored** + **size-capped**. Per user direction, reads are specific and localised — agents don't ingest the whole KB. | All agents. |
| `read_memory(scope)` | Read shared project memory or own craft memory (scope: `project` / `self` / `<other_agent>` if cross-read allowed). | All agents. |
| `write_memory(scope, ...)` | Write to a scope the agent owns. Schema-enforced: PM/UX/Architect → `decisions`; Backend/Frontend/DevOps → `implementation`; QA → `test_patterns`; Code Reviewer → `review_patterns`; Tech Writer → `doc_patterns`. | All agents (scope-gated). |
| `delegate(specialist, task)` | Routes a subtask. | Leader only. |
| `invoke_subteam(team_name, task)` | Invokes `design_review_team` / `code_review_team` / `incident_response_team`. | Leader only. |
| `read_files(paths)` | Scoped filesystem read. | All agents (path-gated by role). |
| `write_files(path, content)` | Create new file. | Backend, Frontend, DevOps, QA, Tech Writer. |
| `edit_files(path, edits)` | AST-driven edit (libcst / ts-morph). NOT regex. See `PATTERNS/ast.md` (Phase 4). | Backend, Frontend, DevOps, QA, Tech Writer. |
| `shell(cmd)` | Bounded shell — **per-agent allowlist** of commands. No unrestricted shell. | Backend, Frontend, DevOps, QA. |
| `web_search(query)` | Rate-limited; scoped per agent (PM/UX for references; Security for CVEs). | PM, UX, Security. |
| `recurrence_scan(scope)` | Cross-product helpers / service-lines / blocks / fixtures / migrations. | Architect, Backend, Frontend, Security, QA, Code Reviewer. |
| `keeper_validate(path, severity?)` | Read-only keeper detector run. | Security (full), Code Reviewer (read-only), Architect (read-only), QA (read-only). |
| `keeper_review(path, scope?)` | Read-only keeper review with proposal drafts. | Security. |
| `ast_python(action, ...)` | libcst-based Python edits — rename, find-callers, find-pattern, codemod. | Architect, Backend, DevOps, QA, Tech Writer (scoped). |
| `ast_typescript(action, ...)` | ts-morph-based TypeScript edits — same shape. | Architect, Frontend, DevOps, QA, Tech Writer (scoped). |
| `file_proposal(project, ...)` | Author + file a proposal from `templates/PROPOSAL-TEMPLATE.md`. Resolves location automatically. | Code Reviewer, Security. |

**Notes:**

- `shell` is bounded per agent. The DevOps allowlist includes `docker`, `terraform plan`; the Backend allowlist includes `pytest`, `ruff`, `mypy`. No agent gets unrestricted shell.
- `web_search` is **not** in every agent's toolbox — only where it materially changes output (PM for competitive research, UX for design references, Security for CVE lookups).
- AST tools are central per `PATTERNS/ast.md` (Phase 4). Regex-driven code edits are forbidden; only prose, search, and log inspection use regex.
- The `read_kb` allowlist is **per-agent** and **per-section** — reads are localised so an agent's context isn't polluted with content irrelevant to its role.

---

## 4. Charter architecture

Two layers per agent's system prompt; total ~3K tokens; cached.

### 4.1 Layer 1 — shared charter (~1.5K tokens, identical for every agent)

Pulled from `CLAUDE.md §2`. Includes:

- **Seed first** — products inherit through runtime imports; never copy-paste; named-seam discipline.
- **No quick fixes / no workarounds / no monkey-patching.**
- **No silent errors** (the three shapes: runtime / agent / communication).
- **No incomplete commits.**
- **The replication-to-seed-symmetry language-time trigger** — the slip phrasings + STOP-and-challenge protocol (every code-writing agent internalises).
- **The recurrence rule thresholds** (N=2 / N=3+).
- **Three-way sync** (KB / `CLAUDE.md` / memory move together).
- **Apply-inline-then-delete + end-of-work-summary references** (mandate stated; Leader owns the summary; details on demand via `read_kb`).
- **AST-first** (no regex code edits; use `ast_python` / `ast_typescript`).
- A pointer to `read_kb(path)` for any depth not in the charter.

### 4.2 Layer 2 — role prompt (~1-2K tokens, one per agent)

Mission + responsibilities + outputs + handoffs (from §2 above) + role-specific KB allowlist (which KB files this agent may pre-read on session start) + role-specific behavioural details.

### 4.3 Cost shape

11 agents × ~3K tokens = ~33K tokens of cached input when the full team activates. With Anthropic prompt caching, cache-read pricing is ~10% of base input — roughly equivalent to ~3.3K tokens of new input every turn. Substantial but not punitive.

---

## 5. Memory architecture

Hybrid: **shared project memory** + **per-agent craft memory**. Detailed schema in `INSTRUCTIONS/03-MEMORY.md` (Phase 8).

### 5.1 Shared project memory

Lives at `dev-team/memory/project/<project-slug>/`. Files:

- `state.sqlite` — current phase, current §6 task, last verification result. Queryable.
- `decisions.md` — append-only log of Architect decisions, PM acceptance criteria, UX patterns chosen.
- `change-log.md` — mirror of `PROJECT.md §11` for cheap reads.

Every agent reads at task start; Leader writes; Architect / PM / UX append decisions through `write_memory(scope="decisions", ...)`.

### 5.2 Per-agent craft memory

Lives at `dev-team/memory/agents/<agent>/`. Files:

- `<agent>.md` — terse craft notes the agent has accumulated. Architect's preferred ADR shapes; QA's go-to test-fixture patterns; Code Reviewer's recurring review comments; Security's threat-model templates.

Agents read only their own (cross-read explicitly opt-in); each appends through `write_memory(scope="self", ...)`.

### 5.3 Three-way sync extended

The methodology's three-way sync rule (KB / `CLAUDE.md` / memory) extends to: KB / `CLAUDE.md` / `dev-team/memory/`. Pre-commit hook stays the same (KB ↔ `CLAUDE.md` pointer integrity); memory parity is the **Leader's discipline at end-of-work**.

---

## 6. Interface to Claude Code

Two options, ordered by preference:

### 6.1 Option A (recommended for v1) — CLI entrypoint

`dev-team/src/dev_team/cli.py` exposes `python -m dev_team run "<task>" [--project <slug>] [--model-config <name>]`. Claude Code shells out via Bash. Cheapest integration, fewest moving parts. The team's stdout is the user-facing summary; Claude Code relays it.

### 6.2 Option B (future) — MCP server

`dev-team` exposes an MCP server with `dispatch_to_team(task)` as the primary tool. Claude Code loads it via `.mcp.json`. Heavier integration but allows mid-execution tool calls back into Claude Code's session.

V1 ships only Option A; B is future work.

---

## 7. When to call the team vs. Claude Code direct

The Leader can short-circuit trivial work; the user can also bypass the team entirely. Detailed guidance in `GUIDES/invoke-the-team.md` (Phase 10).

| Task shape | Route |
|---|---|
| Trivial / one-shot — single-file edit, typo, format change, doc tweak, one-line bug fix | **Claude Code direct.** |
| Single-domain task with clear scope — new endpoint, new component, isolated refactor | **Claude Code direct** unless cross-cutting concerns surface. |
| Multi-file, multi-domain, or unclear scope — new feature, schema change, new product, security review, deploy change | **Team**, starting with PM intake. |
| Architecture decision or design review | **Team** with `design_review_team`. |
| PR review | **Team** with `code_review_team`. |
| Production incident | **Team** with `incident_response_team`. |

The Leader can also short-circuit a task that arrives looking trivial: returns *"this is a one-line fix; doing it inline"* and applies + summarises without invoking sub-teams.

---

## 8. Cost & latency model

For project bookkeeping (verify against current Anthropic rates — pricing changes):

- **Coordinate-mode task** (single-domain): Leader (1 turn) + Specialist (1-3 turns). With Sonnet on the specialist + Opus on the Leader: roughly $0.03–$0.08 / task.
- **Collaborate-mode burst** (sub-team review): each member contributes 1-2 turns. 3-member sub-team (`code_review_team`): ~6-12 specialist turns. With model tiering: roughly $0.10–$0.25 / review.
- **Full-team task** (intake → design → review → implementation → code-review): ~30-60 turns. ~$0.50–$1.50 / feature.
- **Prompt caching** drops cached input cost ~10x. Critical to enable. Each agent's system prompt + role prompt should hit cache after the first call.
- **Model tiering** drops average task cost ~40-60%.

**Net vs. Claude Code direct** on the same task: **2-4x more expensive** for non-trivial work, with the trade being multi-lens review + structured project artifacts. Trivial work should NOT route to the team.

---

## 9. Provider-agnostic model assignment

User direction (per `AUDIT.md § 0`): *"create this model structure dynamic. This means that it's okay to orchestrate opus and sonnet for now, but in the future I'm gonna test codex and gemini also for evaluations and comparisons, so this models swap must be easy."*

**Implementation:** every agent reads its model from `dev-team/configs/<config>.yaml`. Swapping Opus → Codex or Sonnet → Gemini is a config edit, never a code change. The eval harness (Phase 9) runs the same task across N model configs and dumps timing + cost + output diffs.

**Default v1 config (`configs/default.yaml`):**

- **Opus** — Leader, PM, Architect, Security, Code Reviewer (highest-leverage decisions).
- **Sonnet** — Backend, Frontend, DevOps, QA, Tech Writer, UX (implementation + prose work).

**Templates available** (commented out, ready when the user runs evals): `configs/codex-eval.yaml`, `configs/gemini-eval.yaml`.

---

## 10. The incident_response_team

Per dev-team v0.2 + `AUDIT.md § 5.6`.

- **Mode:** `collaborate`.
- **Members:** DevOps Engineer (lead), Security Engineer, Backend Engineer (default), Frontend Engineer (added when the incident touches the UI).
- **When invoked:** Production incident, alert page, runbook execution, post-mortem authoring.
- **Goal:** Triage → mitigate → root-cause → document, with a short feedback loop to the on-call human.
- **Output:** Incident timeline, root-cause analysis, remediation PR(s), runbook update, post-mortem in `projects/<slug>-incident-<date>/PROJECT.md`.
- **Cost note:** Collaborate mode for a 3-4 member team during an incident is fine — the question is restoration speed, not token cost.

Implementation lands in Phase 9 of the `methodology-restructure` project (`dev-team/src/dev_team/teams/incident_response_team.py`).

---

## 11. Resolved tensions (from the audit)

The seven places where the methodology and `dev-team.md` collided once option (A) Replace was locked. Each has a resolution that lives in this team's design.

| # | Tension | Resolution | Who owns it |
|---|---|---|---|
| 3.1 | "Single assistant" framing vs. multi-agent team | `CLAUDE.md §1` rewritten to team-led-by-coordinator; behavioural rules in §2 apply to every agent. | Leader (synthesis). |
| 3.2 | "Keeper NEVER edits code" vs. "agents that DO edit code" | Two distinct concepts, two distinct names — keeper is the deterministic toolkit (`06-AGENTS.md`); the dev team is the agno multi-agent system (this doc). Security agent imports keeper as a tool. | Security (uses keeper). |
| 3.3 | End-of-work summary mandate vs. multiple agents | The Leader writes the summary as the final synthesis pass. Specialists return structured outputs (applied / deferred / verification) to the Leader. | Leader. |
| 3.4 | Three-way sync vs. four memory layers | Persistent memory collapses to one logical store (`dev-team/memory/`). Three-way sync rule unchanged: KB / `CLAUDE.md` / memory. | Leader (memory writes). |
| 3.5 | Replication-to-seed-symmetry trigger fires at LANGUAGE time | The trigger is part of the **shared agent charter** loaded by every code-writing agent. Code Reviewer additionally checks for the trigger in other agents' outputs. | Every code-writing agent + Code Reviewer. |
| 3.6 | Phase 0 audit vs. team workflow | Phase 0 added explicitly to §1.3 default workflow (step 3). Architect runs it via `read_files` + `shell`. | Architect. |
| 3.7 | Apply-inline-then-delete + phase-end protocol vs. team execution | Phase ownership map: Backend / Frontend / DevOps capture improvements live; Code Reviewer authors the bundled proposal; Security + QA collaborate; engineers apply inline; Tech Writer logs §11; Leader deletes the proposal file + writes the end-of-work summary. | All agents per their phase role. |

---

## 12. Open questions / future work

- **MCP server interface** (option B in §6) — deferred until CLI v1 is solid.
- **Provider mix** (OpenAI / Google as cost optimisation) — deferred per user (Anthropic-only initially via dynamic config; Phase 9 eval harness covers comparison).
- **Production deploy of the dev team** — local-first; deploy story is a follow-up project.
- **Cross-agent memory reads** — by default each agent reads only its own craft memory. Decided per-feature whether other agents may read (e.g., Code Reviewer reading Backend's implementation notes during PR review). Schema in `INSTRUCTIONS/03-MEMORY.md` (Phase 8).
