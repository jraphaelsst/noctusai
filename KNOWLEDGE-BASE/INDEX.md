# Knowledge Base — Index

> **Purpose:** This is the structural catalog of the NoctusAI Knowledge Base. Agents and developers use it to answer: *"where is X?"*.
> For *"what is this place?"* — read `AGENT-CONTEXT.md` instead (prose onboarding).
>
> **Sync rule:** Kept in sync with `CLAUDE.md`'s map section. If you add, rename, or delete a file in the KB, update both.

---

## Layout

```
KNOWLEDGE-BASE/
├── INDEX.md                ← this file (the catalog)
├── AGENT-CONTEXT.md        ← "what is this place" (onboarding prose)
├── CONTEXT/                ← deep technical + architectural context
│   ├── 01-PHILOSOPHY.md    ← engineering principles (elaborated)
│   ├── 02-LANDSCAPE.md     ← products, schemas, ports, stack
│   ├── 03-SEED-ARCHITECTURE.md  ← the spine
│   ├── 04-SHARED-LIBRARY.md     ← reusable components catalog
│   ├── 05-INFRASTRUCTURE.md     ← deployment + self-hosted services
│   ├── 06-AGENTS.md        ← MCP dev toolkit (Claude-side agents)
│   ├── 07-GAMIFICATION.md  ← cross-product UX philosophy
│   ├── PATTERNS/           ← how-to technical patterns
│   │   ├── backend.md
│   │   ├── frontend.md
│   │   ├── testing.md
│   │   ├── database-rls.md
│   │   ├── environment.md
│   │   ├── notifications.md
│   │   ├── shared-library-conventions.md
│   │   ├── project-execution.md
│   │   ├── proposals-and-improvements.md  ← two-system protocol (improvements per-project, ONE bundled proposal per phase)
│   │   ├── lgpd.md
│   │   ├── llm-usage.md       ← Phase 15 DB-backed usage sink + admin endpoints
│   │   ├── logging.md         ← level guide, no-`# silent-ok` rule, correlation IDs
│   │   ├── seed-lib-layout.md ← 6-layer model + decision tree
│   │   ├── agent-reading-discipline.md ← narrow-read first; Explore delegation (forthcoming)
│   │   ├── webhook-signatures.md ← four shapes (Hub-Signature / hex HMAC / Svix / Stripe SDK); helpers in noctusai_lib.security.webhook_signatures
│   │   ├── accept-with-rationale.md ← pattern definition + durable catalog of every active accept-with-rationale on the platform
│   │   ├── ast.md                  ← AST-first toolchain (libcst / ts-morph / tree-sitter) + recipes + anti-patterns + boundary rule
│   │   ├── mcp-tool-conventions.md ← 3-segment dotted naming + Pydantic In/Out + hierarchical registration + lazy context + MCP-first principle
│   │   └── template-workspace.md   ← sibling consume-only workspace; "templates cannot modify noc" rule + 3-layer defense + promotion manifest
│   ├── GUIDES/             ← task-oriented guides
│   │   ├── setup.md
│   │   ├── new-product.md
│   │   └── seed-first-design.md
│   ├── backend/            ← per-product backend details
│   │   ├── 01-CORE.md
│   │   ├── 02-ERP.md
│   │   ├── 03-PF.md
│   │   ├── 04-DATABASE.md
│   │   ├── 05-AI-FEATURES.md
│   │   ├── 06-THERAPY.md
│   │   ├── 07-AUTH-SECURITY.md
│   │   └── 08-DAILY-LIFE.md
│   └── frontend/           ← per-product frontend details
│       ├── 01-CORE.md
│       ├── 02-ERP.md
│       ├── 03-PF.md
│       └── 04-THERAPY.md
├── INSTRUCTIONS/           ← agent development / skill design
│   ├── 00-MASTER.md
│   ├── 01-SKILLS.md
│   ├── 02-MCP.md
│   ├── 03-AGENTIC-WORKFLOWS.md
│   ├── 04-DESIGN-PHASES.md
│   ├── 05-TESTING-EVALS.md
│   ├── 06-TECH-STACK.md
│   └── 07-TEMPLATES.md
├── EVALS/                  ← eval config + cases
├── SKILLS/                 ← skill definitions
├── WORKFLOWS/              ← multi-step workflows
└── MCP-SERVERS/            ← MCP server references
```

---

## By topic — "where do I find…"

| Topic | File |
|---|---|
| Engineering rules (seed-first, no quick fixes, DRY, etc.) | `CONTEXT/01-PHILOSOPHY.md` |
| Product landscape (names, ports, schemas, stack) | `CONTEXT/02-LANDSCAPE.md` |
| Seed framework APIs (`create_product_app`, `createProductApp`, etc.) | `CONTEXT/03-SEED-ARCHITECTURE.md` |
| Reusable components catalog (before writing anything) | `CONTEXT/04-SHARED-LIBRARY.md` |
| Infrastructure (ports, Docker, WAHA, LiveKit, n8n) | `CONTEXT/05-INFRASTRUCTURE.md` |
| MCP dev toolkit (heal loop, proposals, tools) | `CONTEXT/06-AGENTS.md` |
| Gamification philosophy (ranks, points, subtle UX) | `CONTEXT/07-GAMIFICATION.md` |
| Backend patterns (auth, SSO, RLS, N+1, services) | `CONTEXT/PATTERNS/backend.md` |
| Frontend patterns (mobile-first, TanStack Query, hooks) | `CONTEXT/PATTERNS/frontend.md` |
| Testing discipline (3 layers, mocking, auth boundary) | `CONTEXT/PATTERNS/testing.md` |
| RLS + DB rules (`auth.uid()` subquery, search_path) | `CONTEXT/PATTERNS/database-rls.md` |
| Environment vars (single `.env`, VITE_ prefix, CORS) | `CONTEXT/PATTERNS/environment.md` |
| Notifications (`public.notifications`, field mapping) | `CONTEXT/PATTERNS/notifications.md` |
| Shared-library conventions (privatize / absorb / rename; catalog tool) | `CONTEXT/PATTERNS/shared-library-conventions.md` |
| Project execution (phase-header ticks, improvements block, improvements.md retrospective tool) | `CONTEXT/PATTERNS/project-execution.md` |
| Proposals & improvements (two systems — per-project folders, ONE bundled proposal per phase, promote boundary) | `CONTEXT/PATTERNS/proposals-and-improvements.md` |
| LGPD awareness (keeper principle, the five questions, noctusai_lgpd_flag tool) | `CONTEXT/PATTERNS/lgpd.md` |
| LLM usage tracking (SupabaseUsageSink, /api/llm/usage, cost estimation, RLS scoping) | `CONTEXT/PATTERNS/llm-usage.md` |
| Logging convention (when-to-log, level guide, no-`# silent-ok` rule, correlation IDs) | `CONTEXT/PATTERNS/logging.md` |
| Seed-lib layout (6 layers — primitives/config/testing/integrations/domain/api — where to put new helpers, where to find existing ones) | `CONTEXT/PATTERNS/seed-lib-layout.md` |
| Agent reading & research discipline (narrow-read first; Explore delegation rule forthcoming) | `CONTEXT/PATTERNS/agent-reading-discipline.md` |
| Webhook signature verification (the four shapes: Hub-Signature / hex HMAC / Svix / Stripe SDK; constant-time compare; helper module in `noctusai_lib.security.webhook_signatures`) | `CONTEXT/PATTERNS/webhook-signatures.md` |
| Accept-with-rationale catalog (durable home for every legitimate divergence on the platform — survives project folder deletion; how to add / retire entries) | `CONTEXT/PATTERNS/accept-with-rationale.md` |
| AST-driven code edits (libcst for Python / ts-morph for TypeScript / tree-sitter cross-language; recipes for rename / find-callers / codemods; anti-patterns; boundary rule) | `CONTEXT/PATTERNS/ast.md` |
| MCP tool conventions (3-segment dotted naming `noctus.dev.* / noctus.business.* / google.* / openai.*`, Pydantic In/Out per tool, hierarchical registration, lazy `NoctusContext` for business-logic tools, settings shim, MCP-first principle) | `CONTEXT/PATTERNS/mcp-tool-conventions.md` |
| Template workspace (sibling-of-noc consume-only workspace; symlinks all 8 noc surfaces; pre-commit hook + chmod + KB rule = three-layer "templates can't modify noc" defense; promotion manifest for additions; bootstrap script + workspace.py resolver + `noctusai_promote_from_template` MCP tool) | `CONTEXT/PATTERNS/template-workspace.md` |
| First clone + starting servers | `CONTEXT/GUIDES/setup.md` |
| Creating a new product | `CONTEXT/GUIDES/new-product.md` |
| Seed-first design checklist (cross-product projects — REQUIRED at authoring time) | `CONTEXT/GUIDES/seed-first-design.md` |
| Core backend (routers, services, tables) | `CONTEXT/backend/01-CORE.md` |
| ERP backend | `CONTEXT/backend/02-ERP.md` |
| PF backend | `CONTEXT/backend/03-PF.md` |
| Database inventory per schema | `CONTEXT/backend/04-DATABASE.md` |
| AI features (OpenAI, embeddings, summaries) | `CONTEXT/backend/05-AI-FEATURES.md` |
| Therapy backend | `CONTEXT/backend/06-THERAPY.md` |
| Auth + security deep-dive | `CONTEXT/backend/07-AUTH-SECURITY.md` |
| Daily Life backend | `CONTEXT/backend/08-DAILY-LIFE.md` |
| Core frontend | `CONTEXT/frontend/01-CORE.md` |
| ERP frontend | `CONTEXT/frontend/02-ERP.md` |
| PF frontend | `CONTEXT/frontend/03-PF.md` |
| Therapy frontend | `CONTEXT/frontend/04-THERAPY.md` |
| Skill design (composable agent units) | `INSTRUCTIONS/01-SKILLS.md` |
| MCP integration patterns | `INSTRUCTIONS/02-MCP.md` |
| Agentic workflows | `INSTRUCTIONS/03-AGENTIC-WORKFLOWS.md` |
| Eval strategy | `INSTRUCTIONS/05-TESTING-EVALS.md` |
| Tech stack details | `INSTRUCTIONS/06-TECH-STACK.md` |
| Artifact templates | `INSTRUCTIONS/07-TEMPLATES.md` |

---

## By situation — "when I'm doing X, read Y"

| Situation | Start here |
|---|---|
| Fresh agent, zero context | `AGENT-CONTEXT.md` → `CONTEXT/01-PHILOSOPHY.md` → `CONTEXT/02-LANDSCAPE.md` |
| About to write new backend code | `CONTEXT/PATTERNS/backend.md` + product-specific `CONTEXT/backend/0X-*.md` |
| About to write new frontend code | `CONTEXT/PATTERNS/frontend.md` + product-specific `CONTEXT/frontend/0X-*.md` |
| Touching any DB migration | `CONTEXT/PATTERNS/database-rls.md` + `CONTEXT/backend/04-DATABASE.md` |
| Adding a new product | `CONTEXT/GUIDES/new-product.md` + `CONTEXT/03-SEED-ARCHITECTURE.md` |
| Adding a shared component | `CONTEXT/04-SHARED-LIBRARY.md` (check existing first) |
| Working on tests | `CONTEXT/PATTERNS/testing.md` |
| Adding a `try/except` (production code) | `CONTEXT/PATTERNS/logging.md` (level guide, the no-`# silent-ok` rule) |
| Adding a new keeper detector | `CONTEXT/PATTERNS/testing.md § Regression-test-the-detector` + `CONTEXT/06-AGENTS.md § Detectors` |
| Adding a helper to seed lib (deciding which layer it lives in) | `CONTEXT/PATTERNS/seed-lib-layout.md § Where to put a new helper` |
| Looking for an existing seed-lib helper | `CONTEXT/PATTERNS/seed-lib-layout.md § Where to look` + `CONTEXT/04-SHARED-LIBRARY.md` (catalog) |
| Working on env / deployment | `CONTEXT/PATTERNS/environment.md` + `CONTEXT/05-INFRASTRUCTURE.md` |
| Touching UI with performance data / gamification | `CONTEXT/07-GAMIFICATION.md` |
| Reading a large/unfamiliar file (default — narrow-read first) | `CONTEXT/PATTERNS/agent-reading-discipline.md § Narrow-read first` |
| About to edit `.py` / `.ts` / `.tsx` source — rename, codemod, find-callers, anything beyond a 1-line targeted edit | `CONTEXT/PATTERNS/ast.md` (AST-first; never sed/regex on source) |
| Adding any helper or function an agent might want to call (Claude Code / future bot / future product agent) | `CONTEXT/01-PHILOSOPHY.md § MCP-first` (default surface is `mcp/noctusai/`) |
| Designing a new agent / skill / MCP | `INSTRUCTIONS/00-MASTER.md` |

---

## Sync with `CLAUDE.md`

`CLAUDE.md` at the repo root is the **outer map** — slim, loaded every Claude session, contains behavioral rules + pointers into this KB.

This `INDEX.md` is the **inner map** — the KB's own authoritative self-description. Kept in sync with CLAUDE.md's map section.

Sync enforcement (pick any/all):
1. **Rule** — when you change `CLAUDE.md`'s map or any KB file/folder, update both this INDEX and CLAUDE.md. Documented in `CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`.
2. **Script** — `scripts/verify-kb-sync.sh` validates that CLAUDE.md pointers resolve to real files and all KB files are indexed. Run pre-commit.
3. **MCP tool** — `python mcp/noctusai/cli.py verify-kb-sync` (same check, integrated into the heal loop).
