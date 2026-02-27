# 01 — Core Backend Context

> Path: `core/backend/app/`
> Server: FastAPI on port **8000**
> Tests: `core/backend/tests/` (23 test files)

---

## App Setup (`main.py`)

- FastAPI v1.0.0 with CORS middleware (configurable origins)
- Rate limiting: 100/min default via slowapi (10/min for auth endpoints)
- 5 exception handlers: `AppException`, `HTTPException`, `ValidationError`, generic, fallback
- Health endpoints: `GET /` (platform info), `GET /health`
- 20 routers mounted under `/api/`

---

## Authentication (`dependencies.py`)

| Function | Returns | Purpose |
|----------|---------|---------|
| `get_current_user(authorization)` | `(user, token)` | Validates Bearer token via Supabase Auth |
| `get_current_admin(authorization)` | `(user, token)` | Same + checks `noctus_users.role == "admin"` (403 if not) |
| `get_current_user_with_permissions(authorization)` | `(user, token, permissions)` | Fetches org_role + role permissions |
| `create_sso_token(user_id, org_id, ...)` | `str` | Short-lived JWT for product access (5 min) |
| `verify_sso_token(token)` | `dict` | Validates SSO token structure and expiry |

---

## Database (`database.py`)

| Function | Purpose |
|----------|---------|
| `get_supabase_client(access_token?)` | RLS-respecting client (anon key) |
| `get_admin_client()` | Service role client (full access, no RLS) |
| `supabase_admin` | Module-level singleton admin client |

---

## Configuration (`config.py`)

Pydantic BaseSettings loading from root `.env`. Key groups:
- **Supabase**: `supabase_url`, `supabase_anon_key`, `supabase_service_role_key`
- **JWT**: `jwt_secret`, `jwt_algorithm` (HS256), `jwt_expiration_minutes` (1440)
- **SSO**: `sso_token_expiration_minutes` (5)
- **Billing**: `stripe_secret_key`, `stripe_publishable_key`, `stripe_webhook_secret`
- **Optional**: `resend_api_key`, `sentry_dsn`, `redis_url`

---

## Routers (20)

### Authentication & Identity

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| `auth.py` | `/api/auth` | `POST /signup`, `POST /login`, `GET /me`, `PATCH /profile`, `POST /logout` |
| `oauth.py` | `/api/auth/oauth` | `GET /providers`, `POST /callback` (Google, Azure) |
| `sso.py` | `/api/sso` | `POST /token`, `POST /validate`, `GET /launch/{slug}`, `POST /session` |
| `onboarding.py` | `/api/onboarding` | `GET /status`, `PATCH /complete` (4 steps) |

### Organization & Team

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| `organizations.py` | `/api/organizations` | `GET /`, `GET /{id}`, `PATCH /{id}` |
| `team.py` | `/api/team` | `GET /`, `POST /invite`, `DELETE /{user_id}`, `PATCH /{user_id}/role`, invitations |
| `roles.py` | `/api/roles` | CRUD for system + custom org roles with permissions |

### Products & Licensing

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| `products.py` | `/api/products` | `GET /`, `GET /{id}`, `POST /` (admin) |
| `licenses.py` | `/api/licenses` | `GET /`, `POST /` (admin), `DELETE /{id}` (admin), `GET /check/{slug}` |

### Billing & Subscriptions

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| `plans.py` | `/api/plans` | CRUD for plan tiers (free/pro/enterprise) |
| `subscriptions.py` | `/api/subscriptions` | `GET /me`, admin CRUD, status tracking |
| `billing.py` | `/api/billing` | `POST /checkout`, `POST /webhook`, `POST /portal`, `GET /invoices`, `GET /status` |
| `entitlements.py` | `/api/entitlements` | `GET /`, `GET /check/{feature}` |

### Platform Admin

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| `api_keys.py` | `/api/api-keys` | CRUD (noctus_k_* format, SHA256 hashed) + `GET /api/admin/api-keys` |
| `analytics.py` | `/api/admin/analytics` | `GET /overview`, `GET /revenue`, `GET /tenants` |
| `test_accounts.py` | `/api/admin/test-accounts` | Create/list/deactivate test orgs |
| `audit_logs.py` | `/api/audit-logs` | Org logs + `GET /api/admin/audit-logs` |

### Communication & Settings

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| `notifications.py` | `/api/notifications` | List, unread count, mark read |
| `webhooks.py` | `/api/webhooks` | CRUD + delivery log |
| `settings.py` | `/api/settings` | Platform settings (admin), org settings (user), resolve chain |

---

## Services (8)

| Service | Purpose |
|---------|---------|
| `audit_service.py` | Log user actions for compliance |
| `billing_service.py` | Stripe subscription lifecycle |
| `email_service.py` | Email delivery via Resend |
| `entitlements.py` | Feature gating based on plan limits |
| `notification_service.py` | In-app notification delivery |
| `permissions.py` | Permission checking helpers |
| `stripe_service.py` | Stripe API wrapper (checkout, portal, customers) |
| `webhook_delivery.py` | Webhook event delivery + retry logic |

---

## Response Patterns

- **List**: `paginated_response(data, total, page, page_size)`
- **Single**: `success_response(data)`
- **Delete**: `ok_response(message)`
- **Error**: `{"error": {"code": "...", "message": "...", "details": {...}}}`

---

## Permission Model

**System roles** (org_id IS NULL): `owner`, `admin`, `member`, `viewer`

**Granular permissions**: `team:manage`, `team:read`, `billing:manage`, `billing:read`, `settings:manage`, `settings:read`, `products:access`, `products:access:readonly`, `*`

Custom roles can be created per-organization with any combination of permissions.
