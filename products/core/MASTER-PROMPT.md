# Core Platform -- Master Prompt

## Purpose

Central auth and administration hub for the NoctusAI multi-product SaaS platform. Manages organizations, users (noctus_users), billing (Stripe), licensing, SSO token exchange, and the admin dashboard. All other products depend on Core for authentication, org management, and notification delivery.

## Architecture

- Schema: `public`
- Backend port: 8000 | Frontend port: 5173
- Tenant key: `org_id`
- Auth: Custom REST API (Supabase Auth + noctus_users table); core IS the identity provider that Supabase delegates to for every consumer product.
- Backend path: `products/core/backend/app/` — inherits from the seed framework via `create_product_app(schema="public", standard_routers=["health"])`. Core owns its own `team` / `notifications` / `admin_*` routers (not the seed's bundled counterparts).
- Frontend path: `products/core/frontend/src/` — **currently on custom JWT + refresh-token auth** (not Supabase-based) because core IS the auth source. Migration to `createProductApp({ authProvider })` is tracked by Phase 4 of `products/core/projects/core-seed-wiring/`.

## Key Domains

### Auth and Identity
- **auth** -- login, signup, password reset, token refresh. The core SPA owns its own refresh chain: every refresh goes through `refreshCoreSession()` (`frontend/src/lib/api.ts`), serialised across tabs by a Web Lock. `POST /api/auth/logout` defaults to scope `global` (the explicit "Sair"); the inactivity timer uses `?scope=local` so a forgotten core tab never signs the user out of the products (2026-10-23).
- **oauth** -- third-party OAuth provider flows
- **sso** -- SSO token creation/verification for cross-product access (5-min short-lived JWT)
- **sso_public** (`GET /api/sso/produto/{slug}`, `app/routers/sso_public.py`, tier public/auth) -- `{slug, nome, icone, landing_url}` of an ACTIVE product for core's central login (`/login?produto=&next=&prompt=none|login`, `/esqueci-senha`, `/redefinir-senha`); contract `products/core/docs/sso-entry-contract.md`, design `sso-session-lifecycle-2026-11` (S3, dormant until the seed points at it)
- **onboarding** -- first-time org setup wizard
- **M2M API tokens** (migration 099, page `/admin/tokens`, platform admins only) -- machine access for our own automation. The seed token routes are mounted in `app/auth_context.py::build_tokens_router` (`/api/settings/api-tokens`: mint, list, `GET /scopes`, `POST /{id}/rotate`, `DELETE /{id}`); tokens mint as `noc_<64 hex>` (legacy `pk_` still accepted until the cutoff, `NOC-REMEDIATE[pk-prefix-cutoff]`), with an expiry or an explicit no-expiry, revocation and `last_used_at`. Scopes come from the server allow-list `app/services/api_tokens.py::CORE_TOKEN_SCOPES` (`transcription:read|write`, `reminders:read|write`), never free text. `public.service_accounts` ("noc-agent") + nullable `api_tokens.service_account_id`. ONE `get_auth_context` (`app/auth_context.py`) serves the transcription API and the token routes; `ApiTokenAuditMiddleware` writes `api_token_audit`. **MFA to mint is a platform setting, OFF by default** (`platform_settings.exigir_mfa_para_tokens`; `GET/PUT /api/admin/tokens/settings`, platform admins): off = no MFA to mint/rotate; on = an unmet MFA is refused by name (403 `mfa_required`). KB: `PATTERNS/backend/platform-grants.md`.

### Organization and Team
- **organizations** -- CRUD for orgs, org settings
- **team** -- invite members, manage org membership (uses noctusai_lib invitations)
- **roles** -- 7-role hierarchy (owner, admin, manager, member, viewer, dev, test) with granular permissions
- **brand** (`/api/brand`, migrations 089 + 094 NULL-safe tokens schema CHECK) -- the org's visual identity, ONE per org, worn by core and every product of the selected org via the seed `BrandProvider`; falls back to the NOC standard (platform row, `org_id IS NULL`). Versioned drafts (`draft|active|archived|failed`), `.md`/`.pdf` ingestion through the seed LLM client (Sonnet 5.5) into `noctus.brand-tokens/v1` with deterministic validation (token keys derived from seed `tokens.css`, strict regexes, WCAG contrast in code, derived dark), activate/rollback via the service-role `brand_identity_activate`. `voice`/`brand_book`/`source` are server-only (column grant). Contract: `projects/org-brand-identity/CONTRACT.md`
- **platform_templates** (`/api/admin/templates`, migration 092) -- platform-admin-only versioned template library (`design_system|agent|message|document|repo_workflow`, `product` NULL = platform-wide). Append-only history: a draft edits in place, editing an active/archived version spawns draft N+1; activation archives the previous active via the service-role `platform_template_activate`; non-draft rows are content-frozen by trigger. JSON bodies must parse to an object; `design_system` bodies are validated with the `noctus.brand-tokens/v1` rules (seed row = NOC standard tokens). Body cap 200k chars. `GET /meta` is the kind->scope nav tree, `GET /sources` the read-only "Fontes" catalogue (`app/services/platform_templates/sources.py`, path-existence tested). The filesystem scaffold browser lives at `/api/admin/template-scaffolds`

### AI usage ledger
- **ai_usage** (`public.ai_usage`, migration 091, roadmap D25) -- ONE append-only ledger of every LLM call of every product (core included), written by the seed `CentralUsageSink` (service role) with org / product / feature / user attribution, write-time price (`price_version`) and PTAX BRL. Trigger refuses UPDATE/DELETE/TRUNCATE except the wallet's single `charged_credits` NULL->value stamp; RLS = org members + platform admins read. Read by `/api/admin/llm-usage` (platform admin; `org_id/product/feature/from/to`), the seed `/api/llm/usage` and the budget guard. Pattern: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend/llm-usage.md` §0
- **dev_telemetry_claude / dev_telemetry_os / dev_telemetry_jobs / dev_telemetry_marks** (`public`, migration 097) -- DEV telemetry, never product data and never mixed into `ai_usage`: Claude Code usage per host x 5-min bucket x session/agent x model (tokens incl. thinking/cache, API-equivalent cost from the seed rate card, chars, tool calls), OS samples and heavy-job runs from the hardware-admission log, plus phase/experiment marks. Written only by `noctus.dev.usage_eval action=sync` (service role, idempotent upserts, counts only — no text); RLS on, no policies; read by the usage dashboard prototype. Pattern: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/usage-evaluation.md`

### AI credit wallet (prepaid)
- **noctus_users.telefone** (`public`, migration 096) -- the platform user's WhatsApp number, E.164 (`CHECK ^\+[1-9][0-9]{7,14}$`, probe `noctus_users.telefone.e164`), NULL = unset. SINGLE source of truth ("my number is set in noc"): `PATCH /api/auth/profile` normalizes via `noctusai_lib.primitives.phone.normalize_phone` (`""` clears; unparseable → 422 pt-BR), `/me` + admin user list return it (`select("*")`). Other products store a USER ID and resolve the phone at use time with `noctusai_lib.integrations.persistence.table_reads.resolve_user_phones(core_client, user_ids)`. Not `organizations.telefone` (the company phone).
- **credit_pricing / credit_wallets / credit_entries / credit_purchases** (`public`, migration 093) -- per-org prepaid AI credits. Every movement (purchase, admin grant, adjustment, refund, usage debit) goes through ONE SECURITY DEFINER RPC `credit_apply_entry` (per-org advisory lock, dedup on `ai_usage_id` / `payment_ref`, appends the entry, moves the balance, advances the 50/80/100% alert state, stamps `ai_usage.charged_credits`); entries are append-only, balances writable only through that RPC (GUC carve-out), pricing insert-only + versioned. Probes: `noctus.dev.verify_db_guards` (credit_*).
- **Pricing** (`app/services/credits/pricing.py`, the one formula): `price_BRL = cost_usd x (PTAX + fx_buffer) x (1 + IOF + import) / (1 - Simples - gateway_fee) x (1 + margin)`; credits = price / credit_unit_brl (seed v1: R$ 0,01, margin 1.0 -> about 48% usage gross margin).
- **Debit** -- scheduler job `core_credits_debit` every minute (`services/credits/debit.py`): charges `ai_usage` rows with `charged_credits IS NULL` of orgs WITH a wallet, created at/after the wallet's `charge_from`; BYOK wallets are stamped 0 (`source='byok'`); idempotent. Orgs without a wallet are untouched (today's behaviour).
- **Enforcement** -- seed `noctusai_lib.integrations.llm.budget.enforce_credits` (inside `enforce_budget`): `prepaid` at/below `-overdraft_limit` -> `LLMCreditsExhausted` 402 before the provider call; unreadable wallet of an unknown/prepaid org -> `LLMCreditsUnverifiable` 503 + platform-admin mark (fail-closed); 15 s TTL cache.
- **Routes** -- org owner/admin/manager: `GET /api/credits/wallet`, `GET /api/credits/usage` (org -> product -> feature, credits + retail R$ + tokens; never cost/margin), `POST /api/credits/purchase` (one-off charge on the enabled gateway; `external_reference = credits:<id>`; the paid webhook credits via `credit_apply_entry`). Platform admin: `/api/admin/credits/wallets`, `/{org_id}`, `/{org_id}/grant` (GET history / POST credits or USD + reason, `kind=grant source=admin_grant`), `/{org_id}/adjustments`, `PUT /{org_id}/wallet` (mode `prepaid|postpaid_trusted|byok`, overdraft, thresholds), `/pricing` (GET / POST new version), `/margin`.
- **Alerts** -- a crossed 50/80/100% threshold notifies the org's owners/admins and the platform admins in-app (seed `write_in_app`, kind `creditos_alerta`).

### Products and Licensing
- **products** -- product registry, per-org product activation
- **licenses** -- license provisioning, `on_license_change` trigger auto-provisions product defaults
- **entitlements** -- feature gating per plan/org

### Billing
- **plans** -- plan definitions
- **subscriptions** -- Stripe subscription lifecycle
- **billing** -- Stripe checkout, webhooks, customer portal

### Admin
- **api_keys** -- API key management
- **analytics** -- platform-wide metrics
- **test_accounts** -- test/demo account management
- **audit_logs** -- compliance audit trail
- **audit_digest** -- C2 weekly audit-log narrative digest (ai-expansion Phase 9). `POST /api/admin/audit-digest/{org_id}` aggregates the past `period_days` (default 7) of `audit_logs`, asks the LLM for a 3-paragraph PT narrative, and fans out via `noctusai_lib.email.digest.send_digest` to every `noctus_users.role='admin'` recipient. `GET .../preview` returns the rendered body without sending. Service: `app/services/audit_digest_service.py`. Rendering inline (no Jinja — same as metas digest).
- **usage** -- usage tracking per org/product
- **admin_usage** (`/api/admin/usage/{dev,machine,jobs,fx}`, `app/routers/admin_usage.py`, platform-admin only; page `/admin/uso` = `src/pages/admin/AdminUsoCustos.tsx` + `src/lib/usage.ts`, "Uso & Custos") -- dev usage evaluation per window: Claude Code tokens / API-equivalent cost / chars (`app/services/dev_usage.py`, reads the `dev_telemetry_*` tables of migration 097), machine (OS) and job telemetry, and the FX rate. Dev cost is the Claude Code API-equivalent and is NEVER mixed into `ai_usage` or the credit wallet. `/api/admin/llm-usage` also returns `per_agent` / `per_session` / `attribution` and accepts `agent_key` / `conversation_id` filters
- AI call pipeline (migration 116): `ai_usage` carries `trace_id` / `span_id` / `parent_span_id` / `latency_ms` / `prompt_version` (an LLM-call row is its trace span); `ai_trace_spans` holds tool / guardrail / internal spans (service-role only); view `ai_trace_timeline` joins both; function `ai_spend_window()` feeds the seed per-surface spend guard and view `ai_spend_24h_by_surface` is the report to choose its limits from (`KNOWLEDGE-BASE/CONTEXT/PATTERNS/ai/ai-engineering-canon.md` §6, §8)
- Platform AI usage & cost (`/api/admin/usage/ai/{sources,usage,cost,spend,deliveries,rate-limits}`, `app/routers/admin_ai_usage.py` + `app/services/ai_usage/`, platform admins only; migration 112, contract `products/core/docs/ai-usage-contract.md`): two sources never summed -- `anthropic` (Admin usage/cost analytics synced by the `anthropic_usage_snapshot` scheduler job with `ANTHROPIC_ADMIN_API_KEY`; unavailable on an Individual Org) and `ledger` (`dev_telemetry_claude` + `dev_deliveries`)
- **operations** -- `/api/admin/operations` (platform admin only): `GET routines` (per-product jobs from `public.scheduler_jobs` + last run/24h counts from `public.scheduler_runs`, missing runs computed from the published cron/interval, brief dead-man), `GET runs`, `GET models` (seed catalog), `GET costs` (LLM spend yesterday via the existing usage aggregation + `cost_ledger` per org), `GET/POST briefs`. Services: `operations_service.py`, `owner_brief_service.py`. Jobs (`app/scheduler.py`): `core_owner_daily_brief` 07:00 platform tz (code-only, no LLM; in-app to platform admins + e-mail to `settings.website_leads_notify_email`) and `core_scheduler_runs_retention`. The run ledger itself is seed-wide (`noctusai_lib.domain.scheduler_runs`, installed by `create_product_app`). Page: `/admin/operacao`.
- **noc_funnel** (`/api/admin/funnel`, `app/noc_funnel.py`, migration 107; page `/admin/funil` = `src/pages/admin/AdminFunil.tsx` + `pages/admin/funil/`) -- NoctusAI's own sales funnel: core's `FunnelConfig` for the seed funnel organ (`noctusai_lib.domain.pipeline.funnel`), mounted after `create_product_app` with `get_current_admin` as the guard (platform tier: 401 / 403, never public). The card table IS `website_leads` (title `name`, owner `owner_user_id`, status `status`; value = `valor_unico`, plus `valor_mensal`); migration 107 = the organ's `pipeline_migration` output verbatim (`render_migration()`, pinned by test) + offer columns + BEFORE/AFTER INSERT triggers that place every new lead in the first stage + 4 default stages + backfill of the legacy `stage` column (KEPT, expand-only: `NOC-REMEDIATE[funnel-lead-stage-contract]`). Funnel rows (stages, movimentos) carry the scope id `NOC_FUNNEL_ORG_ID` (no FK, not `organizations`). Gates key on stage `papel` (`novo|contatado|qualificado|proposta`); action `ganhar` sets status ganho (`NOC-REMEDIATE[core-funnel-ganho-bridge]`: no Stripe link / receivables yet); card hub not wired (`NOC-REMEDIATE[core-funnel-card-hub]`). Contract: `projects/noc-funnel/CONTRACT.md`

### Communication
- **notifications** -- `public.notifications` table, platform-wide notification delivery
- **owner notifications (Notificações page, `/api/admin/notifications`)** -- every owner-facing notice a product declares, with a per-(product, kind) switch; the roster lists EVERY live product + core even when it declares no kind (`declared: false`). `public.notification_owner_recipients` is the platform's ONE owner number (agents' hand-off number reads it; migration 121 copied the old agents value in). Core declares `skill_scout_novo_skill` (WhatsApp only; `app/notification_kinds.py`, `skill_scout_notice_service`, `POST /api/admin/notifications/skill-scout`). KB `PATTERNS/backend/owner-notification-catalog.md`
- **webhooks** -- webhook registration and delivery system (`webhook_delivery` service)
- **settings** -- platform settings
- **templates** -- email/notification templates

## Auth Functions

| Function | Purpose |
|----------|---------|
| `get_current_user(authorization)` | Validates Bearer token via Supabase Auth, returns `(user, token)` |
| `get_current_admin(authorization)` | Same + checks `noctus_users.role == "admin"` (403 if not) |
| `get_current_user_with_permissions(authorization)` | Fetches org_role + role permissions |
| `create_sso_token(user_id, org_id, ...)` | Short-lived JWT for product access |
| `verify_sso_token(token)` | Validates SSO token structure and expiry |

## Services (9)

audit, **audit_digest** (Phase 9 — weekly LLM narrative + multi-admin Resend fan-out), billing, email (Resend), entitlements, notifications, permissions, stripe, webhook_delivery

## Permission Model

**System roles** (org_id IS NULL): owner, admin, member, viewer. **Granular permissions**: `team:manage`, `billing:manage`, `settings:manage`, `products:access`, `*`, etc. Custom roles per-organization with any combination.

## Frontend Pages

AcceptInvite, AccountSettings, admin/AdminUsoCustos (`/admin/uso` -- Uso & Custos, platform admin), BillingSettings, BrandIdentity (`/org-settings/identidade` — Identidade visual: preview, upload, draft editor, activate, history), CheckoutCancel, CheckoutSuccess, Dashboard, EsqueciSenha, RedefinirSenha, admin/AdminOperacao (`/admin/operacao/*` — Rotinas, Saúde, Modelos de IA, Custos, Brief), Login, Onboarding, OrgSettings, Pricing, TeamManagement, admin/ (incl. AdminCreditos `/admin/creditos` — wallets, grant dialog, margin report, pricing editor; CreditosUso `/org-settings/creditos` — Créditos e uso: balance, usage, buy credits; TemplatesAdmin at `/admin/templates/*`: kind->scope nav, editor with versions, Fontes)

## Development Guidelines

- Follow shared patterns from noctusai_lib (auth, roles, invitations, responses, exceptions)
- Router → Service → Schema pattern; routers thin, business logic in services
- **Schemas live under `app/schemas/` as 21 per-domain modules** (5-wave extraction, commit `09ea826`, 2026-05-11). Add a new module rather than appending; one `BaseModel` cluster per file. `app/schemas/__init__.py` is the canonical re-export surface — keep it tidy.
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- `org_settings`, `webhook_endpoints`, `webhook_deliveries`, `api_keys` are **service-role only** (migration 086): never grant them to anon/authenticated or add a browser policy; the backend reaches them through `get_admin_client()` behind admin role checks. `noctus_users` and its subquery policies are a separate follow-up (SECURITY DEFINER refactor). DB probes `core.secret_tables.*`.
- Portuguese for business domain names, English for technical/framework code
- Use `get_current_admin()` for all admin-only routes
- `audit_logs` service ⇒ log all sensitive operations (user changes, billing events)
- Webhook delivery uses retry with exponential backoff
- N+1 zero tolerance: `.in_("id", ids)` for batch reads, `.insert(rows)` for batch writes
- All product notification proxies route through Core's `public.notifications` table
- Core's frontend passes `notifications: { hooks, onNavigateProduct }` (from `components/NotificationBell.tsx`) to `createProductApp`: the seed shell mounts the live operational pop-ups + a fallback bell on header-less pages, and bridges core's custom auth to the global auth-ready signal (without it the notification queries never enable). See `KB § PATTERNS/frontend/notification-classes.md`
- **Rate-limit policies are canonical.** `team.py` ∧ `onboarding.py` consume `DEFAULT_AUTH_RL` from `noctusai_lib.api.rate_limit_policies`. New auth/team/invite routes MUST import `DEFAULT_AUTH_RL`; webhook routes → `DEFAULT_WEBHOOK_RL`; admin/portal routes → `DEFAULT_PORTAL_RL`; LLM-touching routes → `DEFAULT_AI_RL`. Inline `@limiter.limit("N/min")` strings ≡ N=2 trigger.
- **Doc-code coherence at commit time.** Script / MCP tool / keeper detector / CLI flag Δ referenced by this MASTER-PROMPT ∨ `KB § backend/01-CORE.md` ⇒ update prose in SAME commit. `grep -rn "<tool-name>" KNOWLEDGE-BASE/ CLAUDE.md CLAUDE/ products/core/` first. → CLAUDE.md §1 "Doc-code coherence" + `KB § PATTERNS/methodology-codification-pipeline.md`

## Testing

```bash
cd products/core/backend && pytest
```

Tests live under `products/core/backend/tests/` (45 files; grew from 23 post-Phase-3 seed-framework migration). New core tests should:

- Inherit framework suites from `noctusai_lib.testing.framework_test_suites` (TestHealthCheck / TeamRouter* / AuthBoundary / NotificationFlow / etc.) rather than copy-paste. Core uses the `admin_client` rich variant — content-diff before deciding "duplicate" with another product's adopter.
- For `TeamFlowSuite` adopters: set the `expected_org_id` **class attribute** (commit `f2b0336`, 2026-05-11) — drives the assertion seam without overriding helper methods.
- Use `MockSupabaseClient` from the seed; the mock deep-copies caller inputs at storage time, so write-propagation (UPDATE/DELETE) tests don't mutate module-level fixture dicts. Q's seed-side fix to `_eval_is` (PostgREST IS-NULL semantics) + `_FilterMixin.not_` negation landed 2026-05-11; pull the latest noctusai_lib if a `.is_("col", "null")` / `.not_.is_(...)` query returns surprising rows.
- Never `monkeypatch.setattr(<our_module>, ...)` — seed the underlying data instead. `unittest.mock.patch.object(<external_integration>, ...)` for LLM/Resend/Stripe network IS fine.

## Dependencies

- Shared backend: `noctusai_lib`
- Shared frontend: `@noctusai/lib` + `@noctusai/lib/design-system`
- Stripe: checkout, subscriptions, webhooks, customer portal
- Resend: transactional email delivery
- Supabase: Auth, database, RLS

## Methodology hooks (2026-05-11 refresh)

- **Codification pipeline.** s1 emerges → s2 memory → s3 KB+CLAUDE.md → s4 `check_*` keeper detector with colocated test. Promote when: deterministic predicate ∧ N≥3 ∧ remediation defined. Today's batch added 10 new keeper detectors covering hygiene + codification gaps — discover via `noctus.dev.outline_python mcp/noctusai/tools/noctus/dev/compliance.py`. → `KB § PATTERNS/methodology-codification-pipeline.md`
- **Bootstrap auto-hydrate.** Fresh worktrees ∧ clones run `scripts/bootstrap/bootstrap-worktree.sh` ∨ `scripts/setup.sh`; both auto-hydrate hooks + venv + npm without manual steps. Missing hook in worktree ⇒ re-run setup before touching code; ¬ commit around a missing pre-commit.
- **Branching-first orchestration.** Multi-router ∨ multi-service changes in core (e.g. the schemas extraction) ⇒ waves of focused engineer chunks, ¬ a single sprawling brief. Architect plans; engineers execute. Wave N+1 dispatches after Wave N FF-merges. → CLAUDE.md §1 + `KB § PATTERNS/branching-and-merging.md`
