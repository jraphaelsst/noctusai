# social-wiring: Multi-Account Integration Credentials

> Governing pattern: memory `feedback_seed_shape_vs_primitive_consume`.
> Shipped: `sw-multi-account-integrations` (2026-05-29).

## What ships

Product-local `integration_accounts` table + service that lets an org
register MULTIPLE credential accounts per provider (e.g. two YouTube
channels, personal + business). WAHA is explicitly excluded —
`whatsapp_connections` already handles that.

Key files:
- `products/social-wiring/backend/migrations/005_integration_accounts.sql`
- `products/social-wiring/backend/app/services/integration_account_service.py`
- `products/social-wiring/backend/app/services/integration_providers.py`
- `products/social-wiring/backend/app/routers/integration_accounts_router.py`

## Design invariants

**Seed-shape-vs-primitive-consume rule (governing pattern):**
- The seed `CredentialStore` is single-row-per-(org, provider). That shape
  does NOT fit multi-row-per-account.
- `integration_accounts` is a product-local multi-account table.
- Encryption (Fernet) is consumed from the seed via
  `credential_vault.require_fernet` — zero inline crypto code in the
  product table layer.
- NOT a fork of the seed Protocol.

**Credential safety invariants:**
1. `encrypted_credential` is never returned in REST responses.
2. `decrypt_credential(account_id, org_id)` is a backend-internal method —
   never called from REST routes.
3. Key-mismatch on decrypt → `CredentialStoreError` → router maps to 503.

**is_default constraint:**
- At most one default per `(org_id, provider)` at any time.
- Implemented at the service layer via `_clear_defaults` before set.
- Supabase: partial unique index `(org_id, provider) WHERE is_default = true`.

**RLS policy:**
- All 4 DML operations (SELECT/INSERT/UPDATE/DELETE) scoped by
  `org_id = auth.jwt() ->> 'org_id'`.
- Service-role bypass for backend admin-client writes.

## v1 provider set

| id | OAuth | Manual key | Notes |
|---|---|---|---|
| `youtube` | yes | no | channel pickup via channels.list at callback |
| `google_drive` | yes | no | read-only scope |
| `gmail` | yes | no | gmail.send scope |
| `meta` | yes | yes | OAuth OR system user token |
| `n8n` | no | yes | webhook_url + optional api_key |

## REST surface

```
GET    /api/integrations/providers                    → provider registry
GET    /api/integrations/accounts[?provider=]         → list
GET    /api/integrations/accounts/{id}                → fetch
POST   /api/integrations/accounts                     → create (manual)
PATCH  /api/integrations/accounts/{id}                → update
PATCH  /api/integrations/accounts/{id}/set-default    → atomic set-default
DELETE /api/integrations/accounts/{id}                → delete
POST   /api/integrations/accounts/youtube/oauth/start → {auth_url, state}
GET    /api/integrations/accounts/youtube/oauth/callback → exchange + create row + redirect
```

## Adding a new provider (3-step recipe)

1. **Registry entry** — add to `PROVIDERS` list in
   `app/services/integration_providers.py`. Set `oauth_supported`,
   `manual_entry`, `manual_key_fields`, `scopes`.

2. **OAuth handler** (if `oauth_supported=True`) — add
   `POST /api/integrations/accounts/{provider}/oauth/start` and
   `GET /api/integrations/accounts/{provider}/oauth/callback`
   in `integration_accounts_router.py`. Reuse the YouTube pattern:
   `GoogleProvider` + PKCE + Redis verifier + `asyncio.run()` for the
   channels.list equivalent.

3. **Manual key fields** (if `manual_entry=True`) — the FE renders the
   `manual_key_fields` list from the registry as a form. No backend route
   changes needed — POST `/api/integrations/accounts` accepts any
   `credential` dict.

## Relationship to existing credential flows

The single-account YouTube OAuth (`/api/settings/youtube/...` +
`social_wiring.credentials` table) continues to work unchanged. This is
an ADDITIVE multi-account path. The two flows coexist; the FE can offer
both ("use your connected channel" vs "pick a channel from your library").

## Extension: WAHA multi-session

WAHA multi-session is handled by `whatsapp_connections` (migration 004),
not by this table. `SUPPORTED_PROVIDER_IDS` and the SQL CHECK constraint
both explicitly exclude `whatsapp`.
