# 📩 Session findings — Meta (Facebook + Instagram) Graph API adapter

> **Date:** 2026-05-13
> **Source workspace:** `noctusai-youtube-crawler`
> **Source branch:** `feat/meta-integrations`
> **Continuation of:** `SESSION-NOTES_drive-api-2026-05-13.md`
> (the prior Drive API + LLM-counting-trap session)
>
> **Reference scope:** historical / read-before-planning. Code is
> 100% shipped + 19 mocked tests pass + app imports clean +
> chatbot loads all 22 tools (15 prior + 7 Meta). End-to-end
> validation against live Graph API is **gated on the user
> creating a Meta developer app** and pasting credentials per
> `SETUP_META.md` — the live validation log will be appended to
> this file once that happens.

---

## TL;DR

Ported a Meta read-only adapter into the workspace using the
exact same shape as `calendar/` and `drive_api/`: Protocol + Fake +
OAuth-user adapter + factory. Added 7 chatbot tools, an OAuth
bootstrap router, 19 mocked tests, a full internal API reference,
a setup guide, and a promotion manifest. The chatbot can now
answer "quantas páginas eu administro?", "quais os últimos posts
do Facebook?", "métricas do meu Instagram?" once the user
completes the consent flow.

**Three implementation insights worth lifting into noc:**

1. **Meta's token chain is non-obvious — three swaps, not one.**
   `code → short-lived user token → long-lived user token (~60d) →
   page tokens (∞ while user token valid)`. The page tokens are
   what we actually use for per-Page calls; storing them is
   tempting but wrong — they can rotate, so refetch them from
   `/me/accounts` on every adapter construction (one paged Graph
   call, cheap).

2. **`.summary(true).limit(0)` saves bandwidth at the edge.** For
   posts with thousands of likes, asking Graph for
   `likes.summary(true).limit(0)` returns `summary.total_count`
   inline without expanding the edge body. We need the COUNT, not
   the list of likers — same pattern as the
   precompute-stats-in-Python rule, applied to Graph's edge model
   instead of CSV aggregation.

3. **App Review is a real blocker that the adapter cannot solve in
   code.** Without it, `pages_show_list` / `pages_read_engagement`
   / `instagram_basic` / `instagram_manage_insights` only work for
   users explicitly added as App Admins / Developers / Testers.
   This needs to be loud in the setup docs and the failure mode
   table — silent "I see 0 pages" responses confuse the operator
   into thinking the integration is broken.

When this lifts into noc, the promotion manifest at
`.promotions/meta-integrations.md` is the migration map. Target:
`noctusai_lib/integrations/meta/`.

---

## 1 · What landed

### Meta adapter — `app/services/meta/` (new package)

| File | Role | Lines |
|------|------|-------|
| `types.py` | Dataclasses (FacebookPage, InstagramAccount, FacebookPost, InstagramMedia, PostInsights, MetaConnectionStatus) + `MetaAdapter` Protocol | 170 |
| `mappers.py` | Graph JSON → dataclass + default `FIELDS` + default insight metric lists + `parse_graph_datetime` (handles `+0000` shim) | 232 |
| `_meta_api.py` | httpx plumbing (`graph_get`, `graph_paged`), error envelope parser → `MetaGraphError` with `is_auth_error` / `is_rate_limited` helpers, OAuth code+long-lived exchanges | 231 |
| `oauth_adapter.py` | Live adapter — user token for /me + /me/accounts, page token per-page calls, IG account discovery via `instagram_business_account` field | 293 |
| `fake_adapter.py` | In-memory adapter (default when no creds) — `seed(pages, posts_by_page, ig_accounts, media_by_ig_user, post_insights, media_insights, me)` | 106 |
| `__init__.py` | Factory `get_meta_adapter(org_id, credential_store)` → OAuth ⇒ Fake | 85 |

No service-account variant. Meta's identity model requires a real
Facebook user behind every call; SAs are not a Meta concept.

### OAuth bootstrap — `app/routers/meta_router.py`

Routes (mirrors `calendar_router` 1:1):
- `GET /api/meta/status?org_id=...` — adapter introspection +
  probe (/me + count pages + count IG accounts) with structured
  `error` field for "needs reconnection".
- `GET /api/meta/oauth/start?org_id=...` — 302 to Facebook's
  `/v21.0/dialog/oauth` with `auth_type=rerequest` so denied
  permissions are re-asked.
- `GET /api/meta/oauth/callback?code=...&state=...` — exchanges
  code → short-lived → long-lived → /me probe → persist via
  CredentialStore (provider="meta"). Redirects to
  `<frontend>/configuracoes?meta=connected` on success.

### Seven chatbot tools

| Tool | Purpose | Aggregation in Python? |
|------|---------|------------------------|
| `meta_status` | "Is Meta wired up? Who consented?" | n/a |
| `list_facebook_pages` | All managed Pages | n/a |
| `list_facebook_posts(page_id, limit?)` | Recent posts | YES — `engagement_summary` precomputed |
| `get_facebook_post_insights(post_id, page_id?)` | Per-post metrics | n/a (already aggregated by Graph) |
| `list_instagram_accounts` | IG Business accounts linked to Pages | n/a |
| `list_instagram_media(ig_user_id, limit?)` | Recent IG posts | YES — `engagement_summary` + `media_type_counts` precomputed |
| `get_instagram_media_insights(media_id)` | Per-media metrics | n/a |

Same posture as `query_drive_sheet`: **wherever the LLM might be
tempted to count, we count in Python first and hand it the
result.** Total likes across 10 posts? Sum it in the handler, not
in the model.

### Tests

`tests/services/test_meta_integration.py` — 19 tests across:

- `TestMappers` (9 tests) — `parse_graph_datetime` quirks, page /
  post / IG account / media body parsing, insight body flattening
  including the dict-valued-metric case
- `TestGraphErrorParsing` (4 tests) — error envelope detection on
  200 OK responses, auth-error vs rate-limit classification, HTML
  503 fallback
- `TestOAuthExchange` (2 tests) — code-for-token + short-to-long
  call shape via httpx.get mock
- `TestFactory` (2 tests) — Fake fallback when no creds / no
  credential row
- `TestFakeAdapter` (2 tests) — seeded data roundtrip, limit truncation

**19/19 pass in 0.14s.** Full suite is 209/210 (the 1 failure is
`test_e2e_flows::TestTeamFlow::test_list_members_returns_data` —
pre-existing and unrelated to this branch, confirmed via `git stash`).

### Configuration

| `.env.example` field | Default |
|---|---|
| `META_APP_ID` | (empty — operator pastes) |
| `META_APP_SECRET` | (empty — operator pastes) |
| `META_OAUTH_REDIRECT_URI` | `http://localhost:8010/api/meta/oauth/callback` |
| `META_GRAPH_API_VERSION` | `v21.0` |
| `META_OAUTH_SCOPES` | `public_profile,pages_show_list,pages_read_engagement,instagram_basic,instagram_manage_insights` |

### Docs

- `SETUP_META.md` (root) — operator playbook: create app, add
  products, register redirect URI, copy ID+Secret, add yourself as
  tester, consent, validate. Each step terminates in a verifiable
  state.
- `docs/integrations/META_API_REFERENCE.md` — internal API
  reference: token chain diagram, scopes table with App Review
  flags, every endpoint we hit + its fields + sample response,
  error envelope schema with code classification, failure-modes
  catalog with diagnoses. Will move to
  `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/meta.md` on promotion.
- `AGENT.md §3.11` — agent capability description in operator's
  voice; also extends §4 (NOT-implemented limits) with "no Meta
  posting in v1" + "TikTok deferred to future project".
- `.promotions/meta-integrations.md` — migration map: layer
  rationale, seed-first analysis (Q1-Q6), step-by-step lift
  instructions, future work catalog.

---

## 2 · The 3 implementation insights, in depth

### 2.1 — Token chain is non-obvious

Naïve assumption: "OAuth gives us a token, we use the token." Real
Meta:

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP                       │ ENDPOINT                  │ LIFETIME│
├─────────────────────────────────────────────────────────────────┤
│ 1. Consent dialog          │ /dialog/oauth             │ —       │
│ 2. code → short-lived      │ /oauth/access_token       │ ~2h     │
│ 3. short-lived → long-lived│ /oauth/access_token       │ ~60d    │
│    (?grant_type=fb_exchange_token)                              │
│ 4. user token → page tokens│ /me/accounts              │ ∞       │
└─────────────────────────────────────────────────────────────────┘
```

Step 3 doubles the round-trip count but is mandatory — a 2-hour
token is unusable for any production workflow. Step 4 gives you
the page tokens that every per-Page call needs.

**Design decision: don't persist page tokens.** They CAN rotate
under certain conditions (page admin changes, FB security
trigger), and refetching them is one paged Graph call that takes
~150ms. The adapter caches them in-memory per construction so
multiple calls in the same request share one round trip, but
across requests we re-resolve.

This is a noc-level pattern: any OAuth adapter where the upstream
issues short-lived + long-lived + scoped sub-tokens should follow
the same store-the-long-lived-only posture.

### 2.2 — `.summary(true).limit(0)` saves bandwidth

For a post with 5,000 likes, the naïve `?fields=likes` returns
5,000 user records embedded. We need the count, not the names. The
Graph trick:

```
?fields=likes.summary(true).limit(0)
```

`.limit(0)` says "don't return any actual edge items";
`.summary(true)` says "include a summary stanza with total_count".
Response shrinks from 200KB to ~80 bytes.

Same pattern applies to comments + shares. The adapter uses this
in `POST_FIELDS`:

```python
POST_FIELDS = (
    "id,message,created_time,permalink_url,full_picture,"
    "attachments{title,description,type,media_type,unshimmed_url},"
    "likes.summary(true).limit(0),"
    "comments.summary(true).limit(0),"
    "shares"
)
```

The chatbot's `engagement_summary` precompute then sums these
already-aggregated values across N posts in Python. Two layers of
"count it on the server, hand the LLM the number":

1. Graph counts per-post → returns total_count
2. Our handler sums per-page → returns engagement_summary totals

The LLM only ever sees the final aggregated numbers + the human-
readable post bodies. Same anti-fabrication posture as
`query_drive_sheet`.

### 2.3 — App Review is the integration's silent gate

`pages_show_list` / `pages_read_engagement` / `instagram_basic` /
`instagram_manage_insights` all require Meta App Review approval to
work for users outside the App's Roles list. Without review:

- Operator's own account works (because they're the Developer)
- Anyone else gets a successful consent BUT an empty `/me/accounts`
  response — Graph silently filters out anything they're not allowed
  to see, no error envelope, just `{"data": []}`.

This is invisible to the adapter. From the chatbot's perspective,
the response is "you have 0 pages" — which is technically correct
but confusing.

**Mitigation in the failure-modes table:** the API reference doc
calls out "list_facebook_pages returns [] despite managing Pages"
with the dx that `pages_show_list` was denied at consent time and
the user needs to re-consent (the `auth_type=rerequest` flag was
already in the start URL specifically for this case).

**For noc:** any Graph-style integration that depends on scoped
permissions should have a status endpoint that distinguishes
"consent given but permission denied at scope level" from "consent
not yet given" from "fully operational." Our `/api/meta/status`
currently returns the count but doesn't probe per-scope visibility
— a future enhancement.

---

## 3 · What's deferred + why

- **Posting (FB Page post, IG photo/reel)** — requires
  `pages_manage_posts` / `instagram_content_publish` scopes; both
  need App Review per scope; review takes a few days to a week
  per scope. Out of v1. Adapter is structured so adding write
  methods is additive (extend the Protocol, new methods on the
  OAuth adapter only — Fake gets no-ops).
- **TikTok** — user explicitly scoped this out at session start
  ("read only meta, leave tiktok implementation for a future
  project"). Will land as its own branch
  (`feat/tiktok-integrations`) with the same Protocol + Fake +
  OAuth shape. Content Posting API approval is the gating step
  there, equivalent to Meta's App Review for posting scopes.
- **Live validation with real credentials** — gated on the user
  creating a Meta developer app per `SETUP_META.md`. The mocked
  tests cover wire-shape correctness; end-to-end live validation
  is the same posture as the Drive API session
  (`SESSION-NOTES_drive-api-2026-05-13.md` §1) — it gets appended
  here once the credentials are pasted.
- **Webhook subscriptions** — Meta supports realtime updates for
  Page posts / IG comments / messages. Useful for a future "alert
  me when ONE5970 gets a comment" feature, but out of v1.
- **Disconnect endpoint** — `DELETE /api/meta/oauth/disconnect`
  not yet implemented. `SETUP_META.md §10` shows the SQL
  workaround.

---

## 4 · Files + pointers

- Code: `noctusai-youtube-crawler/products/youtube-crawler/backend/app/services/meta/`
- Tool handlers: `app/services/whatsapp_intake_service.py` —
  `meta_status`, `list_facebook_pages`, `list_facebook_posts`,
  `get_facebook_post_insights`, `list_instagram_accounts`,
  `list_instagram_media`, `get_instagram_media_insights`
- Chatbot tools: `app/services/chatbot_service.py` — 7 entries in
  `_build_tools()` + 7 `_tool_*` dispatchers
- Router: `app/routers/meta_router.py`
- Tests: `tests/services/test_meta_integration.py` (19 tests)
- Setup guide: `SETUP_META.md` (workspace root)
- API reference: `docs/integrations/META_API_REFERENCE.md`
- Promotion manifest: `.promotions/meta-integrations.md`
- AGENT.md §3.11
- Companion docs:
  - `SESSION-NOTES_drive-api-2026-05-13.md` — the Drive integration
    that established the OAuth + CredentialStore pattern this
    builds on
  - `SESSION-NOTES_google-integrations-2026-05-12.md` — the
    Calendar + Maps session that established the adapter package
    layout this mirrors
  - `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md` — orthogonal seed-level
    recommendation from the same week

---

## 5 · Promotion-readiness summary

For when this lifts into noc:

| Question | Answer |
|----------|--------|
| Adapter package self-contained? | Yes — 6 files, no cross-product imports |
| Tests cover the noc-side promotion? | Yes — all 19 tests test the adapter in isolation (intake handlers tested separately at chatbot integration layer) |
| Docs ready for INDEX.md insertion? | Yes — `META_API_REFERENCE.md` is in noc's KB format |
| Provider key convention compatible? | Provider key is `"meta"` — flat. Rename to `social.meta` at promotion if noc has namespacing |
| Settings prefix conflicts? | `META_*` doesn't clash with anything in seed or other products |
| Migration cost estimate | Low. Same shape as Drive/Calendar. ~700 LoC adapter + 360 LoC tests. Cut-and-paste with the renames called out in the manifest |

— filed by Claude (Opus 4.7) working in `noctusai-youtube-crawler`
  on branch `feat/meta-integrations`, 2026-05-13, at the user's
  request as historical reference for future expansion into noc.

---

# 📩 ADDENDUM — Live validation saga + System User Token

> **Date:** 2026-05-13 (same day, later)
> **Source branches:** `feat/meta-integrations`, `feat/google-scope-discovery`,
> `integration/oauth-discovery` (merge branch)
> **Status:** ✅ END-TO-END VALIDATED against real One Consultoria
> Facebook Page (146 followers) + @one_consultoria Instagram (9,056
> followers, 1,413 media items)
>
> **TL;DR of the addendum:** the original session shipped Meta code +
> mocked tests, but live validation against the operator's actual
> assets uncovered three sequential blockers we hadn't anticipated.
> Solving them produced **two architectural additions** that every
> future Meta-consuming noc product will inherit:
>
> 1. **Scope auto-discovery** — `META_OAUTH_SCOPES=auto` resolves the
>    request set from Meta's `/{app-id}/permissions` endpoint at
>    consent time, with a kitchen-sink fallback. Removes the per-
>    workspace env-var maintenance burden.
>
> 2. **System User Token auth** — `META_SYSTEM_USER_TOKEN` env var
>    bypasses the OAuth flow entirely. **Required**, not optional,
>    for any product talking to a customer's Business Portfolio-
>    owned assets (which describes virtually every commercial
>    customer in production). User-OAuth tokens silently can't see
>    BM-owned Pages even with all scopes granted.

## A.1 — Three blockers we hit (with diagnoses)

### Blocker 1 — Manual scope maintenance is hostile
**Symptom:** After consent worked, user wanted to add additional
scopes (Messenger, posting, etc.) but the env-var pattern meant
hand-editing `META_OAUTH_SCOPES` every time and hoping the list
stayed in sync across workspaces.

**Diagnosis:** The original code used a hardcoded
`META_OAUTH_SCOPES=public_profile,pages_show_list,...` in the env.
That's a maintenance trap — the scope catalog evolves with each new
Use Case enabled, and env vars drift across environments.

**Resolution (`feat/meta-integrations` second commit, `61b3e02`):**

Added `META_KITCHEN_SINK_SCOPES` constant covering all the
read+write surfaces we might want, plus a `resolve_oauth_scopes()`
helper that:

* When `META_OAUTH_SCOPES` is empty or `"auto"` → calls
  `GET /v21.0/{app-id}/permissions` with the App Access Token
  (`{APP_ID}|{APP_SECRET}`) to discover what scopes the app is
  approved for.
* Falls back to `META_KITCHEN_SINK_SCOPES` when Graph returns
  empty (common in pure dev mode where nothing's been submitted
  for review yet).
* When `META_OAUTH_SCOPES` is an explicit comma-separated list →
  uses it verbatim.

Added a `/api/meta/scopes` introspection endpoint surfacing
**four layers** of state: configured (what we'll request), Graph-
discovered (what app is actually approved for), kitchen-sink
fallback (the in-code default), and granted-to-user (from
`/me/permissions` after consent). Lets the operator audit "did
Meta give me everything I asked for?" without leaving the terminal.

**Lesson for noc:** any OAuth provider that exposes a "list my
app's scopes" endpoint should have an `auto` mode in the consumer.
The `resolve_*_scopes()` shape generalizes — same posture works for
Google (no app-side list endpoint, but tokeninfo gives post-consent
visibility, see the parallel `feat/google-scope-discovery` branch).

### Blocker 2 — Business Portfolio-owned assets are invisible to user OAuth
**Symptom:** Operator (Rapha Souza) completed Meta OAuth consent
successfully. `/api/meta/status` showed `adapter: oauth, user_name:
Rapha Souza` — token stored, identity confirmed. But `pages_count:
0, instagram_accounts_count: 0`. He clearly administers a Facebook
Page (One Consultoria, 146 followers) + Instagram
(@one_consultoria, 9,056 followers).

**Diagnosis (via direct Graph probes):**
1. `GET /me` → returns the user identity correctly ✅
2. `GET /me/permissions` → all 5 scopes granted, 0 declined ✅
3. `GET /me/accounts` → `{"data": [], "summary": {"total_count": 0}}` ❌

Graph is **claiming the user manages zero Pages**, despite the user
clearly administering Pages via Meta Business Suite.

The root cause: the Pages are owned by a **Business Portfolio**
(`BM Gilson Tangerino`), not directly by the personal FB account.
In modern Meta dev mode, **BM-owned Pages are gated** from user-
OAuth tokens — Graph silently filters them out regardless of
`pages_show_list` being granted. This is a deliberate Meta policy:
the user-OAuth flow is intended for end-user-facing apps (each user
consents to their own Pages), not for server-to-server backend
automation against business assets.

We attempted to "connect the Page to the app" in BM Settings, but
that flow in modern Meta UI **only supports Ad Accounts**, not
Pages or IG. The asset-connection mechanism for Pages/IG happens at
a different layer (System Users), not at the App-Asset layer.

**Lesson for noc:** any product whose customers operate Pages
through Meta Business Suite (which is the dominant pattern for any
non-personal business) **must support the System User Token path**.
User-OAuth alone is insufficient for production. Document this
prominently — failure mode is silent (no error, just empty data).

### Blocker 3 — Resolution: System User Token (Path B)
**Resolution (`integration/oauth-discovery` branch, commit
`559dcf7`):**

Refactored `MetaOAuthAdapter._user_token()` to be auth-mode-aware:

```python
def _user_token(self) -> str:
    # 1) Prefer System User Token if configured (production path)
    if settings.meta_system_user_token:
        return settings.meta_system_user_token
    # 2) Fall back to OAuth credential store (end-user path)
    stored = self._store.get(org_id=..., provider="meta")
    return stored.tokens["access_token"]
```

Added `auth_mode` property returning `"system_user"` /
`"user_oauth"` / `"none"`. Surfaced on `/api/meta/status` so the
operator can immediately see which mode is active.

Factory `get_meta_adapter()` now prioritizes System User Token over
OAuth credential row. System User mode doesn't require `org_id` or
`credential_store` — the token is workspace-global (one System User
serves all consumers in the workspace).

**Operator setup (in BM, ~5 min):**
1. BM Settings → Usuários do sistema → Adicionar → role: Admin
2. Open the new system user → Adicionar ativos → assign Pages + IG
   accounts with **Controle total**
3. Gerar novo token → pick the app + scopes → **token never expires
   while system user retains access** → copy
4. Paste into `.env` as `META_SYSTEM_USER_TOKEN=EAA...`
5. `docker compose up -d --force-recreate app`

**Live validation (real numbers):**
```
auth_mode:                system_user
user_name:                Raphael (the System User identity)
pages_count:              1
instagram_accounts_count: 1
Facebook Page:            One Consultoria, 146 followers
Instagram:                @one_consultoria, 9056 followers, 1413 media
Latest FB posts:          real engagement (likes 1-5)
Latest IG media:          real engagement (likes 29-112, comments 2-25)
```

**Lesson for noc:** when promoting `noctusai_lib.integrations.meta`,
ship **two auth backends** from day one: SystemUserAuth (default)
and UserOAuthAuth (carve-out). Configure via a shared `MetaAuth`
protocol the adapter accepts at construction. Document the choice
matrix:

| Customer profile | Recommended auth |
|---|---|
| Personal FB account, manages a few Pages directly | UserOAuth |
| Business with Meta Business Suite + Portfolio | **SystemUser** (mandatory) |
| Server-to-server automation, no human consent needed | **SystemUser** |
| White-label SaaS, each tenant connects their own | UserOAuth per tenant |

## A.2 — The infrastructure bugs we surfaced and fixed

While validating, three workspace-level bugs surfaced. All small,
all now patched on the integration branch — but worth lifting into
noc's seed templates so future workspaces don't reinvent them.

### A.2.1 — `.env` quoting rule

**Bug:** `start.sh` does `source .env`. Bash interprets the first
space as the end of the assignment, then tries to execute the rest
as commands. Hit by `GOOGLE_OAUTH_SCOPES` (space-separated URL
list) — produced cryptic "No such file or directory" errors.

**Fix (commit `0eee3ba`):** Top-of-file comment in `.env.example`
documenting the rule + `GOOGLE_OAUTH_SCOPES` shipped quoted by
default.

**For noc:** `templates/seed-workspace-docker/.env.example` should
ship with the same comment block. Better: `start.sh` should use a
more robust parser (xargs export, python-dotenv via subprocess)
instead of `source` so users don't have to know about shell
quoting.

### A.2.2 — Docker Compose env passthrough gap

**Bug:** `docker compose restart app` doesn't re-read env vars
(env is read at container CREATION). Even
`docker compose up -d --force-recreate app` won't surface env vars
that aren't in the compose service's `environment:` block — the
`.env` file is read by **compose itself for variable
interpolation**, not piped wholesale into the container.

**Symptom:** Pasted `META_APP_ID` + `META_APP_SECRET` into `.env`,
restarted with `--force-recreate`, `/api/meta/status` still showed
`configured: false`. The container had no Meta env vars.

**Fix (commit `6ff76d5`):** Added every `META_*` and
`GOOGLE_OAUTH_SCOPES` to `docker-compose.yml`'s `environment:`
block with `${VAR:-default}` interpolation.

**For noc:** `templates/seed-workspace-docker/docker-compose.yml`
should have a clear pattern for env passthrough + a comment
reminding maintainers that adding a new env var requires updating
BOTH `.env.example` AND the compose env block.

### A.2.3 — `refresh_cf_tunnel.sh` doesn't update OAuth redirect URIs

**Bug:** The tunnel-refresh script updates `TUNNEL_HOSTNAME`,
`YOUTUBE_REDIRECT_URI`, `WAHA_WEBHOOK_URL`, `FRONTEND_BASE_URL`.
It doesn't know about `META_OAUTH_REDIRECT_URI` or
`GOOGLE_OAUTH_REDIRECT_URI`. Refreshing the tunnel left those
pointing at the dead URL.

**Workaround applied this session:** manual `python3 -c "..."` to
patch the two redirect URIs in `.env`.

**For noc:** the seed's tunnel-refresh script should be
parameterized — each product declares its OAuth redirect env vars,
the script iterates and updates them. Pseudo-code:

```bash
OAUTH_REDIRECT_VARS=(
  YOUTUBE_REDIRECT_URI
  META_OAUTH_REDIRECT_URI
  GOOGLE_OAUTH_REDIRECT_URI
)
for var in "${OAUTH_REDIRECT_VARS[@]}"; do
  # extract the path segment from current value, prepend new tunnel
done
```

Alternative: products that follow the convention `<TUNNEL>/api/{provider}/oauth/callback` could just have the script regex-replace the host portion.

## A.3 — Production-readiness checklist (for the next adopter)

When promoting Meta to noc and a sibling product picks it up, the
adopter should:

- [ ] Document the **System User Token requirement** for any
      customer using Meta Business Suite (which is most commercial
      customers). User OAuth is the wrong default for prod.
- [ ] Inherit the `META_OAUTH_SCOPES=auto` convention. Reference
      the `META_KITCHEN_SINK_SCOPES` constant; extend per-product
      as new use cases arise.
- [ ] Expose `/api/{provider}/scopes` introspection. Operators
      need to audit consent gaps without ssh access.
- [ ] Wire `auth_mode` into the status endpoint. Logging "consent
      required: false" without distinguishing system-user vs
      user-oauth modes confuses operators.
- [ ] Test with a real Business Portfolio asset, not just a
      personal account. The dev-mode behavior diverges from prod
      behavior here — empty `/me/accounts` is the signal.
- [ ] If using the tunnel for OAuth callbacks, ensure
      `refresh_cf_tunnel.sh` (or equivalent) updates the OAuth
      redirect URIs in `.env`, not just the YouTube/WAHA ones.

## A.4 — Files added/modified by the addendum work

| File | Role | Branch |
|---|---|---|
| `app/services/meta/_meta_api.py` | + `META_KITCHEN_SINK_SCOPES`, `app_access_token()`, `discover_app_permissions()`, `resolve_oauth_scopes()` | `feat/meta-integrations` |
| `app/routers/meta_router.py` | + `/api/meta/scopes` endpoint, `auth_mode` in status, resolver in oauth_start | `feat/meta-integrations` + `integration/oauth-discovery` |
| `app/services/meta/oauth_adapter.py` | + `auth_mode` property, dual-source `_user_token()` | `integration/oauth-discovery` |
| `app/services/meta/__init__.py` | Factory picks system_user → user_oauth → fake | `integration/oauth-discovery` |
| `app/config.py` | + `meta_system_user_token`, `meta_oauth_scopes="auto"` | `integration/oauth-discovery` |
| `docker-compose.yml` | + all META_* env vars + GOOGLE_OAUTH_SCOPES passthrough | `integration/oauth-discovery` |
| `tests/services/test_meta_integration.py` | +8 scope tests, +4 system_user tests (31 total) | both branches |

## A.5 — Commits in chronological order (for noc-side review)

| Commit | Description |
|---|---|
| `71707ea` | feat: meta read-only graph api adapter (original) |
| `61b3e02` | feat(meta): auto-discover scopes from app permissions endpoint |
| `0eee3ba` | fix(env): document quoting rule + ship quoted GOOGLE_OAUTH_SCOPES |
| `f7613e5` | merge: combine meta + google scope discovery for integration testing |
| `6ff76d5` | fix(compose): pass Meta + GOOGLE_OAUTH_SCOPES env vars into app container |
| `559dcf7` | feat(meta): support System User Token auth for BM-owned assets |

— addendum filed by Claude (Opus 4.7) in `noctusai-youtube-crawler`
  on branch `integration/oauth-discovery`, 2026-05-13 evening, at
  the user's request after live validation against real assets
  succeeded.
