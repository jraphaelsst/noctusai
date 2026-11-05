# 01 — Core Backend Context

> Path: `products/core/backend/app/` · Port: 8000 · 23 routers · 8 services · 31 test files · 392 test fns
> Standard backend patterns (auth, responses, exceptions, N+1): see `../PATTERNS/backend/backend.md`.

## Core-Specific Auth

| Function | Purpose |
|----------|---------|
| `get_current_user(authorization)` | Validates Bearer token via Supabase Auth → `(user, token)` |
| `get_current_admin(authorization)` | Same + checks the PLATFORM flag `noctus_users.role == "admin"` (403 if not), then the platform-admin MFA assurance gate `require_admin_assurance` (policy off/warn/enforce). Platform authz only — NOT a license bypass (`KB § PATTERNS/backend/tenancy-license-gate.md`). Code: `products/core/backend/app/dependencies.py:63-88` (re-verified 2026-11-05). |
| `get_current_user_with_permissions(authorization)` | Fetches org_role + role permissions |
| `create_sso_token(user_id, org_id, ...)` | Short-lived JWT for product access (5 min) |
| `verify_sso_token(token)` | Validates SSO token structure and expiry |

## Routers (23)

**Auth & Identity**: auth, oauth, sso, onboarding
**Org & Team**: organizations, team, roles
**Products & Licensing**: products, licenses
**Billing**: plans, subscriptions, billing (Stripe checkout/webhook/portal), entitlements
**Admin**: api_keys, analytics, test_accounts, audit_logs
**Communication**: notifications, webhooks, settings

## Services (8)

audit, billing, email (Resend), entitlements, notifications, permissions, stripe, webhook_delivery

## Permission Model

**System roles** (org_id IS NULL): owner, admin, member, viewer. **Granular permissions**: `team:manage`, `billing:manage`, `settings:manage`, `products:access`, `*`, etc. Custom roles per-organization with any combination.
