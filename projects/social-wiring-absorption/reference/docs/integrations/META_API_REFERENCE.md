# Meta Graph API — internal reference

> **Scope:** v21.0 Facebook + Instagram **read-only** endpoints used by
> the chatbot's Meta tools. Draft lives here; promotion target is
> `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/meta.md` in noc. See
> `.promotions/meta-integrations.md` for the migration map.
>
> **Pinned version:** `v21.0` (current stable as of Jan 2026). The
> Graph API ages out major versions ~2 years after release — pin
> deliberately via `META_GRAPH_API_VERSION` env var, do not let
> Facebook auto-roll your traffic forward silently.

---

## 1 · OAuth flow

### Token chain (4 steps)

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP                       │ ENDPOINT                       │ NEXT  │
├─────────────────────────────────────────────────────────────────────┤
│ 1. User consent dialog     │ /dialog/oauth                  │ code  │
│ 2. Code → short-lived user │ /oauth/access_token            │ ~2h   │
│    token                   │   (grant_type implicit)        │       │
│ 3. Short → long-lived      │ /oauth/access_token            │ ~60d  │
│    user token              │   ?grant_type=fb_exchange_token│       │
│ 4. User token → page       │ /me/accounts                   │ ∞     │
│    tokens                  │                                │       │
└─────────────────────────────────────────────────────────────────────┘
```

Page tokens (step 4) never expire on their own while the user token
stays valid. **Always use page tokens for per-Page calls**; using the
user token for `/{page_id}/posts` works but counts against the user's
rate-limit pool instead of the page's.

### Scopes (v1 read-only bundle)

| Scope | What it unlocks | App-review needed? |
|---|---|---|
| `public_profile` | `/me` id + name | No |
| `pages_show_list` | `/me/accounts` enumeration | No (dev mode) / Yes (production) |
| `pages_read_engagement` | `/{page_id}/posts` + insights | Yes for production |
| `instagram_basic` | `/{ig_user_id}` + media listing | Yes for production |
| `instagram_manage_insights` | `/{media_id}/insights` | Yes for production |

**Dev mode caveat:** until you submit the app for review and Meta
approves these scopes, only users assigned as **App Admins** /
**Developers** / **Testers** in App Dashboard → Roles can grant
consent. Production traffic from other users will silently bounce.

Posting scopes (NOT in v1):
- `pages_manage_posts` — create FB Page posts
- `instagram_content_publish` — create IG posts/reels

### `auth_type=rerequest`

Our `/api/meta/oauth/start` sends `auth_type=rerequest` so Facebook
re-asks for previously-denied permissions on every flow. Useful while
iterating; you can drop it in production once the scope set is stable.

---

## 2 · Endpoints used by the adapter

### `GET /v21.0/me`

Identity probe. Fields requested: `id,name,email`.

```json
{"id": "10000123456789", "name": "Raphael S."}
```

Used for: `/api/meta/status` display + persisting `user_id` /
`user_name` on the credential row.

### `GET /v21.0/me/accounts`

Lists Pages the user manages. Each row carries its own access token.

Fields: `id,name,category,access_token,fan_count,followers_count,link,tasks`

```json
{
  "data": [
    {
      "id": "1234567890",
      "name": "Imobiliaria One",
      "category": "Real Estate",
      "access_token": "EAA...PAGE_TOKEN",
      "fan_count": 1530,
      "followers_count": 1612,
      "tasks": ["ADVERTISE", "ANALYZE", "CREATE_CONTENT", "MANAGE", "MESSAGING", "MODERATE"]
    }
  ],
  "paging": {"cursors": {"before": "...", "after": "..."}}
}
```

Paginates via `paging.next` / `paging.cursors`. Capped to 100 per page
on the request side; the adapter follows up to 5 pages by default.

### `GET /v21.0/{page_id}/posts`

Page's own posts (vs. `/feed` which includes other people's posts ON
the page; vs. `/published_posts` which excludes drafts/scheduled).

Fields used:
```
id,message,created_time,permalink_url,full_picture,
attachments{title,description,type,media_type,unshimmed_url},
likes.summary(true).limit(0),
comments.summary(true).limit(0),
shares
```

The `.summary(true).limit(0)` trick: ask the edge to include a
`summary.total_count` field in the response body without expanding
the edge body itself. Saves bandwidth on posts with thousands of
likes.

### `GET /v21.0/{post_id}/insights`

Per-post insight metrics. Request body needs `metric` param —
comma-separated list of metric names.

Default metrics requested:
```
post_impressions
post_impressions_unique     (= reach)
post_engaged_users
post_clicks
post_reactions_like_total
post_reactions_love_total
post_reactions_wow_total
post_reactions_haha_total
post_reactions_sorry_total
post_reactions_anger_total
```

Response shape per metric:
```json
{
  "name": "post_impressions",
  "period": "lifetime",
  "values": [{"value": 12345}]
}
```

Some metrics (`post_reactions_by_type_total`) return dict-valued
`value` payloads; the mapper sums them into a flat int.

### `GET /v21.0/{page_id}?fields=instagram_business_account`

Discovers IG Business accounts linked to a Page. Returns
`{"instagram_business_account": {"id": "17841..."}}` or empty.

### `GET /v21.0/{ig_user_id}`

IG Business account metadata. Fields:
```
id,username,name,profile_picture_url,
followers_count,follows_count,media_count,biography,website
```

### `GET /v21.0/{ig_user_id}/media`

IG account's posts (images, videos, carousels). **Does not** include
Stories — those need `/{ig_user_id}/stories` and a 24h-validity caveat.

Fields:
```
id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,
like_count,comments_count
```

`media_type` is one of `IMAGE` / `VIDEO` / `CAROUSEL_ALBUM`.

### `GET /v21.0/{media_id}/insights`

IG media insights. Default metrics:
```
impressions
reach
engagement
saved
video_views     (only meaningful for VIDEO and REELS)
```

---

## 3 · Error envelope

Graph returns errors in a consistent shape, even on `200 OK`:

```json
{
  "error": {
    "message": "Invalid OAuth access token.",
    "type": "OAuthException",
    "code": 190,
    "error_subcode": 460,
    "fbtrace_id": "AnAtKzKqMpqAJqf"
  }
}
```

Our `_meta_api._raise_for_graph_error` lifts these into a typed
`MetaGraphError` with helpers:

| Property | Codes it matches | Meaning |
|---|---|---|
| `is_auth_error` | 102, 190, 467 | Token expired / revoked / wrong scope — re-consent |
| `is_rate_limited` | 4, 17, 32, 613 | Back off; per-app / per-user / per-page limits |
| `code` (raw) | any | Full list at developers.facebook.com/docs/graph-api/guides/error-handling |

`fbtrace_id` is the support-ticket hand-off. Save it in logs when
escalating.

---

## 4 · Setup guide (operator's side)

1. **Create a Meta app**
   - Go to https://developers.facebook.com/apps/
   - Click "Create app" → "Business" type → name it
   - You'll land on the app dashboard

2. **Add products**
   - In the left nav: "Add product"
   - Add **Facebook Login** (Settings → Basic)
   - Add **Instagram Graph API** (Settings → Basic)

3. **Register the OAuth redirect URI**
   - Facebook Login → Settings → "Valid OAuth Redirect URIs"
   - Paste `<META_OAUTH_REDIRECT_URI>` from your `.env`
   - **EXACT string match including scheme and trailing slash if any**
   - For local dev: `http://localhost:8010/api/meta/oauth/callback`
   - For tunnel: `https://<tunnel-host>/api/meta/oauth/callback`

4. **Copy credentials**
   - Settings → Basic → App ID
   - Settings → Basic → App Secret (click "Show", paste your FB
     password to reveal)
   - Paste into `.env`:
     ```
     META_APP_ID=...
     META_APP_SECRET=...
     ```

5. **Test users (dev mode)**
   - App Dashboard → Roles → Test Users (or invite real users as
     Admins / Developers / Testers)
   - Only these can consent until the app passes App Review

6. **Trigger consent**
   - Visit `http://localhost:8010/api/meta/oauth/start` (or the
     tunnel equivalent)
   - Approve the requested scopes
   - You'll be redirected to `/configuracoes?meta=connected`

7. **Validate**
   - `curl http://localhost:8010/api/meta/status` should return
     `adapter: "oauth"` and `pages_count > 0`
   - In the chatbot, ask: "quais paginas do facebook eu administro?"
   - Bot should call `list_facebook_pages` and answer with the list

---

## 5 · Failure modes catalog

| Symptom | Likely cause | Fix |
|---|---|---|
| `/api/meta/status` returns `adapter: "fake"` after consent | CredentialStore row missing — encryption may have failed silently | Check ENCRYPTION_KEY is valid Fernet; check `youtube_crawler.credentials` table for a `meta` row |
| `MetaGraphError code=190` on every call | User token expired or revoked | Visit `/api/meta/oauth/start` again |
| `MetaGraphError code=200` "Permissions error" | Missing scope (e.g. `instagram_basic` denied at consent) | Send the user back through consent with `auth_type=rerequest` |
| `list_instagram_accounts` returns `[]` despite IG account being linked | IG account is **Personal**, not Business / Creator | User must convert to Business at instagram.com → Settings → Account |
| `/me/accounts` returns `[]` despite user managing Pages | `pages_show_list` was denied | Re-consent |
| `MetaGraphError code=4` "Application request limit reached" | App-level rate limit (200 calls/user/hour by default) | Back off; consider App Rate-Limit dashboard at developers.facebook.com |
| OAuth callback throws 400 "Did you mean..." | Redirect URI mismatch — usually trailing slash | Match exactly between `.env` `META_OAUTH_REDIRECT_URI` and what's in App Dashboard |

---

## 6 · Files in this product

| File | Role |
|---|---|
| `app/services/meta/types.py` | Dataclasses + `MetaAdapter` Protocol |
| `app/services/meta/mappers.py` | Graph JSON → dataclass mappers |
| `app/services/meta/_meta_api.py` | httpx plumbing + error parsing + OAuth exchange helpers |
| `app/services/meta/fake_adapter.py` | In-memory adapter (default when no creds) |
| `app/services/meta/oauth_adapter.py` | Live Graph adapter (uses CredentialStore) |
| `app/services/meta/__init__.py` | Factory `get_meta_adapter(org_id, credential_store)` |
| `app/routers/meta_router.py` | `/api/meta/{status,oauth/start,oauth/callback}` |
| `app/services/whatsapp_intake_service.py` (`meta_status`, `list_facebook_*`, `list_instagram_*`, `get_*_insights`) | Chatbot tool handlers |
| `app/services/chatbot_service.py` (7 entries in `_build_tools`) | LLM-facing tool registrations |
| `tests/services/test_meta_integration.py` | 19 mocked tests for mappers / error parser / OAuth / Fake / factory |
