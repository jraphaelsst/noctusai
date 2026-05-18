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
- **auth** -- login, signup, password reset, token refresh
- **oauth** -- third-party OAuth provider flows
- **sso** -- SSO token creation/verification for cross-product access (5-min short-lived JWT)
- **onboarding** -- first-time org setup wizard

### Organization and Team
- **organizations** -- CRUD for orgs, org settings
- **team** -- invite members, manage org membership (uses noctusai_lib invitations)
- **roles** -- 7-role hierarchy (owner, admin, manager, member, viewer, dev, test) with granular permissions

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

### Communication
- **notifications** -- `public.notifications` table, platform-wide notification delivery
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

AcceptInvite, AccountSettings, BillingSettings, CheckoutCancel, CheckoutSuccess, Dashboard, Login, Onboarding, OrgSettings, Pricing, TeamManagement, admin/

## Development Guidelines

- Follow shared patterns from noctusai_lib (auth, roles, invitations, responses, exceptions)
- Router → Service → Schema pattern; routers thin, business logic in services
- **Schemas live under `app/schemas/` as 21 per-domain modules** (5-wave extraction, commit `09ea826`, 2026-05-11). Add a new module rather than appending; one `BaseModel` cluster per file. `app/schemas/__init__.py` is the canonical re-export surface — keep it tidy.
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- Portuguese for business domain names, English for technical/framework code
- Use `get_current_admin()` for all admin-only routes
- `audit_logs` service ⇒ log all sensitive operations (user changes, billing events)
- Webhook delivery uses retry with exponential backoff
- N+1 zero tolerance: `.in_("id", ids)` for batch reads, `.insert(rows)` for batch writes
- All product notification proxies route through Core's `public.notifications` table
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
