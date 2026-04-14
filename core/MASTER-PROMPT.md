# Core Platform -- Master Prompt

## Purpose

Central auth and administration hub for the NoctusAI multi-product SaaS platform. Manages organizations, users (noctus_users), billing (Stripe), licensing, SSO token exchange, and the admin dashboard. All other products depend on Core for authentication, org management, and notification delivery.

## Architecture

- Schema: `public`
- Backend port: 8000 | Frontend port: 5173
- Tenant key: `org_id`
- Auth: Custom REST API (Supabase Auth + noctus_users table)
- Backend path: `core/backend/app/`
- Frontend path: `core/frontend/src/`

## Key Domains

### Auth and Identity
- **auth** -- login, signup, password reset, token refresh
- **oauth** -- third-party OAuth provider flows
- **sso** -- SSO token creation/verification for cross-product access (5-min short-lived JWT)
- **onboarding** -- first-time org setup wizard

### Organization and Team
- **organizations** -- CRUD for orgs, org settings
- **team** -- invite members, manage org membership (uses noctusai_shared invitations)
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

## Services (8)

audit, billing, email (Resend), entitlements, notifications, permissions, stripe, webhook_delivery

## Permission Model

**System roles** (org_id IS NULL): owner, admin, member, viewer. **Granular permissions**: `team:manage`, `billing:manage`, `settings:manage`, `products:access`, `*`, etc. Custom roles per-organization with any combination.

## Frontend Pages

AcceptInvite, AccountSettings, BillingSettings, CheckoutCancel, CheckoutSuccess, Dashboard, Login, Onboarding, OrgSettings, Pricing, TeamManagement, admin/

## Development Guidelines

- Follow shared patterns from noctusai_shared (auth, roles, invitations, responses, exceptions)
- Router -> Service -> Schema pattern; routers are thin, business logic in services
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- Portuguese for business domain names, English for technical/framework code
- Use `get_current_admin()` for all admin-only routes
- `audit_logs` service must log all sensitive operations (user changes, billing events)
- Webhook delivery uses retry with exponential backoff
- N+1 zero tolerance: use `.in_("id", ids)` for batch reads, `.insert(rows)` for batch writes
- All product notification proxies route through Core's `public.notifications` table

## Testing

```bash
cd core/backend && pytest
```

410 tests across 23 test files.

## Dependencies

- Shared backend: `noctusai_shared`
- Shared frontend: `@noctusai/shared` + `@noctusai/shared/design-system`
- Stripe: checkout, subscriptions, webhooks, customer portal
- Resend: transactional email delivery
- Supabase: Auth, database, RLS
