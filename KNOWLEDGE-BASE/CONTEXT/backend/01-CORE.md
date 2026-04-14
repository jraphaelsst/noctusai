# 01 — Core Backend Context

> Path: `core/backend/app/` · Port: 8000 · Tests: 23 files
> Standard backend patterns (auth, responses, exceptions, N+1): see CLAUDE.md

## Core-Specific Auth

| Function | Purpose |
|----------|---------|
| `get_current_user(authorization)` | Validates Bearer token via Supabase Auth → `(user, token)` |
| `get_current_admin(authorization)` | Same + checks `noctus_users.role == "admin"` (403 if not) |
| `get_current_user_with_permissions(authorization)` | Fetches org_role + role permissions |
| `create_sso_token(user_id, org_id, ...)` | Short-lived JWT for product access (5 min) |
| `verify_sso_token(token)` | Validates SSO token structure and expiry |

## Routers (20)

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
