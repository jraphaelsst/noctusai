# NoctusAI Shared Library Catalog

> Check here before building anything new. If it exists, use it.

## Backend: `noctusai_shared` (Python)

Install: `pip install -e shared/backend`. Import: `from noctusai_shared.<module> import ...`

### `auth.py` — Authentication & SSO

| Function | Purpose |
|----------|---------|
| `first_or_none(result)` | Extract first record from Supabase response |
| `resolve_sso_role(user)` | Check SSO metadata → `"platform_admin"` or `None` |
| `get_sso_context(user)` | Extract all SSO context (role, org, plan, license) |
| `require_role(get_user_role_fn, *roles)` | FastAPI dependency factory for role enforcement |
| `get_current_user(authorization, ...)` | JWT validation (base — products define own wrapper) |
| `make_get_current_user(get_supabase_client_fn)` | Factory for product-specific `get_current_user` |

### `roles.py` — Role System Constants

`ORG_ROLES` (all 7), `ADMIN_ROLES` (owner, admin), `MANAGE_TEAM_ROLES` (+manager), `DEV_ROLES` (owner, dev), `ORG_ROLE_LABELS` (Portuguese). Helpers: `is_dev_or_owner()`, `can_manage_team()`, `can_manage_billing()`.

### `invitations.py` — Invitation System

`generate_invite_token()`, `create_invitation()`, `validate_invitation()`, `accept_invitation()`, `cancel_invitation()`, `list_pending_invitations()`, `expire_old_invitations()`.

### `email_templates.py` — Product-Branded Emails

`send_product_invitation_email()` (branded invite with accept button), `send_password_reset_email()` (branded reset).

### `page_status.py` — Dev-Gated Page Visibility

`get_visible_pages(db, user_org_role)` — returns visible page route names based on role.

### `notifications.py` — Notification Field Mapping

`map_notification_to_pt()` / `map_notification_from_pt()` — English↔Portuguese field mapping for core notifications.

### `app_factory.py`

`configure_app(app, settings)` — registers exception handlers, CORS, middleware, rate limiting, Sentry.

### `config.py`

`BaseAppSettings` — Pydantic BaseSettings with `cors_origins_list`, `is_production`, `debug`, `jwt_secret` validation.

### `database.py`

`make_supabase_client(url, key, schema?, token?)` — create Supabase client targeting a specific schema.

### `responses.py`

`success_response(data)`, `paginated_response(data, total, page, page_size)`, `ok_response(message)`, `deleted_response()`.

### `exceptions.py`

`AppException` hierarchy. Auto-registered via `configure_app()`.

### `middleware.py`

`CorrelationIdMiddleware` (unique request ID), `RequestLoggingMiddleware` (timing).

### `logging_config.py`

`configure_logging(debug)` — JSON (prod) or human-readable (dev).

### `testing/` — Mock Supabase Infrastructure

| Class | Purpose |
|-------|---------|
| `MockSupabaseClient` | `.table()`, `.set_table_data()`, `.set_sequential_responses()`, `.rpc()` |
| `MockSelectBuilder` | Chainable: `.eq()`, `.order()`, `.single()`, `.or_()`, `.gte()`, `.lte()`, `.ilike()` (no-op) |
| `MockFilterBuilder` | For `.update()` / `.delete()` chains |
| `MockQueryBuilder` | For `.insert()` / `.upsert()` |
| `MockUser` | Parameterized: `MockUser(role="therapist", org_id="x", clinic_id="y")` |
| `AuthClient` | Wraps TestClient with Bearer auth. `.mock_supabase` property, `.raw()` for unauth |

---

## Frontend: `@noctusai/shared` (TypeScript)

Import: `import { ... } from '@noctusai/shared'`

### `api.ts` — HTTP Client

`createApiClient(options)` — factory with `safeFetch`, 401 retry via `onTokenExpired`, auto-auth headers. `extractErrorMessage(error)`.

### `roles.ts` — Role System Constants

`ORG_ROLES`, `ADMIN_ROLES`, `DEV_ROLES`, `MANAGE_TEAM_ROLES`, `PRODUCT_ADMIN_ROLES`, `ASSIGNABLE_ROLES`, `ORG_ROLE_LABELS`. Helpers: `isDevOrOwner()`, `canManageTeam()`, `canManageBilling()`. Type: `OrgRole`.

### `page-status.ts` — Dev-Gated Page Visibility

`usePageStatus(supabase)` — TanStack Query hook (10min staleTime). `isPageVisible()`, `filterNavByPageStatus()` — hides dev/disabled pages, adds DEV badge.

### `sso.ts` — SSO Context & Role Resolution

`resolveSSORoles(metadata)` → `{ isSSO, isProductAdmin }`. `resolveSSOContext(metadata)` → full context with plan/subscription/license/org. `isTrial()`, `subscriptionDaysRemaining()`, `licenseDaysRemaining()`.

### `auth.ts`

`useSupabaseAuthInit(supabase, setUser, setInitialized?)` — session + auth change subscription.

### `stores.ts`

`createAuthStore()` — Zustand with user/isInitialized. `createFiltrosStore(name)` — persisted date range filter.

### `hooks.ts`

`createCrudHooks<T>(options)` → `useList`, `useOne`, `useCreate`, `useUpdate`, `useDelete` with auto-invalidation.

### `notifications.ts`

`createNotificationHooks(api, useAuthStore)` → `useNotificacoes`, `useContagemNaoLidas`, `useMarcarComoLida`, `useMarcarTodasComoLidas`.

### `env.ts` — Shared Environment Configuration

| Export | Purpose |
|--------|---------|
| `env` | Typed access to all VITE_ product env vars with fallbacks |
| `validateEnv()` | Call in `main.tsx` — logs missing required vars to console |
| `generateEnvExample(port)` | Generates `.env.example` content for a given backend port |
| `ENV_VARS` | Definition object for all required vars (viteKey, description, required, defaultDev) |

Required vars: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`. Optional with defaults: `VITE_BACKEND_API_URL`, `VITE_CORE_URL`, `VITE_CORE_API_URL`.

### `supabase.ts`

`createProductSupabase(schema?)` — creates client using `env.SUPABASE_URL` + `env.SUPABASE_PUBLISHABLE_KEY` from shared env module.

### `utils.ts`

`cn()` (Tailwind class merger), `formatCurrency()` (BRL), `formatDate()` (pt-BR), `getTodayAtMidnight()`, `stripTime()`.

### `components/`

`SSOCallback` (token exchange + session setup), `ErrorBoundary` / `withErrorBoundary`, `createAuthProvider(supabase, useAuthStore)`.

---

## Design System: `@noctusai/shared/design-system`

Import: `import { ... } from '@noctusai/shared/design-system'`

### Layout

`AppShell` (sidebar + header + content, responsive), `Sidebar` (prop-driven with NavGroups, brand, footer), `Header` (HoverCard user card, theme toggle, logout).

### UI Components

`NotificationBell` (bell + popover + mark-as-read), `LoginForm` (Supabase email/password with branding), `AcceptInvitePage` (token validation + signup), `ForgotPasswordPage` (Supabase reset), `PageSkeleton` (animated loading), `PoweredByFooter` (sidebar + landing variants), `InactivityWarning` (session expiry), `HoverCard` (Radix-based).

### Hooks

`useTheme(options?)` — dark/light with localStorage + DOM + optional DB persistence. `useActivityRefresh(options)` — proactive token refresh every 5min.

### Styling

`tokens.css` — single source of CSS custom properties. `tailwind.config.base.ts` — shared Tailwind theme (products extend via presets).

### Types

`NavGroup`, `NavItem`, `NotificationHooks`, `LoginFormProps`.

---

## Adding Shared Code

1. **Backend**: `shared/backend/noctusai_shared/<module>.py`
2. **Frontend**: `shared/frontend/src/<module>.ts`, export from `index.ts`
3. **Design system**: `shared/frontend/src/design-system/components/`, export from `design-system/index.ts`
4. **Document**: Update this file
5. **Update seed product**: `products/seed/` — the live reference implementation. Template auto-syncs via post-commit hook.

## Scripts & Automation

| Script | Purpose | Run when |
|--------|---------|----------|
| `scripts/setup.sh` | Full repo setup (hooks + venv + deps) | Once after `git clone` |
| `scripts/sync-seed-template.sh` | Sync seed → template with `{{PLACEHOLDERS}}` | Automatic via hook, or manual |
| `scripts/install-hooks.sh` | Git hooks only (subset of setup.sh) | If hooks need reinstalling |
| `start.sh` | Start all backend + frontend servers | When developing |

The post-commit hook auto-syncs `products/seed/` → `templates/product-seed/` on every commit that touches the seed. See `scripts/README.md` for details.
