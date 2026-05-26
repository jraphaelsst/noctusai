# OAuth integration patterns — cross-provider reference (NoctusAI)

> **Purpose.** Authoritative, self-contained reference for how OAuth-style
> integrations are architected on the NoctusAI platform: the layer model,
> the five recurring patterns, the per-provider gotchas (G1-G6), the Meta
> token-chain + auth-mode choice matrix, the Google-vs-Meta scope-discovery
> architectural diff, and a cross-provider operator setup-guide template.
>
> **Provenance (dated architectural fact, not a live dependency).** The
> patterns below were discovered + live-validated across four OAuth
> integrations (YouTube, Google Calendar/Drive/Maps, Meta Facebook/Instagram)
> in the externally-developed `noctusai-youtube-crawler` seed-workspace
> during 2026-05-12/13, then absorbed into the noc seed during
> `social-wiring-absorption` + `seed-hardening-from-youtube-crawler`
> (2026-05-03 → 2026-05-16). This doc is the durable distillate — the
> source workspace is **not** a durable reference; the seed code (cited by
> module path below) is.
>
> **Status legend** (per pattern / takeaway):
> - ✅ **in-seed** — shipped in `noctusai_lib`; cited by path. Consume it.
> - 📋 **operator** — a runbook/setup fact, not code.
>
> (All ⏳ gaps were closed 2026-05-17 — see §7. Legend keeps ✅/📋 only.)

---

## 1 · The 5-layer OAuth model

Every OAuth integration decomposes into five layers. Keep them as separate
modules so consumers can swap or extend one without touching the others.

```
Layer 4  Tool surface       chatbot tools / MCP handlers / REST endpoints
Layer 3  Adapter            Protocol + Fake + Real + factory  (seed-fake-real shape)
Layer 2  Auth abstraction   token resolution (env|store) · refresh · auth_mode
Layer 1  Scope catalog      kitchen-sink (in code) · resolver "auto"|explicit · introspection
Layer 0  Credential store   Fernet at rest · one row per (org_id, provider)
```

**Where each layer lives in the seed today:**

| Layer | Seed home | Status |
|---|---|---|
| 0 Credential store | `noctusai_lib.security.token_store` (`CredentialStore` Protocol + `FakeCredentialStore` + `SupabaseCredentialStore` + `make_credential_store`) + `noctusai_lib.security.encrypted_tokens` (`encrypt`/`decrypt`/`rotate_key`/`MultiKeyDecryptor`) | ✅ |
| 1 Scope catalog | Google: `noctusai_lib.integrations.google_scopes` · Meta: `META_KITCHEN_SINK_SCOPES` + `resolve_oauth_scopes` + `discover_app_permissions` in `noctusai_lib.integrations.meta` · Cross-provider: `ScopeResolver` Protocol + `Google/Meta/FakeScopeResolver` + `make_scope_resolver` in `noctusai_lib.security.oauth.scopes` · named bundles in `noctusai_lib.integrations.oauth_bundles` | ✅ per-provider ∧ ✅ cross-provider `ScopeResolver` Protocol ∧ ✅ named bundles |
| 2 Auth abstraction | Generic dance: `noctusai_lib.security.oauth` (`OAuthProvider` Protocol + `GoogleProvider` + `FakeOAuthProvider` + `make_oauth_provider` + `oauth_router`). Meta dual-auth: `MetaOAuthAdapter.auth_mode` in `noctusai_lib.integrations.meta` | ✅ |
| 3 Adapter | `integrations/{google_calendar,google_drive,google_maps,meta,whatsapp,youtube,media}` — all Protocol+Fake+Real+factory | ✅ |
| 4 Tool surface | Consumer-side (product chatbot tool registry / MCP). Meta ships a read-only introspection router (`make_meta_router` → `/api/meta/{status,scopes}`) | ✅ for introspection; tool wiring is per-consumer |

---

## 2 · The 5 patterns

### Pattern 1 — Scope auto-discovery (`auto` mode) ✅ per-provider ∧ ✅ unified

**Problem.** Per-workspace `.env` scope lists drift; operators forget one
environment; prod diverges from dev silently.

**Pattern.** `<PROVIDER>_OAUTH_SCOPES=auto` (default in `.env.example`).
`"auto"`/empty → discover-or-kitchen-sink; explicit list → verbatim. The
kitchen-sink list lives **in code** (versioned with the adapter), never in env.

- **Meta** (`resolve_oauth_scopes` in `integrations/meta/_meta_api.py`):
  `"auto"` → `GET /{app-id}/permissions` with the App Access Token
  (`{APP_ID}|{APP_SECRET}`) via `discover_app_permissions`; empty Graph
  result → `META_KITCHEN_SINK_SCOPES`.
- **Google** (`resolve_google_scopes` in `integrations/google_scopes.py`):
  no app-side scope-list endpoint exists → always the in-code
  kitchen-sink unless explicit.

**✅ Unified.** `noctusai_lib.security.oauth.scopes` ships the
`ScopeResolver` Protocol (`provider` / `resolve` /
`list_app_scopes() -> list[str] | None` / `discover_granted` /
`diagnose`) with `GoogleScopeResolver` (delegates to
`integrations.google_scopes`; `list_app_scopes()` → `None`),
`MetaScopeResolver` (delegates to `integrations.meta._meta_api`;
`list_app_scopes()` → Graph list or `None` in dev mode),
`FakeScopeResolver`, and `make_scope_resolver(provider, ...)`. The Real
impls **delegate to, do not duplicate**, the per-provider functions.
Exported from `noctusai_lib.security.oauth.__all__`.

### Pattern 2 — Dual auth backends (service-style + user-OAuth) ✅

**Problem.** End-user OAuth flows are designed for "each user consents to
their own data". Server-to-server automation against **business assets**
needs a different identity. Wrong choice = silent empty data (no error).

**Pattern.** The adapter accepts EITHER a long-lived service-style token
OR a stored OAuth credential. **Resolution priority: service-style first,
user-OAuth fallback.** An `auth_mode` discriminator is surfaced on the
status endpoint.

✅ Shipped for Meta: `get_meta_adapter(system_user_token=… | resolver=…,
org_id=…)` → priority `system_user` → `user_oauth` → `Fake`;
`MetaOAuthAdapter.auth_mode` reports the active mode; `make_meta_router`
surfaces it on `/api/meta/status`. Google Calendar mirrors this with
service-account vs OAuth-user via `get_calendar_adapter(resolver)`
(adapter kind chosen from the credential dataclass).

**Auth-mode choice matrix** (📋 — bake into every setup guide):

| Customer profile | Recommended auth |
|---|---|
| Personal account, manages own data directly | UserOAuth |
| Business uses provider "Business Suite" / "Portfolio" / "Workspace" | **Service-style** (Meta System User Token / Google Service Account) — *mandatory*, not optional |
| Server-to-server automation, no human in the loop | **Service-style** |
| White-label SaaS, each tenant connects their own account | UserOAuth per tenant |

> **Why service-style is the default recommendation, not the carve-out.**
> Meta Business-Portfolio-owned Pages are silently filtered from
> `/me/accounts` for user-OAuth tokens **even with every scope granted**
> — `{"data": [], "summary": {"total_count": 0}}`, no error envelope.
> This was discovered live: operator consented OK, `/api/meta/status`
> showed `user_name` correct but `pages_count: 0` for a Page they clearly
> administered (BM-owned). User-OAuth alone is the wrong prod default for
> any commercial customer.

### Pattern 3 — Single-consent multi-scope bundling ✅

**Problem.** Calendar + Drive + Userinfo each requiring a separate consent
step is hostile UX.

**Pattern.** Bundle related scopes into ONE consent flow. All consuming
adapters read the **same** credential row (e.g. `provider="google_calendar"`)
with the scope list = **union of every consuming adapter's needs**; each
adapter slices its own scopes at API-call time.

✅ The mechanics work today (Google Drive's `oauth_adapter` reuses the
Calendar credential row + adds Drive scopes on the same consent — see
`integrations/google_drive` reader surface). ✅ **Named bundles shipped:**
`noctusai_lib.integrations.oauth_bundles` ships
`GOOGLE_BUNDLE_PRODUCTIVITY` / `GOOGLE_BUNDLE_COMMUNICATIONS` /
`META_BUNDLE_READ_ONLY` / `META_BUNDLE_FULL_SOCIAL` + `resolve_bundle(name)`
+ `bundle_names()` (opt-in-by-name in product config). Each bundle is a
**named subset of the already-shipped kitchen-sink list** (single source
of truth; a startup `AssertionError` enforces the subset invariant — a
bundle naming a scope absent from its kitchen-sink fails loudly).

### Pattern 4 — Post-consent introspection ✅

**Problem.** "Pages count: 0" / "0 events" is ambiguous — denied scope?
no assets? BM gating? broken adapter? Logs don't disambiguate.

**Pattern.** Every provider exposes a "what did the user actually grant?"
probe, surfaced on a debug endpoint as a 4-layer view:

```json
{ "configured": [...], "kitchen_sink_default": [...],
  "granted_to_user": [...] | null, "declined_by_user": [...] | null,
  "coverage_pct": 100.0 | null, "note": "<actionable>" }
```

`coverage_pct < 100` ⇒ operator knows to re-consent OR fix the consent-
screen config (Google) OR check Use-Case asset connections (Meta) —
**without ssh / log access**.

✅ Shipped:
- **Meta:** `GET /me/permissions` → `[{permission, status}]`; surfaced via
  `make_meta_router` `/api/meta/scopes`.
- **Google:** `discover_granted_scopes(access_token)` +
  `diagnose_consent_screen_gaps(requested, granted)` in
  `integrations/google_scopes` (probes `oauth2/v3/tokeninfo`); router at
  `integrations/google_scopes_router.py`.

A configured-vs-discovered debug endpoint (no user-data leak) is a
required component of every OAuth integration's status surface.

### Pattern 5 — CredentialStore (Fernet at rest) ✅ FORMALIZED

One row per `(org_id, provider)`; token bundle JSON-serialized +
Fernet-encrypted with `ENCRYPTION_KEY`; UPSERT on re-consent;
decrypt-on-read, **fail loudly** on key mismatch (`CredentialDecryptError`).

✅ **Done.** Lifted into `noctusai_lib.security.token_store`
(`CredentialStore` Protocol + `FakeCredentialStore` +
`SupabaseCredentialStore` + `make_credential_store` + `StoredCredential`).
Fernet primitives in `noctusai_lib.security.encrypted_tokens`
(`encrypt`/`decrypt`/`generate_key`/`rotate_key`/`MultiKeyDecryptor` —
multi-key supports rotation). The single-product `credential_store.py`
copy the source notes referenced no longer exists in the platform — this
is the canonical home. Pair `oauth_router(... on_callback=…)` with
`encrypt(...)` inside the callback hook to persist at-rest-encrypted
tokens (see `security/oauth/__init__.py` docstring).

---

## 3 · Gotchas catalog (G1-G6) — 📋 operator / infra

Real bugs hit during live validation; fixes lifted into the seed-workspace
templates + the house container model.

| # | Gotcha | Fix / where addressed |
|---|---|---|
| **G1** | Bash `source .env` aborts silently on unquoted spaces (Google scope lists are the canonical offender — space-separated URLs). | `.env.example` ships the rule comment + values quoted by default. Robust parser (python-dotenv via subprocess) preferred over `source`. |
| **G2** | `docker compose up` does NOT pipe `.env` wholesale into the container. Every var the container needs must appear in the service `environment:` block. Adding a var is a **two-file change** (`.env.example` + compose `environment:`). | Documented; house compose pattern uses `${VAR:-default}` interpolation. |
| **G3** | Env vars load at container **creation**, not start. `docker compose restart` keeps the old env — use `up -d --force-recreate <service>` for env changes. | Operator runbook fact. |
| **G4** | Tunnel-refresh must update **every** OAuth redirect URI env var, not just YouTube/WAHA. Refreshing left `META_OAUTH_REDIRECT_URI` / `GOOGLE_OAUTH_REDIRECT_URI` pointing at a dead URL. | Refresh script parameterizes: products declare redirect env vars, the script iterates. Subsumed by the house single-URL model (one tunnel host, path-routed). |
| **G5** | Tunnel-refresh "preserve non-localhost as explicit override" logic breaks when the previous value was itself a stale `*.trycloudflare.com` URL. | Detect ephemeral tunnel hosts (`*.trycloudflare.com`) as overridable; track tunnel-bound vars at workspace-init. |
| **G6** | Providers reject `localhost` in dashboard domain fields (Meta requires a TLD; Google has per-scope verification). | Setup docs ship **tunnel-first** (cloudflared from the start; register the tunnel host). Localhost is a non-starter for any provider whose dashboard requires a TLD. Cloudflare quick-tunnels MUST pin `--protocol http2` (QUIC/UDP dies ~5min behind NATs — see containerization KB). |

---

## 4 · Meta token chain + Graph specifics — 📋 reference

### 4.1 Token chain is three swaps, not one

```
1. consent dialog       /dialog/oauth                          —
2. code → short-lived    /oauth/access_token                    ~2h
3. short → long-lived    /oauth/access_token?grant_type=         ~60d
                          fb_exchange_token
4. user token → page     /me/accounts                           ∞ (while #3 valid)
   tokens
```

**Design rule (in `MetaOAuthAdapter`): persist the long-lived user token
only.** Page tokens (step 4) CAN rotate (admin change, FB security
trigger) — refetch from `/me/accounts` on every adapter construction
(one cheap paged call, ~150ms; cached in-memory per construction, not
across requests). Generalizes: any OAuth upstream issuing
short+long+scoped-sub tokens → store-the-long-lived-only.

### 4.2 `.summary(true).limit(0)` — count without expanding the edge

For a post with 5,000 likes, `?fields=likes` returns 5,000 records. We
need the count. `?fields=likes.summary(true).limit(0)` → ~80 bytes with
`summary.total_count` inline (used in `POST_FIELDS`). Same anti-fabrication
posture as the precompute-stats-in-Python rule (§5, `compute_content_stats`),
applied to Graph's edge model. Two count layers: Graph counts per-post →
handler sums per-page → LLM only ever sees final aggregates.

### 4.3 App Review is a silent gate the adapter cannot solve

`pages_show_list` / `pages_read_engagement` / `instagram_basic` /
`instagram_manage_insights` only work for users on the App's Roles list
(Admin/Dev/Tester) until App Review approves them. Outside reviewers get
a **successful consent** but empty `/me/accounts` — `{"data": []}`, no
error. Distinguish "consent-but-permission-denied" from "consent-not-given"
from "operational" on the status endpoint. `auth_type=rerequest` is in the
Meta start URL specifically so denied perms are re-asked on re-consent.

### 4.4 Google ↔ Meta scope-discovery architectural diff

| | Meta | Google |
|---|---|---|
| App scopes catalogued via API? | ✅ `GET /{app-id}/permissions` (App Access Token) | ❌ Consent-Screen config not API-exposed |
| Auto-allow unregistered scopes? | ✅ dev mode for testers/admins (Graph silently filters) | ❌ Google blocks scopes not in the Consent Screen |
| Post-consent introspection? | ✅ `GET /me/permissions` (granted/declined) | ✅ `oauth2/v3/tokeninfo` (granted scope string) |
| Kitchen-sink safety | High (FB auto-filters) | **Low** — operator MUST add every scope to GCP Console Consent Screen *first*; an unregistered scope produces a per-scope "unverified app" warning |

**Implication.** The auto-discovery pattern is **provider-shaped, not
generic** — the future unified `ScopeResolver` (§7) needs a
`list_app_scopes()` returning `None` for Google.

**Google operator step (📋 mandatory).** Every kitchen-sink scope
(`openid`, `userinfo.email`, `userinfo.profile`, `calendar`,
`calendar.events`, `drive.readonly`, `drive.file`,
`drive.metadata.readonly`) must be added in GCP Console → APIs & Services
→ OAuth Consent Screen → Scopes **before** the consent flow can request
it. Extending (e.g. Gmail): add in GCP Console → add literal to the
kitchen-sink constant → re-consent. `coverage_pct < 100` after a consent
flow is the signal a scope is missing from GCP config.

### 4.5 Two Drive access paths (📋 — recommend share-with-SA first)

| Path | Setup | Sees | Recommend when |
|---|---|---|---|
| **Share folder with SA email** | Right-click folder in Drive → Share → paste SA email → Viewer | Whatever was shared, recursively | Small set of folders. **No GCP changes** — the default quick-start. |
| **OAuth user consent** | `/api/.../oauth/start` + GCP redirect-URI registration + browser consent | The user's whole Drive (`drive.readonly`) | Whole-Drive coverage OR multiple products without micromanaging shares |

Surface adapter-side `canDownload`/`canRead` capability in the tool
response so the bot distinguishes "permission denied" from "no tool"
from "404" (an honest "no tool yet" reply once read as a permission error).

---

## 5 · Cross-product chatbot takeaways

From the multichannel-chatbot + Drive sessions. **Almost all are ✅
already in the seed** (absorbed via `social-wiring-absorption` 2026-05-16).
Verify-the-seed-ships-it applied — paths cited.

| # | Takeaway | Status / seed home |
|---|---|---|
| 5.1 | **WAHA duplicate-event race** — WAHA subscribes both `message` AND `message.any`; without dedup every chatbot run doubles. | ✅ `noctusai_lib.integrations.whatsapp` — `WebhookDedup` Protocol + `RedisWebhookDedup` (SETNX pre-filter) + `InMemoryWebhookDedup` + `get_webhook_dedup`; DB UNIQUE backstop = `noctusai_lib.domain.chatbot.message_store` (`UNIQUE(provider_message_id)`). |
| 5.2 | **WhatsApp `@lid` hides the phone** — phone-form whitelists silently reject `@lid` senders; same user differs per chat. | ✅ `integrations/whatsapp.lid_auth` — `is_authorized` (3-tier), `resolve_canonical_session`, `remember_lid_phone`, `get_lid_phone_cache` (Protocol+Fake+Real), `extract_resolved_remote`. |
| 5.3 | **Vendor-emitted URLs need rewriting inside docker** — WAHA emits `localhost:3000` media URLs unreachable from the `app` container. | ✅ `integrations/whatsapp` — `rewrite_vendor_media_url` + `WahaClient(external_base_url=…, base_url=…)`; `get_whatsapp_client(external_base_url=)` factory seam. |
| 5.4 | **Durable per-message audit log paid for itself** — `conversation_messages.structured_payload` was the primary debugging surface (3 diagnoses from one SELECT). | ✅ `noctusai_lib.domain.chatbot.message_store` — `MessageStore` Protocol + `SupabaseMessageStore`, `structured_payload` column, `provider_message_id` dedup, migrations shipped. |
| 5.5 | **Vision-model refusals are a recurring shape** — narrow prompts make vision refuse (real-estate prompt refused a CNH). Refusal-detect + retry. | ✅ `noctusai_lib.integrations.llm.refusal` — `looks_like_refusal(text)` + `analyze_image_with_refusal_retry(...)` (exported from `llm.__init__`). |
| 5.6 | **LLM counting is unreliable on long structured data** — precompute aggregates in Python; tool description forbids manual recount (CSV: LLM said 35, real 183/176). | ✅ `noctusai_lib.integrations.google_drive.compute_content_stats` (also re-exported by `domain.chatbot.content_stats`). Generalizes (transcripts→wpm, digests→counts, calendar→hours). |
| 5.7 | **SPA frontends need nginx SPA fallback** — React Router 404s on deep direct loads without `try_files … /index.html`. | ✅ Subsumed by the **house single-container model**: uvicorn serves the built SPA via the seed factory `serve_spa`/`SERVE_SPA_DIR` seam (SPA fallback ⊂ `serve_spa`). No per-product nginx. See containerization KB §12a. |
| 5.8 | **Path-based reverse proxy beats per-service tunnels** — one URL, one set of OAuth callbacks, one webhook URL vs constant 3-URL rotation. | ✅ Subsumed by the house model: same-origin SPA via vite-factory `window.location.origin` injection + the mandatory profile-gated `<slug>-tunnel`. Standalone `proxy/` is redundant under the house container model. |
| 5.9 | **Prompt over-obedience** — LLMs follow narrow refusal/scope instructions even when they hurt the goal; frame prompts around input TYPES the system handles, not one caller's narrow case. | ✅ Mechanically: `domain.chatbot.openai_orchestrator` takes `system_prompt` from the consumer (no hardcoded real-estate prompt). ✅ **Shared fragment shipped:** `noctusai_lib.domain.chatbot.prompt_fragments` ships `URL_IMMUTABILITY_FRAGMENT` (generic — auth_url / htmlLink / checkout / media links) + `with_url_immutability(system_prompt)` (idempotent compose helper; products append to their OWN prompt — seed owns the string, consumers compose). Exported from `domain.chatbot.__all__`. |

---

## 6 · Cross-provider operator setup-guide template — 📋

Every provider's `SETUP_<PROVIDER>.md` follows the same structure for
operator predictability; each step terminates in a **verifiable** state
(no "you should now see…"):

1. Create developer app in the provider dashboard (exact URL).
2. Add products / use cases (provider-specific catalog).
3. Register redirect URIs — explicit string match incl. port + path;
   list both localhost and tunnel forms (and prefer tunnel — G6).
4. Copy ID + Secret into `.env` (named vars).
5. Add operator as Admin/Tester/Developer for dev-mode access.
6. **For business customers: configure service-style auth** (Meta System
   User Token / Google Service Account) — make this the **default
   recommendation**, not the carve-out (Pattern 2).
7. Trigger consent at `/api/<provider>/oauth/start`.
8. Verify `/api/<provider>/status` + `/api/<provider>/scopes` show
   `configured: true, auth_mode: <expected>, coverage_pct: 100`.
9. Smoke-test through the chatbot with a realistic query.

---

## 7 · Residual gaps — all closed 2026-05-17 ✅

After verify-the-seed-ships-it (read every `__init__.py` + adapter, not
just the notes' wording), **the vast majority of the source notes'
recommendations were already shipped** in `noctusai_lib` (Patterns 2/4/5
fully; the Pattern-1 mechanics, all chatbot takeaways 5.1-5.8). The
three narrow residual gaps were lifted into the seed **2026-05-17**:

1. ✅ **Unified `ScopeResolver` Protocol** (Pattern 1 generalization) —
   `noctusai_lib.security.oauth.scopes`: Protocol (`provider` /
   `resolve` / `list_app_scopes() -> list[str] | None` /
   `discover_granted` / `diagnose`) + `GoogleScopeResolver`
   (`list_app_scopes()` → `None`) + `MetaScopeResolver`
   (`list_app_scopes()` → Graph list) + `FakeScopeResolver` +
   `make_scope_resolver(provider, ...)`. Real impls **delegate to**
   `integrations.google_scopes` + `integrations.meta._meta_api` (no
   re-implementation). Home rationale: `security.oauth` already owns
   the cross-provider OAuth surface (`OAuthProvider` + `oauth_router` +
   `make_oauth_provider`); scope resolution is auth-layer, not a vendor
   adapter — placed beside the dance rather than a new
   `integrations/oauth/` package. Seed-fake-real shape (the discovery
   methods touch provider HTTP).
2. ✅ **Named per-provider scope bundles** (Pattern 3) —
   `noctusai_lib.integrations.oauth_bundles`:
   `GOOGLE_BUNDLE_PRODUCTIVITY` / `GOOGLE_BUNDLE_COMMUNICATIONS` /
   `META_BUNDLE_READ_ONLY` / `META_BUNDLE_FULL_SOCIAL` +
   `resolve_bundle(name)` + `bundle_names()`. Each bundle is a **named
   subset of the already-shipped kitchen-sink** (single source of
   truth; a startup `AssertionError` enforces the subset invariant).
   Home rationale: `integrations` sibling of the per-provider scope
   modules gives consumers ONE bundle import surface while the literals
   stay single-sourced in each provider module.
3. ✅ **Shared URL-immutability system-prompt fragment** (takeaway 5.9)
   — `noctusai_lib.domain.chatbot.prompt_fragments`:
   `URL_IMMUTABILITY_FRAGMENT` (generic — auth_url / htmlLink /
   checkout / media links, not Google-specific) +
   `with_url_immutability(system_prompt)` (idempotent compose helper).
   Seed owns the string; consumers append to their **own** prompt
   (`openai_orchestrator` takes `system_prompt` from the consumer).

Verified on the `social-wiring` pilot (import-smoke green; the
pre-existing `google_auth_oauthlib` missing-dep in
`app/services/youtube_service.py` is unrelated). The
`noctusai-youtube-crawler` *product* absorption (distinct from the
OAuth lib code) remains a future effort following
`CONTEXT/GUIDES/absorb-seed-workspace.md`; it now **consumes** these
three primitives rather than gating them.

### Settled design decisions (were open at filing)

- Scope-resolution Protocol home → `security.oauth.scopes` (auth-layer,
  beside the dance), NOT a new `integrations/oauth/` package.
- Bundle placement → `integrations/oauth_bundles.py` (one consumer
  import surface; literals single-sourced per provider module).
- Kitchen-sink lists → per-noc-lib shared catalog + named subsets
  (bundles are subsets of the in-code kitchen-sink, never new literals).
- OAuth testing posture → mocked-only at the httpx boundary
  (external-service carve-out per the no-monkeypatching rule).

### Still open (out of scope of the closed lift)

- How Meta's Use-Case "asset connection" abstraction generalizes across
  providers (Google = GCP Console scope config; TikTok = its own).
- TikTok integration / Meta webhook subscriptions / Meta+IG posting
  (App-Review-gated) — separate future modules.

---

## 8 · Related

- `CONTEXT/PATTERNS/backend/whatsapp-chatbot-seed.md` — WhatsApp connector +
  chatbot framework wiring recipe (the chatbot-side consumer of these
  OAuth adapters).
- `CONTEXT/PATTERNS/backend/seed-fake-real-adapter.md` — the Protocol+Fake+Real+
  factory shape every Layer-3 adapter follows.
- `CONTEXT/PATTERNS/devops/containerization.md` §12a — the house single-container
  model that subsumes takeaways 5.7/5.8 + gotcha G4/G6.
- `CONTEXT/PATTERNS/security/webhook-signatures.md` — sibling
  `noctusai_lib.security` primitive (the 5-pin webhook contract; WAHA
  webhook receivers compose dedup §5.1 + this).
- `CONTEXT/GUIDES/google-oauth-setup.md` — GCP Console operator walkthrough
  (the §6 template, instantiated for Google Calendar).
- `CONTEXT/GUIDES/absorb-seed-workspace.md` — the 10-gate procedure the
  youtube-crawler product absorption (§7) will follow.
- `CONTEXT/INTEGRATIONS/vista.md` — sibling vendor reference (house style).
