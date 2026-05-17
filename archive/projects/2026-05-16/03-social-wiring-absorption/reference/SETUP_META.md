# Setup Meta (Facebook + Instagram) — operator playbook

> **Status:** code shipped + end-to-end validated against real
> assets on 2026-05-13. **Production-grade auth is via System
> User Token, not OAuth consent.** OAuth flow exists for end-
> user-facing scenarios; for any business customer using Meta
> Business Suite (which is most of them), skip to §B.
>
> Reference: `docs/integrations/META_API_REFERENCE.md` for API
> shape, `OAUTH-PATTERNS-FOR-NOC.md` in noc for the architectural
> rationale.

---

## TL;DR — fastest path to a working bot

If you administer Pages through a **Business Portfolio** (the
default for any commercial Facebook account), do **Path B
(System User Token)** below — it's the only auth that works for
BM-owned assets. Skip Path A entirely.

If you're just connecting your own Personal Page (no Business
Portfolio involved), Path A (User OAuth) works.

---

## Path A — User OAuth (end-user-facing only)

> Skip this section if you're integrating a business customer.
> See Path B.

### A.1 — Create Meta developer app

1. https://developers.facebook.com/apps/
2. **Criar app** → **Tipo: Business** → name it (e.g., "One
   Consultoria Bot")
3. After creation you land on the App Dashboard

### A.2 — Add Use Cases

In the App Dashboard (left sidebar → **Casos de uso**), add:

- **Conectar-se com clientes pelo WhatsApp** (optional — WhatsApp
  Business API)
- **Gerenciar mensagens e conteúdo no Instagram** (required for
  IG access)
- **Gerenciar tudo na sua Página** (required for FB Page access)

Inside each Use Case → **Personalizar** → verify the relevant
read scopes are enabled (`pages_show_list`, `pages_read_engagement`,
`instagram_basic`, `instagram_manage_insights` at minimum).

### A.3 — Configure App Domains + Redirect URIs

#### App Domains
`https://developers.facebook.com/apps/{APP_ID}/settings/basic/`

In **Domínios do app**, add your tunnel host (e.g.
`prostate-radiation-immune-sector.trycloudflare.com`).
Localhost is NOT accepted here (requires a TLD).

#### Valid OAuth Redirect URIs
`https://developers.facebook.com/apps/{APP_ID}/fb-login-for-business/settings/`

Add:
```
https://<your-tunnel-host>/api/meta/oauth/callback
```

### A.4 — Copy credentials → `.env`

From **Configurações → Básico**:
```
META_APP_ID=<App ID>
META_APP_SECRET=<App Secret>
META_OAUTH_REDIRECT_URI=https://<your-tunnel-host>/api/meta/oauth/callback
META_OAUTH_SCOPES=auto
```

### A.5 — Restart + trigger consent

```bash
docker compose up -d --force-recreate app
open https://<your-tunnel-host>/api/meta/oauth/start
```

Approve the scopes. After redirect:
```bash
curl -s http://localhost:8010/api/meta/status | python3 -m json.tool
```

Expect `auth_mode: user_oauth, pages_count > 0`.

### Failure mode: `pages_count: 0` after a clean Path A consent
This is **the** signal that your Pages are owned by a Business
Portfolio. User OAuth can't see them. Go to Path B.

---

## Path B — System User Token (production-grade, recommended)

This is what production deployments should use. The token never
expires and bypasses all the consent/asset-connection drama.

### B.1 — Open Meta Business Suite settings

```
https://business.facebook.com/settings/system-users/
```

Make sure your Business Portfolio is selected in the top dropdown.

### B.2 — Create the System User

Click **Adicionar** (Add) → name it `<YourProduct> Bot` → Role:
**Administrador** → Confirmar.

### B.3 — Assign assets to the System User

The new System User appears in the list. Click it → on the right
panel:

1. **Adicionar ativos** → **Páginas** → check the Page you want
   the bot to manage → access level: **Controle total** → Save
2. **Adicionar ativos** → **Contas do Instagram** → check the
   linked IG Business account → access level: **Controle total**
   → Save

Repeat for any other assets the bot will touch (Ad Accounts,
Catalogs, etc.).

### B.4 — Generate the token

Still on the System User detail page → **Gerar novo token**:

- **Aplicativo:** pick the dev app you created (or will create —
  System User Tokens still need an app context, even though they
  don't go through OAuth)
- **Token nunca expira:** enabled
- **Permissões:** check at minimum:
  - `pages_show_list`
  - `pages_read_engagement`
  - `instagram_basic`
  - `instagram_manage_insights`
  - + any future write scopes you want
- **Gerar token**

A long token (≥250 chars) appears. **Copy it now** — you cannot
re-view it after closing the dialog.

### B.5 — Paste into `.env`

```
META_SYSTEM_USER_TOKEN=EAA...<your token>...
META_APP_ID=<App ID from Path A.4>
META_APP_SECRET=<App Secret from Path A.4>
META_OAUTH_SCOPES=auto    # used for /api/meta/scopes introspection only
```

`META_APP_ID` + `META_APP_SECRET` are still needed for the scope-
discovery endpoint (`/api/meta/scopes` queries
`/{app-id}/permissions` with the App Access Token). They don't
affect the token itself.

`META_OAUTH_REDIRECT_URI` can stay at the default (localhost) —
it's never invoked in System User mode.

### B.6 — Restart + verify

```bash
docker compose up -d --force-recreate app
sleep 5
curl -s http://localhost:8010/api/meta/status | python3 -m json.tool
```

Expected:
```json
{
  "configured": true,
  "adapter": "oauth",
  "auth_mode": "system_user",   ← key signal
  "consent_required": false,
  "user_name": "<your system user name>",
  "pages_count": 1+,
  "instagram_accounts_count": 1+
}
```

### B.7 — Smoke test through chatbot

Open `http://localhost:8090/chat` (or send a WhatsApp message).
Ask:

> "Quantos seguidores temos no Instagram?"

Bot should call `list_instagram_accounts` and answer with the
real number. Or:

> "Lista os últimos 5 posts do Facebook com curtidas e comentários"

Bot calls `list_facebook_posts` and reports real engagement.

---

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `auth_mode: user_oauth, pages_count: 0` | Pages owned by Business Portfolio, user OAuth can't see them | Switch to Path B |
| OAuth consent error "Não é possível carregar a URL" | App Domains field missing the tunnel host | Path A.3 — add to App Domains |
| `META_APP_SECRET_KEY=...` not loading | Wrong env var name (we use `META_APP_SECRET`, no `_KEY` suffix) | Rename in `.env` |
| `configured: false` after restart | `docker compose restart` doesn't reread env. Need `--force-recreate` | `docker compose up -d --force-recreate app` |
| `configured: false` still | env var not in `docker-compose.yml`'s `environment:` block | Verify with `docker compose exec app env \| grep META_` |
| `list_instagram_accounts` returns `[]` | IG account isn't Business/Creator OR isn't linked to a Page in the Portfolio | Convert IG to Business in instagram.com Settings; link it to your Page in BM |
| `meta_graph_error code=190` "Invalid OAuth access token" | System User Token revoked OR System User lost asset access | Re-generate token in BM (Path B.4); verify System User still has Controle total on the assets |
| `meta_graph_error code=200` "Permissions error" on a specific call | Scope wasn't granted (Path A) OR System User Token wasn't generated with that scope (Path B) | Add the scope, re-consent (A) OR re-generate token (B) |

---

## Tunnel URL rotation

Cloudflare Quick Tunnel URLs are ephemeral — they change every
time the tunnel container restarts. When this happens, you must:

1. Update `META_OAUTH_REDIRECT_URI` in `.env` (Path A only — Path
   B doesn't use redirect URIs)
2. Update **App Domains** in Meta Settings → Basic (Path A only)
3. Update **Valid OAuth Redirect URIs** in Facebook Login Settings
   (Path A only)

The `refresh_cf_tunnel.sh` script does (1) automatically for
some env vars but not all — manual touchup for Meta + Google
redirect URIs is currently required. (TODO: extend the script.)

System User Tokens (Path B) are **immune to tunnel rotation** —
they have no redirect URI dependency. Another reason Path B is
the production default.

---

## What's deferred

| Feature | Status |
|---|---|
| Posting to FB Page (text, photo) | Code shape supports it; requires `pages_manage_posts` scope + future write methods on the adapter. Not in v1 |
| Posting to Instagram (photo, reel) | Same shape; requires `instagram_content_publish`. Not in v1 |
| Webhook subscriptions (real-time page/IG updates) | Out of v1; future enhancement |
| Disconnect endpoint (`DELETE /api/meta/oauth/disconnect`) | Not implemented; manually delete the credential row + revoke token in BM |
| TikTok integration | Separate future project (`feat/tiktok-integrations` branch — not started) |
