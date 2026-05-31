# methodology-restructure — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update the Change Log. See `CLAUDE.md → § Engineering Philosophy → Projects are living + scope-scoped`.
>
> **Write for a zero-context reader.** The next agent to pick up this project has not seen the conversation that produced it. Inline context in §1, quote the user in §2, name files with paths in §5, pair every §7 Open Question with an evidence-backed recommendation, and make §10 commands copy-paste ready.

- **Created:** 2026-04-30
- **Last updated:** 2026-04-30
- **Status:** Phase 0 ✅ → Phase 1 ✅ → Phase 2 ✅ → Phase 3 ✅ → Phase 4 ✅ (six recurring rules deduplicated, AST-first principle added to philosophy, PATTERNS/ast.md created, CLAUDE.md §2 AST line + §3 map ast pointer landed) → Phase 5 pending (populate seed/ with the reference stack — 3-5 sessions per audit)
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com) · the AI dev team (once wired)
- **Related docs:** `AUDIT.md` (this folder — the canonical Phase 0 audit), `dev-team.md` (root, will be absorbed in Phase 3), `CLAUDE.md` (root, refined in Phase 2), `KNOWLEDGE-BASE/` (root, refined throughout)
- **Project slug:** `methodology-restructure` — cross-cutting (touches the seed, the KB, the dev-team), so lives at `projects/<slug>/` per `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md § Where projects live`.

---

## 1. Context & Purpose

This repo (`automations/`) is being established as the new home of the Noctus AI-first development methodology. Two artifacts existed before this project:

1. `noctus-starter/` — a methodology scaffold extracted from a working multi-product SaaS. Stack-agnostic. Methodology + structure + automation hooks + empty seed stubs. ~4,400 lines of docs.
2. `dev-team.md` (root) — a v0.1 reference spec for a multi-agent Agno dev team (11 specialists + 3 sub-teams in a hybrid coordinate/collaborate architecture).

The two never talked to each other. This project consolidates them: the methodology becomes the team's behavioral charter; the team replaces the single-assistant model assumed by the methodology; the keeper's deterministic detectors survive as a tool the Security agent calls; the reference stack (FastAPI + Supabase + React + Vite + TanStack + Zustand + Tailwind) populates `seed/` so the methodology becomes legible.

Phase 0 (the audit) is captured in `AUDIT.md` — the canonical reference for every decision, tension resolution, and proposed phase in this project. Read it first.

---

## 2. Confirmed constraints

Decisions the user made during the audit conversation. Direct quotes preserved where decisive.

- **Replace, not coexist** — *"1. A"* — The Agno dev-team replaces the single-assistant + observation-only-keeper model. The keeper's deterministic detectors survive as a tool the Security agent calls; LLM-authored review work goes to Code Reviewer + Security agents collaborating. *(Forecloses parallel-system complexity.)*
- **`automations/` is the new home; `noctus-starter/` deleted** — *"it lives in this repo, that's gonna be its new home. noctus-starter is gonna get deleted and dev-team is a guide-reference doc"* — `dev-team.md` becomes a KB doc (`KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md`); the agno code lives at `automations/dev-team/`. *(Drives the hoist in Phase 1 + the dev-team.md absorption in Phase 3.)*
- **Stack-agnostic docs + populated reference stack in `seed/`** — option (C). Reference stack confirmed: FastAPI + Supabase + React + Vite + TanStack Query + Zustand + Tailwind + Pydantic v2 + ruff + mypy + pytest + vitest. *(Drives Phase 5 fuller scope — full backend + full frontend reference implementation.)*
- **Memory hybrid + scoped KB reads** — option (C) hybrid: shared **team/project memory** + per-agent **craft memory**. Team always follows `CLAUDE.md` + KB. KB reads are **specific and localized** — *"i want this kb read to be specific and localized, so agents don't read and get poluted with content it doesnt need"* — per-agent allowlist + section-anchored reads + hard cap on per-call return size. *(Drives Phase 7 tool design.)*
- **Refine both** — `noctus-starter` (now hoisted) AND `dev-team.md` get refined where useful, not just integrated. *(Drives the deduplication work in Phase 4 and the dev-team.md → 07-DEV-TEAM.md rewrite in Phase 3.)*
- **Seed scope = fuller** — *"fuller"* — Phase 5 lands the full backend (auth + roles + invitations + notifications + email templates + standard routers + LLM client) + full frontend (Sidebar / Header / AppShell / NotificationBell / LoginForm / ErrorBoundary + auth.ts + stores.ts + hooks.ts + crud-hooks factory + design system primitives). *(Drives 3-5 working sessions for Phase 5.)*
- **Dynamic model orchestration** — *"create this model structure dynamic. This means that it's okay to orchestrate opus and sonnet for now, but in the future I'm gonna test codex and gemini also for evaluations and comparisons, so this models swap must be easy"* — model assignment per agent is config-driven via `dev-team/configs/*.yaml`, supports per-run overrides, and ships an eval harness for A/B comparisons across providers. *(Drives Phase 7 + Phase 9 design.)*
- **AST-first principle** — added to the methodology this turn (per user request). Any code change goes through an AST tool (libcst / ts-morph / tree-sitter); regex/sed only for prose, search, log inspection. New principle in `01-PHILOSOPHY.md` + new `PATTERNS/ast.md` + `ast_python` / `ast_typescript` agent tools. *(Threads through Phase 4 + Phase 6 + Phase 7.)*
- **dev-team.md v0.2 answers** — Team Leader = dedicated agent. Add `incident_response_team` sub-team. Per-project context injection = scope by project. Memory = shared (refined to hybrid above). *(Drives the 07-DEV-TEAM.md rewrite + Phase 9 design.)*

---

## 3. Design principles

How we're approaching this specific consolidation (beyond the platform-wide rules in `CLAUDE.md`).

1. **No code edits without an AST.** The new AST-first principle applies to this project too. KB content edits use `Edit`/`Write` (markdown is prose). Code edits — once `seed/` and `dev-team/` start landing — go through libcst (Python) and ts-morph (TypeScript).
2. **One canonical home per rule, pointers everywhere else.** The audit's §1.2 cataloged six rules each living in 3-4 places. The deduplication work (Phase 4) puts each rule in one canonical KB file and replaces the duplicates with one-line pointers. The pre-commit hook already enforces pointer integrity.
3. **The Leader presents one face to the user.** With 11 agents writing parts of every reply, the Leader assembles the end-of-work summary. Specialists return structured outputs to the Leader, not directly to the user.
4. **Cost-aware by construction.** Lean charters (~3K tokens/agent total). Localized KB reads. Model tiering. Prompt caching enabled. `coordinate` for routine work, `collaborate` only for design-review and code-review where multi-lens changes outcomes.
5. **Provider-agnostic model assignment.** Every agent reads its model from `configs/<name>.yaml`. Swapping Opus → Codex or Sonnet → Gemini is a config edit, not a code change. Eval harness runs the same task across model configs and dumps timing + cost + output diffs.
6. **Apply-inline-then-delete + end-of-work summary on every phase close.** The methodology's existing protocol (`PATTERNS/proposals-and-improvements.md § 4b § 4c`) governs every phase of this project too.

---

## 3a. Seed-first analysis (REQUIRED)

This project is **methodology-shaped, not feature-shaped** — it touches the seed structure itself, the KB, the templates, the pre-commit machinery. The §3a checklist still applies; most answers are seed-internal.

1. **Where does this capability live in the runtime tree?** Seed framework (`seed/`), seed library (`seed/<side>/lib/`), KB (`KNOWLEDGE-BASE/`), templates (`templates/`), keeper (`mcp/keeper/`), dev-team (`dev-team/`). Every layer is touched. **Zero product-domain code lands in this project** — products consume the result, they don't carry methodology code.
2. **Per-product code count.** **Zero.** This project doesn't add per-product code; it lays the seed + framework + tooling that products will consume.
3. **Seam.** The whole point of this project is **establishing the seams** — `create_product_app(...)` kwargs, `createProductApp({...})` config, `standard_routers=[...]`, `authProvider`, `Layout`, build-config factory, design-system imports. Phase 5 populates them.
4. **Existing seed pattern coverage.** N/A — `seed/` is empty. Phase 5 builds the patterns in.
5. **Triage decision.** N/A — no divergence from contract; this IS the contract.
6. **Recurrence scan.** N/A pre-Phase-5 (no products yet). Once products exist, the scans run normally.

**Litmus — per-product code count this design requires:** [x] **0 lines** — pure cross-product concern; lives entirely in seed.

**Phase plan implications:** §6 phases work in seed / framework / KB / dev-team layers. None walk through products. Correct shape per the language-trigger rule.

---

## 4. Scope

**In scope:**

- Hoist `noctus-starter/` content to repo root (Phase 1).
- Refine `CLAUDE.md` for the multi-agent team (Phase 2).
- Rewrite `06-AGENTS.md` + create `07-DEV-TEAM.md`; delete root `dev-team.md` (Phase 3).
- Deduplicate KB content + add AST-first principle + create `PATTERNS/ast.md` (Phase 4).
- Populate `seed/` with the full reference stack (Phase 5).
- Implement `mcp/keeper/` with the minimal v1 detector set, AST-based (Phase 6).
- Scaffold `dev-team/` Python package with agents, teams, tools, prompts, memory, configs (Phase 7).
- Wire memory architecture (Markdown + SQLite hybrid) (Phase 8).
- Spec + implement `incident_response_team` + the eval harness (Phase 9).
- Update root `README.md` + `GUIDES/invoke-the-team.md` (Phase 10).
- Final verification (Phase 11).

**Out of scope (for now — with reason):**

- Building actual products under `products/<slug>/` — this project lays the foundation; first product is a separate project.
- Multi-tenant control-plane (`core/`) implementation — deferred until a real control-plane need arises; `core/` stays as a placeholder per the methodology.
- Production deploy of the dev-team — local-first; deploy story is a follow-up project.
- MCP-server interface for the dev-team — Phase 7 ships CLI only; MCP is future work per the audit.
- Full keeper detector inventory — Phase 6 ships the minimal 5; the rest grow over time.

---

## 5. Architecture / Data Model

End-state structure after Phase 11. Reference: `AUDIT.md § 4`.

```
automations/
├── CLAUDE.md                          ← rewritten (Phase 2)
├── README.md                          ← rewritten (Phase 10)
├── KNOWLEDGE-BASE/                    ← refined (Phase 4)
│   ├── INDEX.md
│   ├── AGENT-CONTEXT.md
│   ├── CONTEXT/
│   │   ├── 01-PHILOSOPHY.md           ← + AST-first principle (Phase 4)
│   │   ├── 02-LANDSCAPE.md            ← reference stack details (Phase 5)
│   │   ├── 03-SEED-ARCHITECTURE.md
│   │   ├── 04-SHARED-LIBRARY.md       ← reference catalog filled (Phase 5)
│   │   ├── 05-INFRASTRUCTURE.md       ← reference deploy details (Phase 5)
│   │   ├── 06-AGENTS.md               ← rewritten: team + keeper-as-tool (Phase 3)
│   │   ├── 07-DEV-TEAM.md             ← NEW (Phase 3)
│   │   ├── PATTERNS/
│   │   │   ├── ... (existing)
│   │   │   └── ast.md                 ← NEW (Phase 4)
│   │   └── GUIDES/
│   │       ├── ... (existing)
│   │       └── invoke-the-team.md     ← NEW (Phase 10)
│   └── INSTRUCTIONS/
│       ├── 00-MASTER.md
│       ├── 01-AGENTS.md               ← NEW (Phase 7)
│       ├── 02-TOOLS.md                ← NEW (Phase 7)
│       ├── 03-MEMORY.md               ← NEW (Phase 8)
│       └── 04-COSTS.md                ← NEW (Phase 7)
├── seed/                              ← populated (Phase 5)
│   ├── backend/{lib,framework}/
│   └── frontend/{lib,framework}/
├── products/.gitkeep
├── projects/methodology-restructure/  ← THIS PROJECT
├── core/.gitkeep                      ← placeholder per methodology
├── templates/
├── scripts/
├── mcp/
│   └── keeper/                        ← NEW Python package (Phase 6)
└── dev-team/                          ← NEW Agno python implementation (Phase 7)
    ├── pyproject.toml
    ├── configs/
    │   └── default.yaml               ← model assignment per agent
    ├── src/dev_team/
    │   ├── cli.py
    │   ├── agents/{leader,pm,ux,architect,backend,frontend,devops,security,qa,code_reviewer,tech_writer}.py
    │   ├── teams/{dev_team,design_review_team,code_review_team,incident_response_team}.py
    │   ├── tools/{kb,filesystem,shell,keeper,recurrence,proposals,memory,ast_python,ast_typescript}.py
    │   ├── memory/{project,agents}/
    │   └── prompts/{shared,agents}/
    ├── evals/                         ← model A/B harness (Phase 9)
    └── tests/
```

---

## 6. Implementation phases

### Phase 0 — Audit ✅

- [x] Read all 4,400 lines of `noctus-starter/` + `dev-team.md`.
- [x] Audit redundancy, gaps, inconsistencies.
- [x] Resolve seven tensions between methodology and dev-team spec.
- [x] Propose end-state structure + 11-phase plan.
- [x] Surface 10 open questions; user answered key ones; defaults set for the rest.
- [x] Document captured in `AUDIT.md` (this folder — moved here in Phase 1).

**Improvements:**
- The audit took ~3,000 lines of reading before the first user clarification turn — could have stopped earlier with a structured "what shape do you want?" check; in fact did once the user pushed back on inference. Captured: read-then-clarify is a fine pattern when token cost is the only constraint, but a clarify-first pattern is cheaper when the deliverable shape is unknown.
- The audit's §6 "remaining open questions" list bundled 10 questions; in practice the user answered #3 and #4 inline, gave a recommendation request on #3 and a clarification on #4, and ignored the rest. Future audits should ask 2-3 load-bearing questions, not 10.

### Phase 1 — Hoist `noctus-starter/` + scaffold this project doc ✅

- [x] Move `noctus-starter/{CLAUDE.md, README.md, core, KNOWLEDGE-BASE, mcp, products, projects, scripts, seed, templates, .gitignore}` to repo root.
- [x] Remove empty `noctus-starter/` directory.
- [x] Run `bash scripts/verify-kb-sync.sh` from new root — confirm all CLAUDE.md pointers resolve + all KB docs indexed. *(Result: ✓ KB sync OK.)*
- [x] Create `projects/methodology-restructure/` with `proposals/.gitkeep`.
- [x] Populate this `PROJECT.md` from `templates/PROJECT-TEMPLATE.md`.
- [x] Move `AUDIT.md` from repo root to `projects/methodology-restructure/AUDIT.md` as a reference artifact. *(Clean-folder principle: audit doesn't live at root.)*
- [x] Confirm root layout matches §5 Architecture diagram (minus the not-yet-built items). *(Confirmed: `CLAUDE.md`, `README.md`, `.gitignore`, `core/`, `KNOWLEDGE-BASE/`, `mcp/`, `products/`, `projects/`, `scripts/`, `seed/`, `templates/` at root. `dev-team.md` at root is a known stray — Phase 3 absorbs it.)*
- [x] Phase 1 close: improvements captured below; no bundled proposal filed (Phase 1 produced only observational items, no actionable bundle to triage); §11 entry added.

**Improvements:**
- `verify-kb-sync.sh` worked from the new root without modification. The script's `REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"` math is portable — good architecture, no churn needed in Phase 1.
- `dev-team.md` left at root after the hoist. Known stray; Phase 3 absorbs it into `KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md`. Flagged here so the next agent doesn't trip on it as a clean-folder violation.
- `automations/` is not a git repo. The pre-commit hook (`scripts/install-hooks.sh`) cannot be installed until `git init` runs. Documented in §8 Dependencies & blockers; flagged here as a deferred item the user controls.
- `core/` ships with `core/projects/.gitkeep` + `core/README.md` but no `core/.gitkeep` at the folder root. The folder is non-empty so git tracks it without the keep-file. No action needed; noted for §7 Open Question #1 (keep-or-drop) if the user chooses to drop, the deletion is `rm -rf core/`.
- `.DS_Store` was present at the root before the hoist (macOS artifact), already covered by `.gitignore`. No remediation required.
- The `AUDIT.md` move from root → `projects/methodology-restructure/AUDIT.md` is the methodology's clean-folder rule applied to itself. The audit is now correctly co-located with the project that consumes it; the root stays minimal.

*Phase 1 produced no items requiring proposal-bundle triage — all improvements are observational notes for the retrospective. Per `PATTERNS/proposals-and-improvements.md § 1` (Improvements lifecycle: "no accept/reject; the retrospective is a log, not a queue"), no proposal file was filed for Phase 1.*

### Phase 2 — Refine `CLAUDE.md` for the multi-agent team ✅

- [x] Rewrite §1 (the team's role) — *"The AI capability in this repo is a multi-agent team led by a coordinator. The Leader presents one face to the user. The behavioral rules in §2 apply to every agent."* Header comment + §0 table row updated to "the team" framing in the same edit.
- [x] Tighten §2 (engineering philosophy) — replaced repeated rule prose with one-line + threshold/litmus + KB pointer. CLAUDE.md went from ~22kb to ~19kb (-14% overall, with §2 hitting close to the -30% target).
- [~] **DEFERRED to Phase 3** (per user direction — §3 map pointers depend on files that don't exist yet): Update §3 (the map) — add pointers to `06-AGENTS.md` and `07-DEV-TEAM.md`. *Tracked as a sub-task on Phase 3.*
- [~] **DEFERRED to Phase 4** (same reason): Update §3 map with pointer to `PATTERNS/ast.md`; add `CLAUDE.md §2` line for AST-first principle. *Tracked as sub-tasks on Phase 4.*
- [x] Verify KB sync passes after edits. *Result: ✓ KB sync OK.*

**Improvements:**
- The verifier's regex `\`KNOWLEDGE-BASE/[^\`]+\.md\`` requires the path's closing backtick to immediately follow `.md` — section-anchored pointers like `\`KNOWLEDGE-BASE/.../foo.md § anchor\`` slip through and aren't checked. Functional today (broken anchored paths fail loudly when an agent follows them) but a future hardening pass could extend the regex to also validate anchored forms by matching `\`KNOWLEDGE-BASE/[^\`]+\.md(\s§ [^\`]+)?\``. Captured here as a Phase 6 keeper enhancement candidate (a real `check_kb_pointer_resolves` detector should subsume the shell verifier).
- §1's framing now has TWO Leader-mentions per audit §3.1 + §3.3 (the Leader synthesises; specialists return to Leader, not user). The two are distinct enough to keep separately, but a future tightening could collapse them. Watch for redundancy if §1 grows further.
- §2's "Behavioral rules for the team" subsection still has only three items. As Phase 3+4 add the AST-first line and the team-coordination behaviors expand, this subsection may need a sub-subsection split. Note for Phase 4 / Phase 7 reviewers.

*No bundled proposal filed for Phase 2 — improvements are observational meta-notes about the verifier and future tightening, not actionable items requiring triage. Per `PATTERNS/proposals-and-improvements.md § 1` (Improvements lifecycle: "no accept/reject; the retrospective is a log, not a queue"), no proposal file was filed.*

### Phase 3 — Rewrite `06-AGENTS.md` + add `07-DEV-TEAM.md`; delete root `dev-team.md` ✅

- [x] Rewrite `06-AGENTS.md` to describe **two distinct concepts, two names** (keeper = deterministic toolkit; dev team = agno multi-agent system). Detector inventory carries over with `(v1)` annotation per `AUDIT.md § 6.5`; orchestration framing replaced; new "How the dev team uses the keeper" section maps every detector / scan to its consuming agent. Added `check_kb_pointer_resolves` (v1) detector to formally subsume the shell verifier (the Phase 2 improvements note about regex weakness is captured here).
- [x] Create `07-DEV-TEAM.md` absorbing `dev-team.md` content with: v0.2 answers integrated (Leader = dedicated agent, `incident_response_team` added, scope-by-project, hybrid memory); the seven tension resolutions from `AUDIT.md § 3` (table form in §11 of the new doc); concrete tool catalog per agent (15 tools across 11 agents); memory architecture pointer; Claude Code interface spec (CLI primary, MCP future); when-to-call-the-team thresholds (table form); `incident_response_team` design; AST-first reference threaded through every code-writing role (forward-pointer to `PATTERNS/ast.md` lands in Phase 4); provider-agnostic model assignment via `configs/<name>.yaml`.
- [x] Add new files to `KNOWLEDGE-BASE/INDEX.md` — layout tree updated, by-topic table updated, by-situation table updated.
- [x] **(Carry-over from Phase 2 ✓)** Update `CLAUDE.md §3` map — refreshed `06-AGENTS.md` description ("observation-only detector toolkit; used by the Security agent"); added new `07-DEV-TEAM.md` row under Architecture & context. Also added §1 closing pointer ("Team architecture details … live in 07-DEV-TEAM.md; the keeper toolkit … is documented in 06-AGENTS.md") since both files now exist on disk; added §4 row for "Designing a dev-team agent / tool / sub-team".
- [x] Delete root `dev-team.md` (clean-folder rule satisfied — root now holds only platform-wide files).
- [x] Verify KB sync. *Result: ✓ KB sync OK — all CLAUDE.md pointers resolve, all KB docs indexed.*

**Improvements:**
- 07-DEV-TEAM.md is sizable (~440 lines, ~24kb). It's a reference doc loaded on-demand so size is acceptable, but it overlaps with `INSTRUCTIONS/01-AGENTS.md` + `INSTRUCTIONS/02-TOOLS.md` + `INSTRUCTIONS/03-MEMORY.md` + `INSTRUCTIONS/04-COSTS.md` + `GUIDES/invoke-the-team.md` (all created in Phase 7+). When those instructions docs land, 07-DEV-TEAM.md should shrink: keep §1 architecture + §2 roles + §11 tensions + §12 open questions; move §3 tool catalog → `INSTRUCTIONS/02-TOOLS.md`; §4 charter → `INSTRUCTIONS/01-AGENTS.md`; §5 memory → `INSTRUCTIONS/03-MEMORY.md`; §6 interface + §7 when-to-call → `GUIDES/invoke-the-team.md`; §8 cost + §9 model assignment → `INSTRUCTIONS/04-COSTS.md`. **This shrink is a Phase 10 sub-task, not Phase 3.**
- `06-AGENTS.md` now mentions `(v1)` annotations on five detectors that ship in Phase 6. The annotation creates a soft dependency: Phase 6 must implement exactly those five (or revise this doc). Captured here so Phase 6's agent doesn't have to rediscover the v1 set from `AUDIT.md § 6.5`.
- `07-DEV-TEAM.md` forward-references `PATTERNS/ast.md` (Phase 4), `INSTRUCTIONS/01..04` (Phase 7+), and `GUIDES/invoke-the-team.md` (Phase 10). All forward references are labelled `(Phase N)` in the prose so a cold reader knows they're pending. The verifier doesn't check inside-KB pointers (only `CLAUDE.md → KB`), so they're harmless until they land.
- The new doc places `incident_response_team` in §10 with a short spec; the actual implementation in Phase 9 will need to cross-reference this (and probably copy the spec into `dev-team/teams/incident_response_team.py` as a docstring). Note for Phase 9.

*No bundled proposal filed for Phase 3 — improvements are observational forward-references about Phase 7+ shrink + dependency notes, not actionable items requiring triage. Per `PATTERNS/proposals-and-improvements.md § 1`, no proposal file was filed.*

### Phase 4 — Deduplicate KB content + add AST-first principle ✅

- [x] **Deduplicate** per `AUDIT.md § 1.2` table — six recurring rules:
  - **Recurrence rule.** Canonical: `01-PHILOSOPHY.md § The recurrence rule`. Tightened the duplicate in `PATTERNS/project-execution.md § 2.7` (now an "operative reminder" with the threshold table + a `→` pointer).
  - **No silent errors.** Canonical: `01-PHILOSOPHY.md § No silent errors`. Added cross-reference at the top of `PATTERNS/logging.md § No # silent-ok` (the section earns its keep as the logging-side lens — keeps the `# silent-ok` retirement specifics; just names the canonical home). Did NOT touch `PATTERNS/testing.md § Auth boundary` — that section is a one-line auth-test rule, not a no-silent-errors duplicate (audit reference was inaccurate).
  - **Three-way sync.** Canonical: `01-PHILOSOPHY.md § Three-way sync`. Tightened `PATTERNS/proposals-and-improvements.md § 6` (now states the ordering in one sentence + `→` pointer).
  - **Apply-inline-then-delete.** Canonical: `PATTERNS/proposals-and-improvements.md § 4b`. The mention in `PATTERNS/project-execution.md § 0` is already a workflow-index name, not a re-statement — no change needed.
  - **End-of-work summary.** Canonical: `PATTERNS/proposals-and-improvements.md § 4c`. Tightened `CLAUDE.md §1 Honest summariser` to drop the list-shape detail (now: *"The Leader writes the end-of-work summary as the final synthesis pass — specialists return structured outputs (applied / deferred / verification), the Leader assembles. See §2 'End-of-work summary' for the operative form."*). The §2 entry remains as the operative form with a `→` pointer to the canonical.
  - **Replication-to-seed symmetry.** Canonical: `PATTERNS/project-execution.md § 3`. CLAUDE.md §2's version was already tightened in Phase 2; canonical is unchanged.
- [x] **Add AST-first principle** to `01-PHILOSOPHY.md` (new section after Module-scope imports). Includes the user's framing quoted verbatim, the `if-the-file-is-parsed-by-a-compiler-use-the-AST-tool` boundary rule, anti-patterns (sed-rename trap, multi-line regex trap, hand-edit-then-find-and-replace trap), companion-rule callouts (seed-first + no-quick-fixes), and forward-references to `PATTERNS/ast.md` + `07-DEV-TEAM.md § 3` + `06-AGENTS.md § Architecture`.
- [x] **Create `KNOWLEDGE-BASE/CONTEXT/PATTERNS/ast.md`** (188 lines). Toolchain (libcst, ast, tree-sitter for Python; ts-morph, @babel/parser, tree-sitter-typescript for TS; sqlglot for SQL; ruamel.yaml/tomlkit for YAML/TOML). Concrete recipes: rename-in-scope (Python + TypeScript), find-callers (Python read-only), find-pattern (Python — the libcst shape `check_silent_errors` v1 detector uses), apply-codemod (Python parallel + TypeScript). Anti-patterns table (sed across .py, multi-line regex, grep|xargs sed, AWK over Python, hand-edit + find-and-replace, regex.sub for imports). When regex IS the right tool (search-only, prose, logs, one-shots, sanity-checks). The boundary rule. Tools available to the dev team's agents (cross-ref to `07-DEV-TEAM.md § 3`).
- [x] **(Carry-over from Phase 2 ✓)** Added one-line pointer in `CLAUDE.md §2 Quality rules` for AST-first (between "No workarounds" and "No silent errors"). Pointer goes to both `01-PHILOSOPHY.md § AST-first` (the rule) and `PATTERNS/ast.md` (the operational reference) since the pair is genuinely two destinations a cold reader benefits from.
- [x] **(Carry-over from Phase 2 ✓)** Added `PATTERNS/ast.md` row to `CLAUDE.md §3` map under "Patterns".
- [x] **Update `KNOWLEDGE-BASE/INDEX.md`** with `PATTERNS/ast.md` — layout tree, by-topic table, by-situation table all updated.
- [x] Verify KB sync. *Result: ✓ KB sync OK — all CLAUDE.md pointers resolve, all KB docs indexed.*

**Improvements:**
- The audit's §1.2 table flagged `PATTERNS/testing.md § Auth boundary` as a no-silent-errors duplicate, but on inspection that section is a one-line auth-test rule. The actual silent-fail framing in testing.md is in the `MockSchemaError` section (about column-typo-returning-zero-rows in tests), which IS a no-silent-errors-shaped concern but is genuinely lens-specific. No change made; auditor confidence in the §1.2 row should be lower than the others. Note for the keeper's `check_kb_pointer_resolves` (v1 detector, Phase 6) — its scope is path resolution, not content-duplication detection, but a future detector pass could find these "claimed duplicate" but actually-not cases.
- The §2 entry for AST-first carries TWO `→` pointers (to `01-PHILOSOPHY.md` for the rule + to `PATTERNS/ast.md` for the toolchain). Other §2 rules carry one. The pair is intentional — a cold reader hitting "AST-first" needs both the principle (why) and the toolchain (how) immediately, and the two files are independent. Note for future CLAUDE.md hygiene reviews: if §2 grows another double-pointer rule, consider a stylistic convention split (rule pointer in line, toolchain pointer in a sub-bullet).
- `PATTERNS/ast.md` includes a code recipe for `FindTryExceptPass` that's specifically the shape Phase 6's `check_silent_errors` detector will use. The recipe is documentation, not implementation — Phase 6 reimplements with full edge-case handling. The recipe doubles as the v1 detector's spec by example. Captured here so Phase 6's agent doesn't have to re-derive.
- `01-PHILOSOPHY.md` is now 340 lines. Still the canonical home for behavioural rules so size is acceptable, but the recurrence-rule + replication-symmetry + AST-first triplet now spans about 100 lines combined. A future reorganisation could split philosophy into `01-PHILOSOPHY.md` (vocabulary + headline rules) + `01b-PRINCIPLES.md` (full prose for each rule). NOT a Phase 4 concern; flagged for any future "split philosophy" project.

*No bundled proposal filed for Phase 4 — improvements are observational forward-references about Phase 6 detector spec + future-doc-restructure thoughts, not actionable items requiring triage. Per `PATTERNS/proposals-and-improvements.md § 1`, no proposal file was filed.*

### Phase 5 — Populate `seed/` with the full reference stack (3-5 sessions)

- [ ] **Backend skeleton.** `seed/backend/framework/<pkg>/` — `app.py` (`create_product_app`), `settings.py` (`ProductSettings`, `BaseAppSettings`), `database.py` (`create_database_module`), `dependencies.py` (`create_dependencies`), `routers/` (health, team, notifications, ai_feedback bundled).
- [ ] **Backend lib.** `seed/backend/lib/<pkg>/` — `auth.py`, `roles.py`, `invitations.py`, `email/` (templates + digest), `notifications.py`, `responses.py`, `exceptions.py`, `middleware.py` (correlation IDs + request logging), `logging_config.py`, `credentials.py`, `llm/` (client + budget + consent), `testing/` (mock supabase, mock user, auth client).
- [ ] **Backend tests.** `seed/backend/lib/tests/` + `seed/backend/framework/tests/` — pure-python framework tests + lib tests.
- [ ] **Frontend skeleton.** `seed/frontend/framework/<pkg>/` — `app.tsx` (`createProductApp`), `layout.tsx` (`createProductLayout`), `infra.ts` (`createProductInfra`), `vite.config.factory.ts`, `vitest.config.factory.ts`.
- [ ] **Frontend lib.** `seed/frontend/lib/src/` — `api.ts`, `auth.ts`, `env.ts`, `stores.ts`, `hooks.ts`, `notifications.ts`, `roles.ts`, `sso.ts`, `utils.ts`, `components/` (SSOCallback, ErrorBoundary, AuthProvider), `design-system/` (AppShell, Sidebar, Header, NotificationBell, LoginForm, AcceptInvitePage, ForgotPasswordPage, PageSkeleton, InactivityWarning, HoverCard).
- [ ] **Frontend tests.** Hook tests + design-system component tests via vitest.
- [ ] **Update `04-SHARED-LIBRARY.md`** with the real catalog entries.
- [ ] **Update `02-LANDSCAPE.md`** with the reference stack table.
- [ ] **Update `05-INFRASTRUCTURE.md`** with concrete deploy details.
- [ ] **Editable installs** — `pip install -e seed/backend/lib seed/backend/framework`; npm/pnpm workspaces for frontend.

### Phase 6 — Implement `mcp/keeper/` minimal v1 detector set (AST-based)

- [ ] **Scaffold `mcp/keeper/`** — `pyproject.toml`, `src/keeper/`, `tests/`, `cli.py`.
- [ ] **Detector 1:** `check_silent_errors` (AST: `try/except` blocks with empty body or bare `pass` or silent `return None`/sentinel). Regression test (true positive + false positive).
- [ ] **Detector 2:** `check_no_self_monkeypatch` (AST: `monkeypatch.setattr` and `patch.object` with our-package targets; allowlist external boundaries). Regression test.
- [ ] **Detector 3:** `check_project_has_3a` (markdown: every `PROJECT.md` has §3a section). Regression test.
- [ ] **Detector 4:** `check_kb_pointer_resolves` (port from `verify-kb-sync.sh`). Regression test.
- [ ] **Detector 5:** `check_phase_state_consistency` (markdown: §6 ↔ §11 drift detection). Regression test.
- [ ] **Meta-detector:** `check_detector_has_regression_test` (introspects the keeper module). Regression test.
- [ ] **CLI:** `python -m keeper --validate` aggregating all detectors.
- [ ] **Pre-commit hook** extension — uncomment phase-state check block in `scripts/pre-commit`.

### Phase 7 — Scaffold `dev-team/` Python package

- [ ] **Project structure** — `pyproject.toml`, `src/dev_team/`, `tests/`, `evals/`, `configs/default.yaml`, `.env.example`.
- [ ] **Configs.** `configs/default.yaml` mapping `agent → {provider, model, ...}`. Anthropic-only initially (Opus on Leader/PM/Architect/Security/CodeReviewer; Sonnet on the rest).
- [ ] **Shared charter prompt** (`prompts/shared/charter.md`) — terse §2 behavioral rules, AST-first reference, language-time triggers.
- [ ] **Per-agent role prompts** (`prompts/agents/*.md`) — one per agent with mission + responsibilities + handoffs + per-agent KB allowlist + role-specific behavior.
- [ ] **Tools** — `tools/kb.py` (allowlist-scoped, section-anchored, size-capped), `tools/filesystem.py` (scoped read/write/edit), `tools/shell.py` (allowlisted commands per agent), `tools/keeper.py` (wraps `mcp/keeper`), `tools/recurrence.py`, `tools/proposals.py`, `tools/memory.py`, `tools/ast_python.py` (libcst), `tools/ast_typescript.py` (ts-morph).
- [ ] **Agents** — 11 specialist agents instantiating from configs + role prompts + tool subsets.
- [ ] **Teams** — `dev_team` (coordinate), `design_review_team` (collaborate), `code_review_team` (collaborate). `incident_response_team` deferred to Phase 9.
- [ ] **CLI entrypoint** — `python -m dev_team run "<task>"` with optional `--model-config`, `--project <slug>`.
- [ ] **Tests** with deterministic mock-LLM responses verifying orchestration topology + tool call shape + memory writes.
- [ ] **`KNOWLEDGE-BASE/INSTRUCTIONS/01-AGENTS.md`** — agno-specific design notes.
- [ ] **`KNOWLEDGE-BASE/INSTRUCTIONS/02-TOOLS.md`** — tool catalog with the per-agent matrix from `AUDIT.md § 5.2`.
- [ ] **`KNOWLEDGE-BASE/INSTRUCTIONS/04-COSTS.md`** — model tiering rationale + cost-per-task examples + prompt-caching notes.

### Phase 8 — Wire memory architecture

- [ ] **Schema design** — `dev-team/memory/project/<slug>/{state.sqlite, decisions.md, change-log.md}` + `dev-team/memory/agents/<agent>/<agent>.md`.
- [ ] **`tools/memory.py`** — read/write APIs with scope enforcement (project-shared vs. agent-self vs. cross-agent-read).
- [ ] **Three-way sync extension** — verify Markdown sources are referenced from KB or PROJECT.md to keep sync rule honest.
- [ ] **`KNOWLEDGE-BASE/INSTRUCTIONS/03-MEMORY.md`** — architecture, what each agent reads/writes, retention.
- [ ] **Tests** — concurrent-write contention, schema validation, agent scope isolation.

### Phase 9 — `incident_response_team` + eval harness

- [ ] **Spec `incident_response_team`** — collaborate mode; DevOps (lead) + Security + Backend; Frontend added situationally.
- [ ] **Implement** in `dev-team/src/dev_team/teams/incident_response_team.py`.
- [ ] **Eval harness** — `dev-team/evals/run.py` runs the same task across N model configs (default + codex-eval + gemini-eval), dumps timing/cost/output diffs.
- [ ] **Sample model configs** — `configs/codex-eval.yaml`, `configs/gemini-eval.yaml` as templates (commented out, since the user is Anthropic-only initially).
- [ ] **Document evals** in `KNOWLEDGE-BASE/INSTRUCTIONS/04-COSTS.md`.

### Phase 10 — Update root `README.md` + add `GUIDES/invoke-the-team.md`

- [ ] **Rewrite root `README.md`** — describe the methodology + the agno team + how to install + how to invoke + cost expectations.
- [ ] **Create `KNOWLEDGE-BASE/CONTEXT/GUIDES/invoke-the-team.md`** — when to call the team vs. Claude Code direct.
- [ ] **Update `KNOWLEDGE-BASE/INDEX.md`** with the new guide.
- [ ] Verify KB sync.

### Phase 11 — Final verification

- [ ] **Keeper full validate** — `python -m keeper --validate` clean.
- [ ] **KB sync** — verifier clean.
- [ ] **All test suites** — seed tests, keeper tests, dev-team tests all green.
- [ ] **End-to-end smoke test** — invoke dev-team via CLI on a tiny task; confirm Leader → Specialist → end-of-work-summary cycle works.
- [ ] **§6 ↔ §11 self-check** — every phase header `✅`, every sub-task `[x]`, `**Improvements:**` filled, §11 entries match.
- [ ] **Folder remains.** Per clean-folder rule, completed projects stay; only ephemerals get cleaned.

---

## 7. Open questions

The audit's §6 listed 10. User answered #1 (stack), #3 (memory backend defaults — implicit by silence), #4 (provider — dynamic config), #5 (keeper v1 — defaults accepted), #6 (migration — defaults accepted), #7 (Claude Code interface — defaults accepted), #8 (seed scope — fuller), #9 (incident-team membership — defaults accepted), #10 (keeper location — defaults accepted). One remains:

1. **`core/` — keep or drop.** Currently kept as `.gitkeep` placeholder per methodology. Needs answer before Phase 11 close (or before any first-product project lands).
   - **Recommendation:** keep. Cost is one empty folder; methodology already names the slot; future control-plane work has a home. Drop only if you decide the platform will never need a control-plane (rare).

---

## 8. Dependencies & blockers

- **Anthropic API key** — required from Phase 7 onward when the dev-team starts running.
- **Local Python 3.11+** + uv/pip — for `seed/backend/`, `mcp/keeper/`, `dev-team/`.
- **Local Node 20+** + pnpm/npm — for `seed/frontend/`.
- **Supabase project** (or compatible Postgres) — needed for end-to-end smoke tests in Phase 11; not strictly required for the seed framework tests (mocked).
- **`git init` not yet run** — `automations/` is not currently a git repo (per environment metadata). The pre-commit hook can't be installed until it is. Flag for the user.

---

## 9. Success criteria

- All 11 phases ✅ in §6.
- Repo layout matches §5 Architecture diagram exactly.
- Verifier (`bash scripts/verify-kb-sync.sh`) green.
- Keeper validate (`python -m keeper --validate`) clean.
- All test suites green: seed framework, seed lib, keeper, dev-team.
- A trivial end-to-end task invocation through the dev-team CLI returns a coherent end-of-work summary.
- Root cleanliness: only `CLAUDE.md`, `README.md`, `.gitignore`, top-level folders. No stray `.md` at root.

---

## 10. How to use this project

- **Single source of truth for progress.** Update as we work.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` immediately, save the file. Don't batch.
- **Phase-by-phase by default.** Execute one phase, pause, wait for "continue" / "next phase" / "do phase N". Override with explicit throughput instructions like *"ram through 1-3."*
- **Revise the project when understanding changes.** Rewrite phases, log the revision in §11.
- **Apply-inline-then-delete + end-of-work summary** at every phase close.

**Verification commands (copy-paste ready):**

```bash
# KB sync
bash scripts/verify-kb-sync.sh

# Keeper validate (after Phase 6)
python -m keeper --validate

# Seed framework tests (after Phase 5)
cd seed/backend/framework && pytest -q
cd seed/backend/lib       && pytest -q
cd seed/frontend/framework && npm test
cd seed/frontend/lib      && npm test

# Dev-team tests (after Phase 7)
cd dev-team && pytest -q

# Smoke test (after Phase 11)
python -m dev_team run "Write a one-paragraph hello"
```

**If something surprises you** during execution (line numbers moved, tests already red, file in unexpected state): note in §11, keep going if small (per *expand loudly*), escalate to a new project if the scope widens.

**Drafting agent reachable?** YES — same session as Phase 0 audit. The user may `/clear` between phases; the implementing agent reads `AUDIT.md` + this `PROJECT.md` to inherit full context.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-30 | Phase 0 audit complete — `AUDIT.md` produced. End-to-end audit of `noctus-starter/` + `dev-team.md`; seven tension resolutions, end-state structure, 11-phase plan. | claude (opus-4-7) |
| 2026-04-30 | Phase 1 in progress — hoisted `noctus-starter/` to repo root; KB sync verified green; project folder scaffolded; this `PROJECT.md` created from template. | claude (opus-4-7) |
| 2026-04-30 | **Phase 1 complete ✅** — `AUDIT.md` moved to `projects/methodology-restructure/AUDIT.md`; root layout confirmed; improvements captured (no bundled proposal — observational items only). Verification: `bash scripts/verify-kb-sync.sh` green. | claude (opus-4-7) |
| 2026-04-30 | **Phase 2 complete ✅** — Rewrote `CLAUDE.md §1` to multi-agent-team framing per `AUDIT.md § 3.1` + § 3.3 (Leader synthesises, specialists return structured outputs to Leader, behavioral rules in §2 apply to every agent). Tightened §2 — replaced repeated rule prose with one-line + threshold/litmus + KB pointer. CLAUDE.md ~22kb → ~19kb (-14% overall; §2 alone hit close to the -30% target). Two Phase 2 sub-tasks deferred to Phase 3 / Phase 4 per user direction (§3 map pointers + §2 AST-first line — those targets don't exist on disk yet; verifier would block). Verification: `bash scripts/verify-kb-sync.sh` green. | claude (opus-4-7) |
| 2026-04-30 | **Phase 3 complete ✅** — Rewrote `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` (~50% kept from original: detector inventory, recurrence scans, proposal protocol, CLI surface, architecture; orchestration framing replaced with "two distinct concepts, two names" + agent-by-agent keeper consumption map; added `check_kb_pointer_resolves` (v1) detector). Created `KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md` (~440 lines, ~24kb) absorbing `dev-team.md` with the seven tension resolutions, v0.2 answers, 15-tool catalog, hybrid memory architecture, CLI/MCP interface spec, when-to-call thresholds, cost model, provider-agnostic model assignment, `incident_response_team` design. Updated `KNOWLEDGE-BASE/INDEX.md` (layout tree + both topic tables). Carry-over from Phase 2: updated `CLAUDE.md §1` closing pointer, `§3` map (refreshed 06-AGENTS.md description, added 07-DEV-TEAM.md row), `§4` situation table. Deleted root `dev-team.md` (clean-folder rule satisfied). Verification: `bash scripts/verify-kb-sync.sh` green; root listing confirms only platform-wide files (`CLAUDE.md`, `README.md`, `core/`, `KNOWLEDGE-BASE/`, `mcp/`, `products/`, `projects/`, `scripts/`, `seed/`, `templates/`). | claude (opus-4-7) |
| 2026-04-30 | **Phase 4 complete ✅** — Deduplicated five of the six rules in `AUDIT.md § 1.2` (the sixth — `PATTERNS/testing.md § Auth boundary` — turned out to not be a duplicate; rationale captured in Phase 4 improvements). Tightened `PATTERNS/project-execution.md § 2.7` (recurrence rule), `PATTERNS/proposals-and-improvements.md § 6` (three-way sync ordering), `PATTERNS/logging.md § No # silent-ok` (added cross-ref), `CLAUDE.md §1 Honest summariser` (dropped list-shape detail; preserved Leader-synthesis framing + pointer to §2). Added AST-first principle as a new section in `01-PHILOSOPHY.md` (between Module-scope imports and Three-way sync) — quotes the user's framing verbatim, names the boundary rule, anti-patterns, companion rules, forward-references to PATTERNS/ast.md + 07-DEV-TEAM.md + 06-AGENTS.md. Created `KNOWLEDGE-BASE/CONTEXT/PATTERNS/ast.md` (188 lines) with toolchain, recipes (rename / find-callers / find-pattern / codemod for both Python + TypeScript), anti-patterns table, regex-IS-right cases. Carry-over from Phase 2: added `CLAUDE.md §2` AST-first rule (under Quality rules; double-pointer to philosophy + ast.md), `§3` map ast row under Patterns, `§4` situation row. Updated `KNOWLEDGE-BASE/INDEX.md` with PATTERNS/ast.md (layout tree + both topic tables). Verification: `bash scripts/verify-kb-sync.sh` green. | claude (opus-4-7) |
