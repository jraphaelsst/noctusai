# CLAUDE.md · v2.0

<!--
  Version:   2.0
  Date:      2026-04-18
  Author:    Raphael (joaoraphaelsst@gmail.com) — product owner, platform architect
  AI coauthor: Claude Opus 4.7 (1M context) — iterative collaboration
  Shift:     v1 was directive-only. v2 is instructive — each rule now says
             *what*, *what not*, *why*, and *where to deepen*.
  Enforced:  scripts/pre-commit verifies every pointer resolves before any commit.
-->

> **What this file is.** Claude's **outer map**. It ships with every session to
> establish (a) the behavioral rules Claude obeys every turn and (b) where to
> jump in `KNOWLEDGE-BASE/` for deeper context. **This file itself holds no specs
> or technical depth** — specs live in the KB. If you find yourself writing an
> architecture paragraph here, it belongs in `KNOWLEDGE-BASE/CONTEXT/` with a
> pointer here.
>
> **What this file is NOT.** A tutorial, a changelog, a spec sheet, or a
> reference manual. It's a thin router with behavioral rules on top.
>
> When you can't find something, open **`KNOWLEDGE-BASE/INDEX.md`** — the
> authoritative catalog of every KB doc.

---

## 0 · How this file is organized

This file has four parts. Each part has a single, narrow job.

| Section | What it does | How to use it |
|---|---|---|
| **§1 Engineering Philosophy** | The behavioral rules that govern every decision. | Read every session. When a rule applies, it wins. |
| **§2 The Map** | Pointers into `KNOWLEDGE-BASE/` grouped by topic. | Open the linked file *on-demand* when depth is needed — never pre-load. |
| **§3 When to read what** | Task → "open this first" lookup. | Before starting work, scan the table to find your entry point. |
| **§4 Sync rule** | How this file and the KB stay aligned. | Enforced automatically by the pre-commit hook; manual runs listed for debugging. |

Each rule and pointer is instructive: we say *what to do*, *what not to do*, *why it matters*, and (where useful) *where to go for depth*.

---

## 1 · Engineering Philosophy

Behavioral rules. Short on purpose. For the long-form reasoning — history, incidents that produced the rule, edge cases — read **`KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`**.

- **Seed first. Always.** Every product inherits its backbone from `seed/` — auth, routing, layout, DB clients, health, team management, notifications, page status. Don't copy-paste structural code; don't re-implement what the framework already gives you. *Structure centralized means every fix propagates to every product in one edit.* → `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`
- **MCP toolkit reviews after every change (observation-only).** After modifying code, run `python mcp/noctusai/cli.py --review` on the affected product. The review pass detects seed-compliance issues deterministically and asks an LLM (OpenAI, via `OPENAI_API_KEY`) to author a proposal for each in `mcp/noctusai/proposals/`. **It NEVER modifies code** — every decision goes through explicit human review. *No code ships with unreviewed violations.* Loop: change → review → triage proposals → apply manually → commit. The old auto-fix `--heal` flow was retired because deterministic text rewrites could corrupt code and the string-match checks rotted as the seed evolved. → `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`
- **No incomplete commits.** Never commit a product with mismatched maturity between backend and frontend. "Scaffolded" is not "complete." If one side is real and the other is a placeholder, stop and flag it. *A commit that looks done but isn't becomes tech debt the moment it lands.*
- **No quick fixes.** Never patch symptoms. If a fix touches multiple products for the same reason, you're fixing the wrong level. Go one layer up — the real fix lives in the seed, a shared lib, or a config — and it propagates automatically. *Thirty minutes on the root beats five minutes on a patch that generates future work.*
- **No workarounds.** Use the real API, SDK, or framework. No monkeypatches, shims, or hacks. *If the framework can't do it, extend the framework — don't bolt onto the product.*
- **DRY.** Three similar blocks is a pattern — extract it. Two is a coincidence. Single authoritative source for every piece of logic, every config, every doc.
- **Componentize everything.** Before writing anything, check **`KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md`** — it might already exist. If another product will need it, build it shared from the start. *Duplicate code is debt; shared components are assets.*
- **Module-scope imports.** Python imports go at the top of the file. Don't defer imports into function bodies unless solving a documented circular dependency. *Top-level imports fail fast at startup; deferred imports hide bugs until a specific path runs.*
- **Projects are living documents — and planners interrogate before designing.** Every `*-PROJECT.md` is a guideline that evolves with execution (rewrite phases, fold in optimizations, update the Change Log). *Terminology note:* NoctusAI uses *project* for what other teams call a "plan"; `*-PLAN.md` is deprecated for new files (legacy files may still exist until renamed). Before drafting or revising one, **act as a questionnaire** — ask the user clarifying questions, confirm constraints, surface edge cases. Never assume. **Always start a new project by copying `templates/PROJECT-TEMPLATE.md`**; fill placeholders, delete sections that don't apply. Commit project changes with the code. **During execution, tick tasks live** (`- [ ]` → `- [x]`, saved immediately — never batched), because the user watches the project file as a live dashboard. **Cadence is phase-by-phase by default**: execute one phase, then pause and wait for the user to say "continue" / "next phase". The user overrides with throughput instructions like "ram through 1-3" or "do all backend phases". **Phase headers carry a status icon** (METAS-PROJECT convention — see `products/erp-imobiliario/METAS-PLAN.md` pending rename): no icon = pending, `⏳` = in progress/partial, `✅` = complete, `❌` = blocked/failed. Flip to `✅` only when every sub-task inside is ticked. **Improvement flow is capture-then-synthesize**: (capture) during step implementation, drop quick specific bullets into the phase's `**Improvements:**` block — no ceremony, in-the-act notes; (synthesize) at end of phase, BEFORE flipping the header to `✅`, read the entire block, consider the whole project context, and file **ONE bundled proposal per phase** via `noctusai_file_proposal(project="<slug>", ...)` — the proposal lands in `mcp/noctusai/proposals/<project-slug>/` with `Origin: project:<slug>:phase-<N>` and filled `Context`, `Situation`, `Proposed Solution` (bundled improvements as independently-executable items), `Effects`. Not one proposal per improvement — ONE per phase, bundling them. Each bundled improvement retains individual execution (reviewer schedules separately). Then flip header to `✅`, run `python mcp/noctusai/cli.py --improvements <project.md>` to regenerate `improvements.md`. → `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md` (Projects are living) + `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` (two-system protocol)
- **Gamification is subtle.** Rankings, points, progress bars — always discrete; always with a ⓘ info icon explaining the formula; always tied to real business activity (never "logged in today"-style rewards). → `KNOWLEDGE-BASE/CONTEXT/07-GAMIFICATION.md`
- **Docs stay in sync — and land KB-first, CLAUDE.md second.** Any commit that changes behavior also updates `CLAUDE.md`, `KNOWLEDGE-BASE/INDEX.md`, the relevant topical KB file, and (if tooling changed) `mcp/noctusai/README.md`. **Ordering matters:** when a rule changes, land the KB changes first (topical KB file + INDEX.md entry), *then* touch CLAUDE.md with the short rule + pointer. Never the reverse — CLAUDE.md is the pointer layer and pointing into KB content that doesn't yet exist strands the pointer. Tiny typo-only CLAUDE.md fixes are exempt. *The `verify-kb-sync.sh` pre-commit hook catches dangling pointers but cannot catch "wrote CLAUDE.md first then backfilled the KB" — that discipline is the agent's.* → `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md` (Docs stay in sync)
- **MCP migrations mirror the file.** When you apply DDL via the Supabase MCP (`apply_migration` or `execute_sql`), the same SQL **must** exist as a numbered migration file in `products/<name>/backend/migrations/NNN_<name>.sql` — commit both together. *The database is mutable state; the migration files are the authoritative replay log.* If the file drifts from what was applied, a fresh clone cannot reproduce the schema. Write the file first, then apply via MCP (or if you iterated live, back-port every change into a new file before committing). → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`
- **Supabase MCP is the agent's tool — use it proactively.** When a task needs DB access (apply a migration, audit a schema, verify RLS, seed or inspect data), the agent executes it directly through `mcp__claude_ai_Supabase__*`. **Never** ask the user to paste SQL into the Supabase editor or grant one-off permission — blanket approval stands for this repo. Still use `apply_migration` for DDL (per the rule above); `execute_sql` is for read-only inspection only.
- **`CLAUDE.md` vs `KNOWLEDGE-BASE/` — the token budget rule.** This file is loaded every turn; keep it lean. The KB is loaded on-demand; put depth there. *The split exists to save tokens each iteration without losing knowledge — if CLAUDE.md grows, context degrades.*
- **Every product has `README.md` + `MASTER-PROMPT.md`.** README for humans browsing the repo; MASTER-PROMPT for agents building features. Both are mandatory from day one of a new product. → `KNOWLEDGE-BASE/CONTEXT/GUIDES/new-product.md`
- **LGPD-first, always.** Whenever code touches personal data (identity, financial, clinical, behavioral, derived embeddings, …), the LGPD lens is the first lens — before functionality, before performance, before UX. Clinical text is Art. 11 sensitive data; it never leaves the Therapy schema without a documented basis, never hits a response cache. When in doubt about an approach, call `noctusai_lgpd_flag(...)` — it records the concern in `LGPD-WARNINGS.md` and notifies the user; **it does not block.** The flag is a checklist item: it gets ticked when the concern is resolved. → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`

---

## 2 · The Map

Pointers into `KNOWLEDGE-BASE/`. Open the file *on-demand* — never pre-load. If nothing here matches, open `KNOWLEDGE-BASE/INDEX.md` for the complete catalog.

### Architecture & context — "what the platform is"
- **Product landscape** (products, schemas, ports, stack) → `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`
- **Seed framework** (factories, layer split, how products inherit) → `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`
- **Shared library catalog** (check before building anything) → `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md`
- **Infrastructure** (ports, deploy, self-hosted services) → `KNOWLEDGE-BASE/CONTEXT/05-INFRASTRUCTURE.md`
- **MCP dev toolkit** (heal loop, proposals, CLI commands) → `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`
- **Gamification philosophy** (subtle rankings, ⓘ icons, Metas as reference impl) → `KNOWLEDGE-BASE/CONTEXT/07-GAMIFICATION.md`

### Patterns — "how we write it"
Read these when writing or reviewing code in the relevant area. They capture conventions enforced across products.
- **LLM access** (multi-provider via `noctusai_lib.llm` — never `from openai import`; `cache=False` for clinical text) → `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` § `llm/`
- **Backend patterns** (auth, SSO, RLS, N+1, service layer) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md`
- **Frontend patterns** (TanStack Query, hooks-per-entity, mobile-first) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend.md`
- **Testing** (three-layer discipline + auth boundary) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md`
- **Database & RLS** (subquery `auth.uid()`, `search_path`, policy templates) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`
- **Environment / `.env`** (single root, VITE_ security rule, CORS_ORIGINS) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md`
- **Notifications** (proxy, shape, shared `NotificationBell`) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/notifications.md`
- **Shared-library conventions** (privatize / absorb / rename rules, catalog tool) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/shared-library-conventions.md`
- **Project execution** (phase-header checkboxes, live ticking, improvements block, retrospective tool) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`
- **Proposals & improvements** (two-system protocol, ONE bundled proposal per phase in `proposals/<project-slug>/`, PROPOSAL-TEMPLATE.md fields, promote boundary) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md`
- **LGPD awareness** (keeper principle, the five questions, `noctusai_lgpd_flag` tool) → `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`

### Guides — "how to do a task"
Step-by-step procedures for specific operational tasks.
- **First-time setup** (clone → install → run) → `KNOWLEDGE-BASE/CONTEXT/GUIDES/setup.md`
- **Creating a new product** (mandatory files + checklist) → `KNOWLEDGE-BASE/CONTEXT/GUIDES/new-product.md`

### Per-product details
Deep, product-specific knowledge. Open only the product you're working on.
- Backend specs → `KNOWLEDGE-BASE/CONTEXT/backend/{01-CORE, 02-ERP, 03-PF, 04-DATABASE, 05-AI-FEATURES, 06-THERAPY, 07-AUTH-SECURITY, 08-DAILY-LIFE}.md`
- Frontend specs → `KNOWLEDGE-BASE/CONTEXT/frontend/{01-CORE, 02-ERP, 03-PF, 04-THERAPY}.md`

### Agent / skill / workflow design
Use these when designing new agents, skills, or MCP integrations (not when building product features).
- Entry point → `KNOWLEDGE-BASE/INSTRUCTIONS/00-MASTER.md`

### Two maps, two audiences
- **This file** (`CLAUDE.md`) — outer map, every session, lean.
- **`KNOWLEDGE-BASE/INDEX.md`** — inner map, the KB's self-description with by-topic and by-situation tables.

---

## 3 · When to read what

Quick lookup: *before you start work*, find your situation and open the file listed.

| Situation | Start here |
|---|---|
| Fresh session, need orientation | `KNOWLEDGE-BASE/AGENT-CONTEXT.md` + `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` |
| Writing backend code | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend.md` + product-specific `CONTEXT/backend/0X-*.md` |
| Writing frontend code | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend.md` + product-specific `CONTEXT/frontend/0X-*.md` |
| Writing a migration | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md` + `KNOWLEDGE-BASE/CONTEXT/backend/04-DATABASE.md` |
| Adding a shared component | `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` (check first — it might exist) |
| Creating a new product | `KNOWLEDGE-BASE/CONTEXT/GUIDES/new-product.md` + `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md` |
| Starting a new project | Copy `templates/PROJECT-TEMPLATE.md`. Never hand-roll. |
| Changing env vars | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md` |
| Writing tests | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md` |
| Touching gamified UI | `KNOWLEDGE-BASE/CONTEXT/07-GAMIFICATION.md` |
| Designing an agent / MCP / skill | `KNOWLEDGE-BASE/INSTRUCTIONS/00-MASTER.md` |
| Anything not listed | `KNOWLEDGE-BASE/INDEX.md` |

---

## 4 · Sync rule

This file and `KNOWLEDGE-BASE/INDEX.md` must stay in sync — when you add, rename, or delete any KB file or folder, both get updated.

**Pre-commit hook enforces it automatically** (`scripts/pre-commit` → installed by `scripts/install-hooks.sh`). On every commit the hook:

1. Syncs `products/seed/` → `templates/product-seed/` if staged.
2. Runs `scripts/update-kb-counts.py` — regenerates auto-derived count blocks (product inventory, schema tables, MCP tools) and stages any updated docs.
3. Runs `scripts/verify-kb-sync.sh` — **blocks the commit** if any pointer in this file doesn't resolve, or if any KB doc is missing from `INDEX.md`.

Manual runs (for debugging or CI):
- `bash scripts/verify-kb-sync.sh`
- `python scripts/update-kb-counts.py [--check]`
- `python mcp/noctusai/cli.py --verify-kb-sync`

To install hooks in a fresh clone: `bash scripts/install-hooks.sh` (or the full setup: `bash scripts/setup.sh`).

Bypass the hook (rarely correct): `git commit --no-verify`.

---

<!-- Version history
  2.0 (2026-04-18) — instructive rewrite: each rule now carries what/what-not/why/deepen.
                     Added §0 "How this file is organized" + credits metadata.
  1.0 (2026-04-18) — pointer/map split: specs moved to KNOWLEDGE-BASE/, CLAUDE.md became thin router.
  0.x  — legacy: everything in one long file; spec + rules conflated.
-->
