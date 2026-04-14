# NoctusAI Shared Library Catalog

The shared library is the platform's validated, reusable code that all products consume. Before building anything new, check if it already exists here.

## Backend: `noctusai_shared` (Python)

Installed via `pip install -e shared/backend`. Import as `from noctusai_shared.<module> import ...`.

### `auth.py` — Authentication & SSO

| Function | Purpose | Usage |
|----------|---------|-------|
| `first_or_none(result)` | Extract first record from Supabase response | `record = first_or_none(db.table("x").select("*").execute())` |
| `resolve_sso_role(user)` | Check SSO metadata for admin access. Returns `"platform_admin"` or `None`. | `sso = resolve_sso_role(user); if sso: return sso` |
| `get_sso_context(user)` | Extract all SSO context (role, org, plan, license) from metadata | `ctx = get_sso_context(user); plan = ctx["plan_slug"]` |
| `require_role(get_user_role_fn, *roles)` | FastAPI dependency factory for role enforcement | `admin_only = require_role(get_user_role, "platform_admin")` |
| `get_current_user(authorization, *, _get_supabase_client)` | JWT validation (base — use product wrapper) | Products define own `get_current_user` in `dependencies.py` |
| `make_get_current_user(get_supabase_client_fn)` | Factory for product-specific `get_current_user` | `get_current_user = make_get_current_user(get_supabase_client)` |

### `roles.py` — Role System Constants

| Export | Purpose |
|--------|---------|
| `ORG_ROLES` | Tuple of all 7 valid org_role values |
| `ADMIN_ROLES` | (owner, admin) — manage team + billing |
| `MANAGE_TEAM_ROLES` | (owner, admin, manager) — can invite/remove |
| `DEV_ROLES` | (owner, dev) — see in-development pages |
| `ORG_ROLE_LABELS` | Portuguese labels for UI display |
| `is_dev_or_owner(role)` | Check if user can see dev pages |
| `can_manage_team(role)` | Check if user can invite/remove |
| `can_manage_billing(role)` | Check if user can manage billing |

### `invitations.py` — Invitation System

| Function | Purpose |
|----------|---------|
| `generate_invite_token()` | Cryptographically secure 32-char token |
| `create_invitation(db, table, org_id, email, role, invited_by)` | Creates invitation record, checks duplicates |
| `validate_invitation(db, table, token)` | Validates token: exists, pending, not expired |
| `accept_invitation(db, table, invitation_id)` | Marks invitation as accepted |
| `cancel_invitation(db, table, invitation_id, org_id)` | Cancels pending invitation |
| `list_pending_invitations(db, table, org_id)` | Lists pending invitations for an org |
| `expire_old_invitations(db, table)` | Cleanup: marks expired invitations |

### `email_templates.py` — Product-Branded Emails

| Function | Purpose |
|----------|---------|
| `send_product_invitation_email(to, product_name, org_name, role_label, invite_token, invited_by, base_url)` | Branded invitation email with accept button |
| `send_password_reset_email(to, product_name, reset_url)` | Branded password reset email |

### `page_status.py` — Dev-Gated Page Visibility

| Function | Purpose |
|----------|---------|
| `get_visible_pages(db, user_org_role)` | Returns list of visible page route names based on role |

### `notifications.py` — Notification Field Mapping

| Function | Purpose |
|----------|---------|
| `map_notification_to_pt(record)` | Map core English fields → Portuguese API (`type→tipo`, `title→titulo`, etc.) |
| `map_notification_from_pt(data)` | Reverse: Portuguese → English |
| `NOTIFICATION_FIELD_MAP_TO_PT` | Dict constant for field mapping |

### `app_factory.py` — FastAPI Bootstrap

| Function | Purpose |
|----------|---------|
| `configure_app(app, settings)` | Registers exception handlers, CORS, middleware, rate limiting, Sentry |

### `config.py` — Settings Base

| Class | Purpose |
|-------|---------|
| `BaseAppSettings` | Pydantic BaseSettings with `cors_origins_list`, `is_production`, `debug`, `jwt_secret` validation |

### `database.py` — Supabase Client Factory

| Function | Purpose |
|----------|---------|
| `make_supabase_client(url, key, schema?, token?)` | Create a Supabase client targeting a specific schema |

### `responses.py` — Standard API Responses

| Function | Purpose |
|----------|---------|
| `success_response(data)` | `{"data": data}` |
| `paginated_response(data, total, page, page_size)` | `{"data": [...], "total": N, "page": N, "page_size": N}` |
| `ok_response(message)` | `{"ok": true, "message": "..."}` |
| `deleted_response(message?)` | `{"ok": true, "message": "Removido com sucesso"}` |

### `exceptions.py` — Error Handling

| Class/Function | Purpose |
|----------------|---------|
| `AppException` | Base exception hierarchy |
| Exception handlers | Auto-registered via `configure_app()` |

### `middleware.py` — Request Middleware

| Class | Purpose |
|-------|---------|
| `CorrelationIdMiddleware` | Adds unique ID to every request |
| `RequestLoggingMiddleware` | Logs request start/complete with timing |

### `logging_config.py` — Logging

| Function | Purpose |
|----------|---------|
| `configure_logging(debug)` | JSON (prod) or human-readable (dev) format |

### `testing/` — Mock Supabase Infrastructure

All products import from here instead of defining their own mock classes.

| Class | Purpose |
|-------|---------|
| `MockSupabaseResponse` | Wraps `data`, `error`, `count` |
| `MockSelectBuilder` | Chainable: `.eq()`, `.order()`, `.single()`, `.execute()` etc. |
| `MockFilterBuilder` | For `.update()` / `.delete()` chains |
| `MockQueryBuilder` | For `.insert()` / `.upsert()` (execute only) |
| `MockRequestBuilder` | Entry point returned by `.table()` — routes to correct builder |
| `MockSupabaseClient` | `.table()`, `.set_table_data()`, `.set_sequential_responses()`, `.rpc()` |
| `MockUser` | Parameterized: `MockUser(role="therapist", org_id="x", clinic_id="y")` |
| `MockUserResponse` | Wraps MockUser for `auth.get_user()` response |
| `AuthClient` | Wraps TestClient with Bearer auth header. `.mock_supabase` property, `.raw()` for unauth |

**Usage in conftest.py:**
```python
from noctusai_shared.testing import MockSupabaseClient, MockUser, MockUserResponse, AuthClient

@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id="org-1")))
    with patch("app.database.get_supabase_client", return_value=mock_sb):
        from app.main import app
        yield AuthClient(TestClient(app), mock_sb)
```

---

## Frontend: `@noctusai/shared` (TypeScript)

Consumed via Vite path alias. Import as `import { ... } from '@noctusai/shared'`.

### `api.ts` — HTTP Client

| Export | Purpose |
|--------|---------|
| `createApiClient(options)` | Factory with `safeFetch`, 401 retry via `onTokenExpired`, auto-auth headers |
| `extractErrorMessage(error)` | Extract user-friendly error message from API responses |

### `roles.ts` — Role System Constants

| Export | Purpose |
|--------|---------|
| `ORG_ROLES` | Array of all 7 valid org_role values |
| `ADMIN_ROLES`, `DEV_ROLES`, `MANAGE_TEAM_ROLES`, `PRODUCT_ADMIN_ROLES` | Role group constants |
| `ASSIGNABLE_ROLES` | Roles that can be assigned (excludes owner) |
| `ORG_ROLE_LABELS` | Portuguese labels: `{ owner: "Proprietario", ... }` |
| `isDevOrOwner(orgRole)` | Check for dev page visibility |
| `canManageTeam(orgRole)` | Check for invite/remove permission |
| `canManageBilling(orgRole)` | Check for billing access |

**Type:** `OrgRole`

### `page-status.ts` — Dev-Gated Page Visibility

| Export | Purpose |
|--------|---------|
| `usePageStatus(supabase)` | TanStack Query hook — fetches status_pagina table (10min staleTime) |
| `isPageVisible(route, statusPaginas, orgRole)` | Check if a specific page is visible to user |
| `filterNavByPageStatus(groups, statusPaginas, orgRole)` | Filter nav groups: hides dev/disabled pages, adds DEV badge |

**Types:** `StatusPagina`, `NavItemWithRoute`, `NavGroupWithRoute`

### `sso.ts` — SSO Context & Role Resolution

| Export | Purpose |
|--------|---------|
| `resolveSSORoles(metadata)` | Returns `{ isSSO, isProductAdmin }` — lightweight role check |
| `resolveSSOContext(metadata)` | Returns full `SSOContext`: roles + plan + subscription + license + org |
| `isTrial(ctx)` | True if subscription is in trial |
| `subscriptionDaysRemaining(ctx)` | Days until subscription expires (null if no expiry) |
| `licenseDaysRemaining(ctx)` | Days until license expires (null if permanent) |

**Types:** `SSORoleInfo`, `SSOContext`, `SSOPlanInfo`, `SSOSubscriptionInfo`, `SSOLicenseInfo`, `SSOOrgInfo`

### `auth.ts` — Auth Initialization

| Export | Purpose |
|--------|---------|
| `useSupabaseAuthInit(supabase, setUser, setInitialized?)` | Hook: gets session, subscribes to auth changes, calls store setters |

### `stores.ts` — Zustand Store Factories

| Export | Purpose |
|--------|---------|
| `createAuthStore()` | Creates Zustand store with `user`, `isInitialized`, `setUser`, `setInitialized` |
| `createFiltrosStore(name)` | Creates persisted date range filter store |

### `hooks.ts` — TanStack Query CRUD Factory

| Export | Purpose |
|--------|---------|
| `createCrudHooks<T>(options)` | Returns `useList`, `useOne`, `useCreate`, `useUpdate`, `useDelete` with auto-invalidation |

### `notifications.ts` — Notification Hooks Factory

| Export | Purpose |
|--------|---------|
| `createNotificationHooks(api, useAuthStore)` | Returns `useNotificacoes`, `useContagemNaoLidas`, `useMarcarComoLida`, `useMarcarTodasComoLidas` |

### `query-client.ts` — Query Client

| Export | Purpose |
|--------|---------|
| `createQueryClient()` | TanStack QueryClient with shared defaults |

### `supabase.ts` — Supabase Client Factory

| Export | Purpose |
|--------|---------|
| `createProductSupabase(schema?)` | Creates Supabase client with env vars + optional schema targeting |

### `utils.ts` — Utilities

| Export | Purpose |
|--------|---------|
| `cn(...classes)` | Tailwind class merger (clsx + twMerge) |
| `formatCurrency(value)` | BRL currency formatting |
| `formatDate(date)` | pt-BR date formatting |
| `getTodayAtMidnight()` | Today at 00:00 |
| `stripTime(date)` | Remove time portion |

### `components/` — Shared Components

| Component | Purpose |
|-----------|---------|
| `SSOCallback` | SSO token exchange + session setup (used on `/sso` route) |
| `ErrorBoundary` / `withErrorBoundary` | React error boundary wrapper |
| `createAuthProvider(supabase, useAuthStore)` | Factory: returns `AuthProvider` component with session init |

---

## Design System: `@noctusai/shared/design-system`

Import as `import { ... } from '@noctusai/shared/design-system'`.

### Layout Components

| Component | Purpose |
|-----------|---------|
| `AppShell` | Unified layout shell: sidebar + header + content. Responsive off-canvas sidebar on mobile. |
| `Sidebar` | Prop-driven sidebar with `NavGroup`s, brand section, footer content. Props: `brandIcon`, `brandTitle`, `brandSubtitle`, `navGroups`, `standaloneItems`, `footerContent`. |
| `Header` | Full header: HoverCard user card, edit profile, change password, theme toggle, logout. Props: `user`, `onLogout`, `theme`, `onThemeToggle`, `actions`, `onMenuToggle`. |

### UI Components

| Component | Purpose |
|-----------|---------|
| `NotificationBell` | Bell icon + popover with notification list + mark-as-read. Accepts `hooks` object from `createNotificationHooks`. |
| `LoginForm` | Supabase-based email/password form with configurable branding. Props: `brandIcon`, `brandTitle`, `supabase`, `onSuccess`, `showForgotPassword?`, `showRegisterLink?`. |
| `AcceptInvitePage` | Full invitation acceptance flow: validates token, signup form (nome + password), calls accept endpoint. Props: `productName`, `brandIcon`, `acceptEndpoint`, `apiBaseUrl`. |
| `ForgotPasswordPage` | Password reset via Supabase `resetPasswordForEmail`. Props: `brandIcon`, `brandTitle`, `supabase`, `loginPath?`. |
| `PageSkeleton` | Loading placeholder: animated dashboard skeleton (title bar + card grid + content area). |
| `PoweredByFooter` | "Technology by NoctusAI" footer (sidebar + landing variants). Built but not applied yet — needs design polish. |
| `InactivityWarning` | Session expiry warning with extend/logout actions. |
| `HoverCard` | Radix-based hover card with fade/zoom animations. |

### Hooks

| Hook | Purpose |
|------|---------|
| `useTheme(options?)` | Dark/light theme with localStorage + DOM sync + optional DB persistence |
| `useActivityRefresh(options)` | Proactive token refresh every 5min while user is active |

### Styling

| File | Purpose |
|------|---------|
| `tokens.css` | Single source of truth for CSS custom properties (all products import this) |
| `tailwind.config.base.ts` | Shared Tailwind theme. Products extend via `{ presets: [base] }` |

### Types

| Type | Purpose |
|------|---------|
| `NavGroup` | `{ key, label, icon, defaultOpen?, items: NavItem[] }` |
| `NavItem` | `{ name, href, icon, badge? }` |
| `NotificationHooks` | Object shape accepted by `NotificationBell` |
| `LoginFormProps` | Props for `LoginForm` component |

---

## How to Consume Shared Code

### Backend (Python)
```python
# In any product's dependencies.py, routers, services:
from noctusai_shared.auth import resolve_sso_role, get_sso_context
from noctusai_shared.responses import success_response, paginated_response
from noctusai_shared.notifications import map_notification_to_pt
from noctusai_shared.testing import MockSupabaseClient, AuthClient  # in tests
```

### Frontend (TypeScript)
```typescript
// Utilities and factories
import { createApiClient, createAuthStore, resolveSSORoles, resolveSSOContext, createProductSupabase } from '@noctusai/shared';

// Design system components
import { AppShell, Sidebar, Header, NotificationBell, LoginForm, PageSkeleton, useTheme } from '@noctusai/shared/design-system';
```

### Adding New Shared Code

1. **Backend**: Add to `shared/backend/noctusai_shared/<module>.py`
2. **Frontend**: Add to `shared/frontend/src/<module>.ts`, export from `index.ts`
3. **Design system**: Add to `shared/frontend/src/design-system/components/`, export from `design-system/index.ts`
4. **Document**: Update this file (`KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md`)
5. **Update seed**: If it's a pattern all products should have, update `templates/product-seed/`
