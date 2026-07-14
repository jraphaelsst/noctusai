# Meta (Instagram / Facebook) Setup — social-wiring

How to enable **per-client Meta connections** in social-wiring. Instagram/Facebook
accounts work exactly like YouTube: **multi-account, attached to each client**,
connected via OAuth and scoped for per-client visualisation.

> **Model:** ONE shared Meta (Facebook) App for the whole platform (the agency's app,
> like the single Google OAuth client YouTube uses) + **per-client connected accounts**.
> The App ID/Secret are shared and set once; each client's Instagram/Facebook account
> is connected through that app and stored per-client (`integration_accounts.client_id`).

---

## Prerequisites (on Meta's side — one-time)

1. A **Facebook App** at <https://developers.facebook.com> (Business type).
2. The app has **Facebook Login** and the Instagram/Pages products added.
3. For live **write** actions (publish, DMs, comment moderation) the app must pass
   **Meta App Review** for the corresponding permissions. *Connecting* and *reading*
   work before review; write actions only take effect once approved.

---

## Step 1 — Set the shared App credentials (in the platform, via UI)

The credentials live in the platform, **not** in `.env`. Set them once as an admin:

1. Open social-wiring → **Configuração → Settings**.
2. In the **Meta App** section (admin-only), enter:
   - **App ID**
   - **App Secret**
   (from `developers.facebook.com` → your app → **Settings → Basic**).
3. Save.

Everything else — OAuth scopes, redirect URI, Graph API version — is auto-configured;
you only set App ID + App Secret. The App Secret is write-only (never shown again after
saving). Stored encrypted-at-rest in `social_wiring.app_integration_config`; a DB value
wins over any `META_APP_ID` / `META_APP_SECRET` env fallback.

> Backend: `PUT /api/settings/meta-app` (admin-gated) → resolved by
> `resolve_meta_app_creds()`. Until this is set, connecting returns
> `[503] META_APP_ID / META_APP_SECRET not configured`.

---

## Step 2 — Register the redirect URI (in the Meta App dashboard)

In your Facebook App → **Facebook Login → Settings → Valid OAuth Redirect URIs**, add
the **per-client** callback:

```
https://social-wiring.noctusai.com/api/integrations/accounts/meta/oauth/callback
```

(Also add the `https://social.noctusai.com/...` variant if that domain is used — Meta
allows multiple redirect URIs.)

> ⚠️ This is the **per-client** callback path (`/api/integrations/accounts/meta/...`).
> It is distinct from the older org-level `/api/meta/oauth/callback` surface.

---

## Step 3 — Connect an account (per client)

1. Open a client (e.g. **One Consultoria**) → **Contas** tab.
2. Click **Conectar** on the **Meta** row.
3. Authorize in the Facebook OAuth popup.
4. The client's Instagram/Facebook account is linked, **scoped to that client**, and is
   **immediately usable** by the posting / insights / DMs / comments features (they all
   read the same per-client store).

Repeat per client — each client gets its own connected Meta account(s), the same way
YouTube and WhatsApp already work.

---

## Requested scopes

The connect flow requests: `instagram_basic`, `instagram_content_publish`,
`instagram_manage_comments`, `instagram_manage_messages`, `instagram_manage_insights`,
`pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
`pages_manage_engagement`, `business_management`.

Read/overview works on connect. Write actions (publish, DM, hide/delete comments) only
take effect once the app passes **Meta App Review** for those permissions.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `[503] META_APP_ID / META_APP_SECRET not configured` | Shared App creds not set | Step 1 — Settings → Meta App |
| `redirect_uri_mismatch` on the Facebook OAuth screen | Callback URI not registered (or wrong domain) | Step 2 — register the exact per-client callback URI |
| Connect works but publish/DM returns "requires app review" | Permissions not yet approved | Submit the app for Meta App Review |
| Meta row shows "em breve" | You're on the **org-level** Integrations/Conexões page, not the per-client client modal | Connect from a **client** (Clientes → open a client → Contas) |

---

## Technical reference

- **Shared creds store:** `social_wiring.app_integration_config` (global key/value,
  encrypted). Set via `PUT /api/settings/meta-app`; read via `resolve_meta_app_creds()`.
- **Per-client OAuth:** `POST /api/integrations/accounts/meta/oauth/start` (body:
  `client_id`) → signed state `{org_id}:{nonce}:{client_id}` → Facebook OAuth →
  `GET /api/integrations/accounts/meta/oauth/callback` → creates an `integration_accounts`
  row scoped to `client_id`.
- **Per-client accounts:** `social_wiring.integration_accounts` (`client_id` FK,
  0..N per client). Live Meta feature routers (posting/insights/DMs/comments) resolve
  the adapter per-account via `get_account_adapter` (account-scoped), reading this store.
- **Org resolution:** endpoints are session-gated; the org is derived from the
  authenticated session (trusted `noctus_users` lookup), never a query parameter.
