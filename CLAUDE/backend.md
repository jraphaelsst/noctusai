# CLAUDE/backend.md — backend behavioral rules

> **Loading discipline.** This file is not auto-loaded. Read it when starting backend code work — the §3 routing table in `CLAUDE.md` is the canonical signal. Sibling of `CLAUDE.md`, NOT depth (depth lives in `KNOWLEDGE-BASE/`).

## Rules

- **Module-scope imports.** Python imports at the top of the file. Don't defer into function bodies unless solving a documented circular dependency. → `KB § 01-PHILOSOPHY.md § Module-scope imports`
- **FastAPI dep factories defer config to request time.** Boot-order trap: routers decorate at import-time but `create_product_app(...)` wires `configure_X_module(...)` later. A fail-fast factory crashes router imports. Pattern: module-level slots default `None`; `configure_X_module(...)` populates them; factory returns dep without checking; dep reads slots at request time. Ship `bind_X_module_to_mock(mock_sb)` in `noctusai_lib.testing` for conftests. Reference adopters: `noctusai_lib.ai.consent.consent_required` + `noctusai_lib.llm.budget.configure_budget_module`. → `KB § PATTERNS/backend.md § FastAPI dependency factories with module-level injection`
- **MCP migrations mirror the file.** Any DDL applied via Supabase MCP (`apply_migration` / `execute_sql`) MUST also exist as a numbered migration file at `products/<name>/backend/migrations/NNN_<name>.sql` — commit both together. The DB is mutable state; migration files are the authoritative replay log. → `KB § PATTERNS/database-rls.md`
- **Supabase MCP is the agent's tool — use it proactively.** When a task needs DB access (apply migration, audit schema, verify RLS, seed/inspect data), execute it directly through `mcp__claude_ai_Supabase__*`. **Never** ask the user to paste SQL. Blanket approval stands. `apply_migration` for DDL; `execute_sql` for read-only inspection. → `KB § 01-PHILOSOPHY.md § Supabase MCP is the agent's tool`
- **Webhook receivers verify before any side effect.** Every inbound webhook in this monorepo authenticates the payload's origin via `noctusai_lib.security.webhook_signatures` (HMAC `sha256=…` / bare hex / Svix protocol) before parsing the body, writing to the DB, or dispatching downstream work. Stripe ships its own verifier — use the SDK, don't wrap it. Constant-time compare always; replay-window enforcement when the provider sends a timestamp. Bypass on unset secret = WARNING + 200 (early-dev affordance only); production sets the secret. → `KB § PATTERNS/webhook-signatures.md` + `KB § 04-SHARED-LIBRARY.md § security/`

## Pointers (depth)

- Backend patterns (auth, SSO, RLS, N+1, service layer) → `KB § PATTERNS/backend.md`
- Per-product backend specs → `KB § backend/{01-CORE, 02-ERP, 03-PF, 04-DATABASE, 05-AI-FEATURES, 06-THERAPY, 07-AUTH-SECURITY, 08-DAILY-LIFE}.md`
- Database & RLS (subquery `auth.uid()`, `search_path`, policy templates) → `KB § PATTERNS/database-rls.md`
- LLM access (multi-provider via `noctusai_lib.llm`; never `from openai import`; `cache=False` for clinical text) → `KB § 04-SHARED-LIBRARY.md § llm/`
- Logging convention (level guide, no-`# silent-ok` rule, bootstrap-time pattern, correlation IDs) → `KB § PATTERNS/logging.md`
- Environment / `.env` (single root, VITE_ security rule, CORS_ORIGINS) → `KB § PATTERNS/environment.md`
- Notifications (proxy, shape, shared `NotificationBell`) → `KB § PATTERNS/notifications.md`
