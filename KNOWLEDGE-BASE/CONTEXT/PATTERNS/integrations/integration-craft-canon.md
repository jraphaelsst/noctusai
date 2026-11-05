# Integration craft canon — third-party integrations, mapped onto the house

> **What this is.** The integrations-engineering canon (OAuth 2.0 / OIDC, inbound webhooks, outbound
> calls under vendor limits, vendor lifecycles, sandbox vs live, the action ledger, per-vendor
> observability, failure modes, vendor exit) that a master-level integrations engineer brings to this
> platform. Every principle is mapped to the house mechanism that implements it, with file:line, a
> checklist and anti-patterns. Owner: `integrations-engineer` (`.claude/agents/integrations-engineer.md`).
> Authored 2026-11-05 (agent-refinement W2-S6). Every external URL in § Sources was fetched that day.
>
> **Why it exists.** The 24 `INTEGRATIONS/*.md` docs are excellent per-vendor references, written
> after real incidents (WAHA config REPLACE, Meta silent `[]` before App Review, Vista echoing our key
> in a 401 body). None of them teaches the discipline those incidents are instances of. An engineer
> who knows only the vendor docs re-derives OAuth CSRF binding, durable webhook dedup and retry
> budgets by hand — and every vendor gets a slightly different, slightly wrong version.
>
> **How to use it.**
> 1. **The seed mechanism wins.** If a seed primitive (`noctusai_lib.integrations.*`,
>    `noctusai_lib.security.*`), keeper or `noctus.dev.*` tool covers a point, use it. The canon
>    explains why it exists and covers only what the house has not built yet. A canon idea with no
>    house mechanism is a *proposal to surface*, never a licence to hand-roll a per-product version
>    (CLAUDE.md §1 seed-first, replication-to-seed symmetry).
> 2. **Compose, don't duplicate.** Generic reliability (timeouts, one retry layer, outbox, sagas,
>    idempotent consumers) lives in `KB § PATTERNS/backend/backend-craft-canon.md` §4.5 / §6. Webhook
>    signature verification lives in `KB § PATTERNS/security/webhook-signatures.md` (security-owned,
>    the 5-pin contract). OAuth threat rules live in `KB § PATTERNS/security/appsec-craft-canon.md` §7.
>    This doc adds only the vendor-facing layer on top and points at those for the rest.
> 3. **Per-vendor facts live in `KB § INTEGRATIONS/<vendor>.md`.** Read the vendor doc for the slice,
>    then the section here that matches the concern (auth, inbound, outbound, lifecycle).
> 4. **Vendor docs drift; verify before coding.** Fetch the vendor's current page (WebFetch) before
>    relying on a limit, a version or an error code. § 7 shows three facts that drifted under us.

## 0 · Standard term ↔ house term

| Standard term | House mechanism | Where |
|---|---|---|
| Anti-corruption layer (Evans) | vendor adapter (Protocol + Fake + Real + factory) emitting domain types; mappers normalise vendor shapes | `KB § PATTERNS/backend/seed-fake-real-adapter.md`; e.g. `seed/lib/backend/noctusai_lib/integrations/vista/protocol.py:1-21` |
| Fake-or-refuse adapter selection | `resolve_fake_or_refuse(configured=, build_real=, unconfigured=, allow_fake=)` | `seed/lib/backend/noctusai_lib/integrations/fake_or_refuse.py:1-48` |
| Credential resolution / secret store | `resolve_credential` (override → `org_settings` → `platform_settings` → env) · `resolve_org_credential` (org only, fail-closed) · `CredentialStore` (Fernet, per `(org_id, provider)`) | `seed/lib/backend/noctusai_lib/config/credentials.py:1-14,146-208,211-240`; `KB § INTEGRATIONS/oauth-patterns.md` §2 Pattern 5 |
| OAuth client (authorization code + PKCE) | `OAuthProvider` Protocol + `GoogleProvider(use_pkce=)` + `FakeOAuthProvider` + `oauth_router` | `seed/lib/backend/noctusai_lib/security/oauth/` (`google_provider.py:65-80,141-180`) |
| Token persistence bridge | `make_token_persisting_callback` + `CredentialStore*Resolver` | `seed/lib/backend/noctusai_lib/integrations/credential_resolvers.py:258-290` |
| Scope minimisation / incremental auth | named bundles `oauth_bundles` + `ScopeResolver` + post-consent introspection | `KB § INTEGRATIONS/oauth-patterns.md` §2 Patterns 1, 3, 4 |
| Webhook signature verification | `webhook_endpoint(scheme=…)` / `verify_*` helpers, 5-pin contract | `seed/lib/backend/noctusai_lib/security/webhook_signatures.py`; `KB § PATTERNS/security/webhook-signatures.md` |
| Idempotent consumer / inbox | `WebhookDedup` (SETNX, fast pre-filter) · `EventInbox` (durable claim/release) · `message_store` UNIQUE | `integrations/whatsapp/dedup.py:79-166`; backend canon §6.5 |
| Client-side rate limiter + backoff | `rate_limit.acquire[_async]` (token bucket per vendor) + `retry_with_backoff[_async]` + `paced_call` | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:81-101,407-481`; `KB § PATTERNS/common/outbound-rate-limiting.md` |
| Transactional outbox / work queue | jobs organ (`enqueue(dedupe_key=)`, SKIP LOCKED, lease) | backend canon §6.4 |
| Contract test vs vendor | boundary-contract tests + "assert the emitted wire key" + gated live probes | `KB § PATTERNS/backend/boundary-contract-tests.md`; memory `vendor-config-silent-key-drop` |
| Vendor action ledger | append-only ledger with before-image + exact undo for writes on someone else's platform | memory `feedback_external_platform_action_ledger` (§ 8 here) |
| Remediation backlog per vendor | `NOC-REMEDIATE[<class>]` markers (e.g. `[rate-limit]`, `[waha-verify]`) | `KB § PATTERNS/common/remediation-markers.md` |

---

## 1 · Integration architecture — one adapter per vendor, behind a seed seam

**Principle.** An integration is a boundary between our domain model and a model we do not control.
Evans' **anti-corruption layer** (ACL) puts a translation layer at that boundary so the vendor's
semantics never leak inward: callers speak our model, the layer speaks the vendor's
(Microsoft Azure Architecture Center, "Anti-Corruption Layer pattern", which credits Evans' *DDD*).
The same page lists the costs: extra latency, one more thing to maintain and monitor, and the risk of
smuggling business rules into the translator — keep the layer to translation.

**How it applies here — the five layers.** `KB § INTEGRATIONS/oauth-patterns.md` §1 already names the
house layering; generalised to every vendor:

```
L4  Tool surface      product routers / chatbot tools / MCP (mcp/<vendor>)       ← consumer-owned
L3  Adapter (ACL)     Protocol + Fake + Real + make_/get_ factory; emits DOMAIN types  ← seed
L2  Auth              credential resolution · token refresh · auth_mode           ← seed
L1  Scope / capability catalog (in code, versioned with the adapter)              ← seed
L0  Credential store  CredentialStore (Fernet) · org_settings / platform_settings  ← seed
```

- **Protocol + Fake + Real + factory is mandatory** (CLAUDE.md §1, `KB § PATTERNS/backend/seed-fake-real-adapter.md`).
  The Real ships with the Protocol, or the "consume" slice silently becomes a "seed-build" slice.
- **The adapter returns domain types, not vendor JSON.** Vista: `VistaCRMAdapter.get_imovel → Imovel`
  from `noctusai_lib.domain.real_estate` (`integrations/vista/protocol.py:30-56`) — a cross-CRM
  vocabulary, which is what makes a future CRM swap possible (§ 11). WAHA: one tolerant mapper
  (`whatsapp/mappers.py`) absorbs the `id` string-or-object, seconds-vs-ms and `_data.body` variants
  (memory `feedback_waha_response_shape_drift` traps 5 and 6).
- **Fake vs not-configured is a declared state, never inferred.** `resolve_fake_or_refuse`
  (`fake_or_refuse.py:1-29`) has no path from "credential missing" to "Fake" except `allow_fake=True`.
  The anti-shape it exists to kill: prod sending a fake WhatsApp that reads "Enviada".
- **Hot paths never wait on a vendor.** WAHA history is ~13 s per call; the 2026-06-24 regression
  put two WAHA calls before the bot's reply (memory `feedback_external_api_hot_path_boundaries`).
  Rule: hard timeout on every read, cache vendor data in our DB, background the slow half, degrade
  to what we have. Budgets: `KB § PATTERNS/backend/request-path-latency.md`.
- **Mirror vs live proxy is a design decision, stated per vendor.** Vista = mirror
  (`social_wiring.imoveis`, reads never hit Vista — `products/social-wiring/backend/app/routers/imoveis_router.py:16`);
  Mailchimp = live proxy, no local copy (`KB § INTEGRATIONS/mailchimp.md`). A mirror owes a sync
  guarantee and a divergence policy (§ 11.2); a proxy owes a latency budget and a degraded state.

### 1.1 Credentials — where they resolve

| Kind | Where it lives | Resolver | Rule |
|---|---|---|---|
| Per-tenant vendor key (Vista, a CRM, a gateway) | `CredentialStore` row per `(org_id, provider)`, Fernet | `credential_resolvers.py` bridges | Owner rule 2026-11-03: **DB, never `.env`; no silent env fallback**; UI shows last 4 only (memory `feedback-integration-keys-in-db-not-env`) |
| Per-tenant OAuth token bundle | same store, written by the OAuth callback | `make_token_persisting_callback` (`credential_resolvers.py:258`) | never overwrite a stored refresh token with `None` (`security/oauth/google_provider.py:26-31`) |
| Org-or-platform key (LLM keys) | `org_settings` → `platform_settings` → env | `resolve_credential` (`config/credentials.py:146-208`) | chain is for keys a platform default is *allowed* to serve |
| "Must be this org's own key" | `org_settings` only | `resolve_org_credential` (`credentials.py:211-240`) | fail-closed: a miss is `None`, never a fallback (B1 of the Lais contract) |
| Platform secrets (`ENCRYPTION_KEY`, Supabase, webhook HMAC) | `.env` / `.env.fleet` | settings | one secret per vendor per environment (`webhook-signatures.md` Universal rules) |

**Note the tier-0/1/2 silent fallbacks.** `resolve_credential` logs `org_settings` / `platform_settings`
lookup failures at DEBUG and falls through to env (`credentials.py:191,205-208`). For a tenant key that is
the wrong behaviour — use the org-only resolver or the `CredentialStore` bridge.

### 1.2 Checklist — architecture
- [ ] Seed adapter exists (Protocol + Fake + Real + factory)? If not, the slice is a seed-build: surface it.
- [ ] Adapter emits domain types; vendor JSON stops at the mapper; raw payload kept verbatim where audit/re-derivation needs it (Vista `vista_raw`, Meta `LeadgenEvent.raw`).
- [ ] Mirror or proxy decided and written in the vendor doc; hot-path calls have a timeout and a cached/degraded answer.
- [ ] Credential tier chosen from § 1.1; no `.env` tenant key; key never logged (Vista echoes it — `KB § INTEGRATIONS/vista.md` § "Credential echo").
- [ ] `resolve_fake_or_refuse` at the consumer; `/api/health` or a status endpoint reports "not configured" honestly.

**Anti-patterns.** Vendor JSON passed straight to the FE. A per-product copy of a seed client. Constructing
the Real adapter directly at N call sites instead of one factory (Vista today, § 11.1). Fake as the
silent default when a key is missing.

---

## 2 · Authorization — OAuth 2.0 / OIDC

**Principle.** RFC 6749 defines the authorization-code grant; RFC 9700 (OAuth 2.0 Security BCP,
January 2025) is the current rulebook on top of it. The rules that bind us (RFC 9700 §2):
- **Clients MUST prevent CSRF** — via one-time `state` bound to the user agent, or via PKCE once the
  authorization server is known to support it (§2.1, §4.7.1). RFC 6749 §10.12: the `state` binding
  value MUST be non-guessable and tie the request to the user agent's authenticated state.
- **PKCE:** public clients MUST use it; for confidential clients it is RECOMMENDED (§2.1.1). RFC 7636:
  verifier 43–128 unreserved chars, ≥256 bits of entropy (§7.1); S256 MUST be used when possible (§4.2).
- **Clients MUST prevent authorization-code injection** (§2.1.1); **redirect URIs match exactly**
  (§2.1, §4.1.3); **no open redirectors** on redirect hosts (§4.1.3); implicit grant SHOULD NOT be used.
- **Mix-up defence is REQUIRED** with more than one authorization server; use `iss` (RFC 9207) where
  the AS sends it (§2.1, §4.4.2).
- **Least privilege:** token privileges SHOULD be restricted to the minimum required (§2.3).
- **Codes** expire fast (≤10 min recommended) and are single-use (RFC 6749 §4.1.2).
- **Refresh tokens** MUST stay confidential in transit and storage (RFC 6749 §10.4); if the AS issues
  a new one on refresh, the client MUST discard the old one (§6). Public clients' refresh tokens MUST
  be sender-constrained or rotated (RFC 9700 §2.2.2).
- **Revocation** (RFC 7009): POST `token` (+ `token_type_hint`); 200 even for an already-invalid
  token; revoking a refresh token SHOULD also kill its access tokens (§2.1, §2.2).
- **OIDC:** when using `openid`, validate the ID token — `iss` exact, `aud` contains our `client_id`,
  `exp`, signature unless it came straight from the token endpoint over TLS, `nonce` when sent
  (OpenID Connect Core §3.1.3.7).

**How it applies here.**
- **The seed client.** `GoogleProvider` always sends `access_type=offline`, `prompt=consent`,
  `include_granted_scopes=true` (`security/oauth/google_provider.py:141-170`) — Google issues a
  refresh token only on first consent or under `prompt=consent` (`:26-31`). PKCE is **opt-in**
  (`use_pkce=False` default, `:122-137`); S256 with a 64-byte `token_urlsafe` verifier (`:65-80`), and
  `exchange_code` refuses a PKCE exchange without the verifier (`:214-219`).
- **⭐ Use `use_pkce=True` for every new flow.** Our backend is a confidential client, so the BCP says
  RECOMMENDED, not MUST — but in our design PKCE is also the CSRF/code-injection binding (worked
  example B). The social-wiring integration-accounts flows already do it
  (`products/social-wiring/backend/app/routers/integration_accounts_router.py:509-525`).
- **State binding.** The generic `oauth_router` echoes `state` and takes `redirect_uri` from the query
  (`security/oauth/router.py:216-271`); **it does not bind state itself** — the consumer must. The
  reference consumer binds it by storing the PKCE verifier in Redis keyed by the state, 10-min TTL,
  single-use (`integration_accounts_router.py:480-483,654-662,742-750`). An unknown state therefore
  has no verifier and the exchange refuses.
- **Callback runs without a JWT** (the browser arrives from Google), so the org comes from the server-
  bound state, never from a query param the caller can choose freely (`integration_accounts_router.py:699-722`).
- **Meta token chain** — short-lived (~2 h) → long-lived user token (~60 days, `fb_exchange_token`,
  server-side because it carries the app secret) → Page tokens from `/accounts` with no expiry date but
  invalidatable. Persist the long-lived user token only; refetch Page tokens
  (`KB § INTEGRATIONS/oauth-patterns.md` §4.1; Meta "Long-lived access tokens").
- **Service-style identity beats user OAuth for business assets.** Meta System User token / Google
  service account (`oauth-patterns.md` §2 Pattern 2) — Business-Portfolio-owned Pages are filtered out
  of `/me/accounts` for user tokens with no error.
- **Granted ≠ requested.** Google lets users grant a subset of scopes (granular consent); RFC 6749 §3.3
  makes the AS return `scope` when it differs. Post-consent introspection (`oauth-patterns.md` §2
  Pattern 4: `/me/permissions`, `tokeninfo`) is mandatory on every status surface.

### 2.1 Token lifecycle — the states to design for

| Event | Google | Meta | Our handling |
|---|---|---|---|
| Access token expiry | ~1 h | user ~60 d; Page token no expiry | refresh on 401 / before `expires_at`, in ONE place (the adapter) |
| Refresh token dies | revoked by user · unused 6 months · password change with Gmail scopes · >100 live tokens per account per client (oldest silently invalidated) · time-based access expired · admin policy (`admin_policy_enforced`) · **7 days if the app is External + "Testing"** (Google "Using OAuth 2.0" § Refresh token expiration) | user token expiry ~60 d; password change; permission removal | map `invalid_grant` / Graph `190` (`_meta_api.py:88-89`) to a **needs_reconnection** state on the status endpoint — never a 500, never silent |
| User revokes in vendor UI | `invalid_grant` on next refresh | `190` | same |
| We disconnect | POST `https://oauth2.googleapis.com/revoke` (`GOOGLE_REVOKE_URL`, `google_provider.py:52`) then `CredentialStore.delete` | delete stored token (+ data-deletion URL obligations, `meta-app-verification.md` §0) | revoke at vendor **and** delete locally; RFC 7009 says 200 for already-dead tokens, so treat 200 as done |

### 2.2 Delivery dependencies — consent screens and reviews are on the critical path

| Gate | Who | What it blocks | Lead time to plan for |
|---|---|---|---|
| Google OAuth verification | operator, Google Cloud Console | sensitive/restricted scopes for users outside "Testing"; restricted scopes re-verify **annually** (Google Cloud Help "OAuth app verification") | days–weeks; restricted adds a security assessment. While unverified + Testing: refresh tokens die in 7 days |
| Google consent-screen scope registration | operator | every kitchen-sink scope must be registered **before** the flow requests it (`oauth-patterns.md` §4.4) | minutes, but forgetting it = per-scope "unverified app" warning |
| Meta Business Verification | operator | Advanced Access for any permission since 2023-02-01 (Meta "Access levels") | days; the CNPJ-less controller is the named risk (`meta-app-verification.md` §0) |
| Meta App Review (Advanced Access) | operator + screencast + test calls | any permission used by a non-role user; before it, Standard Access works for app-role users only and returns **empty data, not errors** (`oauth-patterns.md` §4.3; memory `reference_meta_ig_dm_facebook_login_model`) | plan in weeks; `instagram_manage_messages` can only clear its test call from an app-role user |
| Meta Data Use Checkup | operator | Advanced Access stays on only after the **annual** checkup (Meta "Access levels") | yearly calendar item |
| WhatsApp Cloud API scaling path | business | messaging limit 250 → 2 000 → 10k → 100k → unlimited (§ 9) | business verification or 2 000 high-quality template sends in 30 days |

**Rule.** A slice that needs a new scope/permission names its gate in the brief, and the code ships a
**truthful paused state** (e.g. the 2026-07-28 `requires_app_review` 200 + `AppReviewNotice`, memory
`reference_meta_ig_dm_facebook_login_model`) so the UI is honest while the gate is closed. When the
gate opens, re-verify every claim written while it was closed (memory `feedback_gated_surface_assumptions_rot`).

### 2.3 Checklist — OAuth flow
- [ ] `GoogleProvider(use_pkce=True)` (or the vendor's PKCE); verifier stored server-side keyed by `state`, ≤10 min TTL, deleted on use.
- [ ] `state` is server-issued, unguessable, single-use; the org/user it carries is trusted only because the server issued it.
- [ ] Redirect URI built from config, registered exactly in the vendor console (tunnel host, not localhost — `oauth-patterns.md` §3 G4–G6).
- [ ] Scopes = the minimum named bundle (`oauth_bundles`), requested incrementally; post-consent introspection exposed.
- [ ] Tokens written through `CredentialStore` (Fernet); refresh token never overwritten with `None`; nothing token-shaped in logs.
- [ ] `invalid_grant` / `190` → `needs_reconnection`; disconnect revokes at the vendor and deletes locally.
- [ ] Vendor gate (verification / App Review) named, lead time in the plan, paused state built.
- [ ] Strict-status tests for the callback: bad state ⇒ 400, missing verifier ⇒ 400, missing auth on `/start` ⇒ `== 401` (CLAUDE.md §1).

**Anti-patterns.** `state = org_id` with nothing server-side. Trusting `redirect_uri` from the request
to choose where tokens land. Storing a Meta Page token as the long-lived credential. Treating an empty
Graph `data: []` as "no assets" before checking access level. Mounting `oauth_router`'s `/refresh` and
`/revoke` (`router.py:309-363`) unauthenticated on a public product — they proxy any token in the body;
no product mounts them today, keep it that way or wrap them in an auth dependency.

---

## 3 · Inbound webhooks

**Principle.** A webhook is an untrusted POST that claims to be the vendor. Five properties, in order:
**verify → dedupe → persist → acknowledge fast → process async**, and the consumer tolerates
**duplicates, reordering, replays, silence**. The Standard Webhooks spec (v1.0.0) is the clearest
generic statement: `webhook-id` is stable across retries and is the idempotency key; signed content is
`{id}.{timestamp}.{payload}`, verified over the exact bytes; constant-time compare; reject timestamps
outside a tolerance; any non-2xx (including timeouts) is a failure the sender retries with backoff over
hours to days; sender timeout 15–30 s. Stripe's docs say the same in vendor form: log processed event
ids, don't assume order, return 2xx before complex logic, process through an async queue; 5-minute
default timestamp tolerance; live-mode retries for up to three days.

**How it applies here.**
- **Verify** — the 5-pin contract (`KB § PATTERNS/security/webhook-signatures.md`): `webhook_endpoint(...)`
  with a per-request secret resolver, explicit `bypass_when_unset`, `@limiter.limit`, strict-status
  tests. The seed default still accepts unsigned requests when the secret is unset unless
  `WEBHOOK_REQUIRE_SIGNATURE=1` (`security/webhook_signatures.py:58-87`) — the open P0 (PROJECT §6 #1).
  New receivers pass `bypass_when_unset=False` for any route already live in prod, as the Meta leadgen
  receiver does (`products/social-wiring/backend/app/modules/meta_ads/routers/leadgen_router.py:20-26,180-186`).
- **Replay window only where the timestamp is signed.** Stripe and Svix sign the timestamp, so the
  300 s window (`DEFAULT_MAX_AGE_SECONDS`, `webhook_signatures.py:49`) is meaningful. WAHA sends
  `X-Webhook-Timestamp` (milliseconds) and `X-Webhook-Request-Id`, but its HMAC covers the body only
  (WAHA "Events" docs) — an unsigned timestamp proves nothing, so WAHA replay defence is dedup.
- **Dedupe** on the vendor's event/message id **before** side effects — backend canon §6.5 lists the
  three house layers. The seed `WebhookDedup` Protocol has `claim()` and **no release**
  (`integrations/whatsapp/dedup.py:79-90`); the WhatsApp router claims before `on_message`
  (`whatsapp/router.py:138-146`). If `on_message` raises, the id stays claimed (Redis TTL 1 h,
  `dedup.py:52`), WAHA's retry is answered `duplicate`, and the message is lost unless the consumer's
  durable layer (`message_store` UNIQUE) already recorded it. ⇒ **Persist the raw event durably before
  the work, or use `EventInbox.claim/release`** (durable, releases on failure). Seed gap to surface:
  `WebhookDedup.release()`.
- **Acknowledge fast.** Meta retries any non-2xx immediately and then less often for 36 h, then drops
  (Meta "Getting started with webhooks"); Asaas pauses the whole queue after 15 consecutive failures and
  deletes events older than 14 days (Asaas "Sobre os webhooks"). So: return 200 for everything past
  signature verification and make the **durable inbox row**, not the status code, the recovery path
  (`leadgen_router.py:189-197`). Slow work goes to a thread / after-response task / jobs organ
  (`leadgen_router.py:246-294` — the 2026-10-05 65 s inline sweep that stalled the instance).
- **Ordering is never guaranteed.** Stripe says so explicitly and warns that `created` cannot order
  events; Meta batches up to 1 000 updates and may not batch at all. Design handlers as **state
  reconciliation**: on any event, fetch the current resource state from the vendor (thin-payload
  style — Meta leadgen carries only `leadgen_id` and the PII is fetched from Graph,
  `meta/leadgen_webhook.py:1-9`), or apply only if the event's version/updated_time is newer than
  what we hold.
- **Parse every batch element.** `parse_leadgen_webhook` iterates every `entry[] × changes[]` — the
  `entry[0].changes[0]` anti-shape silently drops the rest (`meta/leadgen_webhook.py:72-122`).
- **Distinguish event classes.** `leadgen` (immutable fact) ≠ `leadgen_update` (mutable, many per
  lead) — separate parsers and types so an update never creates a duplicate lead (`leadgen_webhook.py:125-195`).
- **Record the unrecognised.** "Arrived and ignored" must be distinguishable from "never arrived"
  (`leadgen_router.py:226-233`): the first is our parser, the second is the vendor subscription.
- **Subscription handshake ≠ signing secret.** Meta's `hub.verify_token` (ours, GET once) vs the App
  Secret that signs every POST (`leadgen_router.py:11-18`); compare the verify token in constant time
  and echo the challenge as an opaque string (`leadgen_webhook.py:245-272`, `leadgen_router.py:118-139`).
- **Webhook silence is a failure mode** (§ 10): a subscription dropped by the vendor (Meta needs BOTH
  the app-level and the Page `subscribed_apps` subscription, `meta-app-verification.md` §10), an
  expired Google push channel (no auto-renewal; Google Calendar "Push notifications"), a WAHA config
  PUT that dropped our webhook (`KB § INTEGRATIONS/whatsapp.md` §4a). Every push integration needs a
  **reconciliation poll** as the backstop — Google says push messages can be dropped and periodic sync
  is still required.

### 3.1 Checklist — new webhook receiver
- [ ] Shape matched to one of the 5 signature schemes (`webhook-signatures.md`); not a new one.
- [ ] Pins 1–5 (+ proposed pin 6 dedup); `bypass_when_unset=False` once live; secret per vendor per env.
- [ ] Raw body read once, verified, then parsed; malformed-but-verified ⇒ 200 + recorded, never 500.
- [ ] Dedupe key = vendor event/message id; durable (DB UNIQUE / `EventInbox`), released on failure.
- [ ] Raw event persisted (inbox row) before side effects; heavy work async; handler ≤ a few hundred ms.
- [ ] Every batch element parsed; unknown fields/events recorded, not dropped.
- [ ] Handler idempotent and order-independent (fetch-current-state or version check).
- [ ] Public route outside authed namespaces, listed in an auth-boundary test (`leadgen_router.py:3-9`).
- [ ] Reconciliation job for missed deliveries; "last event received at" visible per vendor (§ 9).
- [ ] LGPD: PII from the payload is a personal-data event (`KB § PATTERNS/security/lgpd.md`).

**Anti-patterns.** Verifying parsed-and-re-serialised JSON. Returning 4xx/5xx for "not interesting"
events (WAHA retries; Meta can drop the subscription). Claim-then-crash with a TTL dedup and no durable
row. Using the vendor timestamp to order events.

---

## 4 · Outbound calls under vendor limits

**Principle.** HTTP 429 means "too many requests"; the server MAY send `Retry-After`
(RFC 6585 §4). `Retry-After` is either an HTTP-date or delay-seconds (RFC 9110 §10.2.3). The IETF
`RateLimit` / `RateLimit-Policy` fields are still a draft (-11, May 2026); when both are present
`Retry-After` wins, and quota hints are not guarantees. AWS Builders' Library: retry at **one** layer
(retries multiply across layers), add jitter, retry only idempotent operations or ones with an
idempotency token. Google's retry guidance: retry 408/429/5xx and connection errors, exponential with
jitter, cap ~32–64 s, retry non-idempotent operations only with a precondition, and do not stack
application retries on library retries.

**How it applies here — `rate_limit.py` is the one primitive.**
- **Pace first** (`acquire`/`acquire_async` per vendor bucket), **back off on signal**
  (`retry_with_backoff`, full jitter `uniform(0, min(cap, base·2^n))`, `rate_limit.py:398-404`),
  honour the vendor's `Retry-After` via the `retry_after=` extractor (`:407-455`), `paced_call` paces
  every attempt (`:458-481`). Buckets: `meta` 3 rps, `google` 8, `youtube` 3, `whatsapp` 5,
  `whatsapp_groups` 0.2 (group mutation is the ban vector), `vista` 5, `llm` 8 (`:81-101`); env-tunable
  `NOC_RL_<BUCKET>_RPS/_BURST`. Adoption: `KB § PATTERNS/common/outbound-rate-limiting.md`.
- **Only rate-limit signals are auto-retried** — the request was rejected, not processed, so retrying a
  write is safe. Timeouts may have landed and are never auto-retried by this layer
  (`outbound-rate-limiting.md`; `_meta_api.py:40-46`).
- **Two gaps in the primitive** (surface, don't hand-roll):
  1. `parse_retry_after` handles delay-seconds only; the HTTP-date form returns `None` and falls back
     to jittered backoff (`rate_limit.py:487-497`). RFC 9110 allows both.
  2. The hinted delay is clamped to the bucket's `max_backoff` (60 s, `:445`; async twin `:378`). A vendor that says
     `Retry-After: 3600` is retried after 60 s — ignoring the hint is exactly what extends a throttle
     ("continued calls extend the recovery time", Meta "Rate limits"). Correct shape: if the hint
     exceeds the budget, give up and reschedule (jobs organ `RescheduleLater`), don't retry early.
- **Vendor-specific throttle classification.** Meta `MetaGraphError.is_rate_limited` covers platform
  codes `{4, 17, 32, 613}` (`_meta_api.py:90-91`). Meta's Business Use Case limits — which apply to
  Pages / Instagram / Lead Gen / Ads with system-user or Page tokens, i.e. our production path — throw
  `80000–80014` (`80001` Pages, `80002` Instagram, `80004` Ads Management, `80005` Lead Gen, `80006`
  Messenger, `80008` WhatsApp Business Management) and report `estimated_time_to_regain_access` in
  `X-Business-Use-Case-Usage` (Meta "Rate limits"). **These are not classified as rate-limited today**
  ⇒ a BUC throttle is surfaced as a hard error, not backed off. Seed fix candidate.
- **Read the usage headers, act before 100 %.** Meta throttles when `call_count`, `total_time` or
  `total_cputime` in `X-App-Usage` / `X-Business-Use-Case-Usage` reaches 100. Google Calendar: 600
  req/min/user, 10 000 req/min/project, a 1 000 000/day threshold, 403/429 `usageLimits`, and
  "randomise schedules ±25 %" (Google Calendar "Manage quotas"). A token bucket does **not** model a
  daily quota — YouTube's 10 000 units/day needs a budget counter (`FakeYoutubeClient.quota_units_consumed`).
- **Timeouts.** Every call has an explicit timeout sized to its caller's budget (backend canon §6.1).
  House reference: WAHA reads 6 s (`whatsapp/client.py:50`), history 20 s only because it is cached.
  Meta Cloud client creates `httpx.AsyncClient(timeout=30.0)` per call (`whatsapp/meta_cloud_client.py:71,116`).
- **Circuit breaking.** A breaker opens after N failures, fails fast, half-opens one probe after a reset
  timeout (Fowler, "CircuitBreaker"). The house has none (backend canon §6.3). For a vendor, the cheap
  equivalent today is a **degraded state on the status surface + jobs-organ rescheduling**; propose a
  seed breaker only when a vendor outage measurably saturates unrelated requests.
- **Batch and bulk.** Meta batch requests: ≤50 per batch, each counts toward limits individually,
  partial results on timeout (`null` slots are retryable) (Meta "Batch requests"). Use field expansion
  and `.summary(true).limit(0)` for counts (`oauth-patterns.md` §4.2) before batching.
- **Pagination.** Meta: cursors are opaque, expire, **must not be stored**; the end is "no `next`",
  never "fewer than `limit`" — privacy filtering can return an empty page that still has `next`
  (Meta "Paginated results"). Google: `pageToken`; incremental sync via `syncToken`, and **410 Gone ⇒
  wipe and full re-sync** (Google Calendar "Synchronize resources efficiently"). Our PostgREST side has
  its own cap (`KB § PATTERNS/backend/postgrest-row-cap.md`).

### 4.1 Checklist — new outbound call
- [ ] Goes through the vendor's seed client chokepoint, which calls `rate_limit` (one bucket per vendor; a hot sub-surface gets its own bucket, like `whatsapp_groups`).
- [ ] Explicit timeout inside the caller's budget; request path ⇒ fits the budget or moves to a job.
- [ ] Exactly one retry layer named in the docstring; jittered; rate-limit signals only, unless the call is idempotent or carries an idempotency key.
- [ ] Vendor's throttle codes/headers classified (incl. Meta BUC `800xx`); `Retry-After` honoured, not clamped below the hint.
- [ ] Daily quotas budgeted separately from per-second pacing.
- [ ] Pagination by the vendor's terminator; cursors not persisted; sync tokens handle 410.
- [ ] A throttle or outage leaves an honest state for the user, never a fabricated empty list.

**Anti-patterns.** `for x in items: client.post(...)` with no pacing (the 2026-07-23 Meta backfill).
A second `retry_with_backoff` inside a handler that the jobs `Worker` also retries. Retrying a timed-out
create. Treating a `{"data": []}` from a throttled or unreviewed app as truth.

---

## 5 · Idempotency toward vendors (outbound writes)

Composes backend canon §4.5 (inbound request keys) — this is the outbound half.
- **Use the vendor's idempotency mechanism when it has one.** Stripe idempotency keys (stored first
  response, parameter-mismatch error, 24 h pruning — backend canon §4.5); Google's preconditions
  (`ifGenerationMatch`, `etag`) for conditionally idempotent writes (Google "Retry strategy").
- **No vendor mechanism ⇒ make the write re-derivable.** Look up before create by a natural key we
  control (Vista `POST /lead` is not idempotent — check by phone/code first), or record our intent row
  (jobs organ `dedupe_key`) so a retry finds the previous outcome.
- **Outcome unknown (timeout on a create)** ⇒ do not blind-retry; reconcile by reading the vendor.
  The toolkit's `retry_ambiguous=False` is the reference stance (backend canon §6.2).
- **WhatsApp sends are never idempotent** — a retried send is a second message to a person and feeds
  the spam signals in § 10. Persist "sent" with the vendor message id before any retry logic.

---

## 6 · Webhooks we EMIT (outbound webhooks)

When the platform notifies others (`noctusai_lib.integrations.outbound_webhook`): follow Standard
Webhooks — `webhook-id` / `webhook-timestamp` / `webhook-signature` headers, signed
`{id}.{timestamp}.{payload}`, `whsec_` secrets 24–64 bytes, multiple space-delimited signatures during
rotation, thin payloads under ~20 KB, retries with jitter over a day, disable on prolonged failure and
tell the owner through another channel, and **send through an egress filter that blocks internal
addresses (SSRF)**. Versioning of what we emit: backend canon §4.6 (additive only; `Deprecation` +
`Sunset`).

---

## 7 · Vendor lifecycle — versions, deprecations, changelogs

**Principle.** Every vendor API has a calendar; an integration nobody re-reads silently rides an
auto-upgrade or a removal. Pin explicitly, track the calendar, watch the changelog, and treat a gated or
upgraded surface as unverified until re-probed.

**How it applies here — three drifts found while writing this doc (2026-11-05).**

| Vendor | House pin | Vendor fact (fetched 2026-11-05) | Consequence |
|---|---|---|---|
| Meta Graph (FB/IG) | `DEFAULT_GRAPH_VERSION = "v21.0"` (`integrations/meta/_meta_api.py:67`) | v21.0 available until **2027-01-21**; v22.0 → 2027-05-20; v26.0 released 2026-07-29 (Meta "Graph API changelog — versions"). Calls to an expired version are routed to the next-oldest available version (Meta "Versioning") | ~11 weeks to bump before a silent auto-upgrade. 🔴 Plan the bump now |
| WhatsApp Cloud API | `DEFAULT_BASE_URL = ".../v18.0"` (`integrations/whatsapp/meta_cloud_client.py:21`) | v18.0 expired **2026-01-26** | Every Cloud API call already runs on whatever version Meta routes it to. 🔴 Bump + re-verify payload shapes |
| YouTube Data API | protocol docs `search` = 100 u/page, `upload_video` = 1600 u (`integrations/youtube/protocol.py:49-50`; `KB § INTEGRATIONS/google.md` §3) | `search.list` and `videos.insert` now have **their own buckets of 100 calls/day, 1 unit each**; 10 000 shared units for the rest; reset midnight PT (YouTube "Quota calculator") | quota math in seed + KB is stale; the "≈6 uploads exhaust the quota" claim is wrong |
| WAHA | `devlikeapro/waha:noweb-2026.9.2` per instance (`deploy/fleet/waha-instances.yml:9`); legacy `:latest` at `deploy/services/compose.services.yml:106` | monthly `YYYY.M.patch` releases, latest 2026.10.1; 2026.6.1 "WAHA Plus features are now part of the WAHA Core image" (WAHA changelog) | `KB § INTEGRATIONS/whatsapp.md` §6 "CORE = one session per container" may be stale — re-verify before adding instances; unpin `:latest` |

**Rules.**
- **Pin the version in one constant per vendor**, never inline per call; a bump is one diff plus a
  re-verification run.
- **Vendor calendar.** Each `INTEGRATIONS/<vendor>.md` carries a dated "pinned version · available until ·
  next review" line; the ops daily brief is the natural place to surface "< 90 days to expiry"
  (proposal for `ops-steward`, `KB § PATTERNS/devops/ops-craft-canon.md`).
- **Changelog watching** is a recurring task, not a hope: Meta Graph + Marketing API changelogs, WAHA
  changelog, Google API release notes for each enabled API, Stripe/Asaas API changelogs.
- **Version-bump procedure** — see § 12.4.
- **Gated → opened ⇒ re-verify everything said while closed** (memory `feedback_gated_surface_assumptions_rot`):
  on Vista `/clientes` three confident claims were wrong. A 404 on a name you cannot cite in the vendor
  docs is untested, not absent; probe the published names (Vista `listarcampos`, `KB § INTEGRATIONS/vista.md`).
- **Config you PUT and never read back can be silently dropped** — assert the emitted wire key and the
  absence of the wrong spelling, then read the vendor's echo (memory `vendor-config-silent-key-drop`;
  WAHA `fullSync`).

---

## 8 · Sandbox vs live, test accounts, and the external-platform action ledger

**Sandbox vs live.**
| Vendor | Test surface | Trap |
|---|---|---|
| Stripe | test mode keys; separate `whsec_` per mode; test-mode retries only 3× in a few hours | live-mode retry/latency behaviour differs; test with `stripe trigger` |
| Asaas | sandbox environment (`KB § INTEGRATIONS/payments.md` § Asaas environments) | readiness verdict per env (`check_checkout_readiness`) |
| Focus NF-e | homologação only until P6 (`KB § INTEGRATIONS/invoices.md`) | production guard D36 |
| Meta | app-role users (admin/dev/tester) in Development mode; "Teste" sample payloads in the App Dashboard | Standard Access returns empty data for non-role users — a green test with a tester account proves nothing about real tenants |
| Google | "Testing" publishing status + test users | refresh tokens expire in 7 days |
| WAHA / WhatsApp | no sandbox: every number is real | a test burst can get a real number flagged — use a dedicated number and the slow bucket |

**Fakes are the default test double** (Protocol + Fake), driven through DI seams, never by
monkey-patching our own module (`KB § PATTERNS/backend/di-test-seam.md`, CLAUDE.md §1). Fakes are
instant, so **they cannot catch latency or shape drift**: before shipping anything on a hot path,
measure the real call (`curl -w '%{time_total}'`), and keep a gated live contract probe per vendor
that asserts the shapes the mapper depends on (memory `feedback_waha_response_shape_drift` meta-defence).

**Consumer-driven contract testing (Pact) does not fit public vendor APIs**: Pact's own guidance lists
"the team maintaining the other side will not also be using Pact" and public APIs as poor fits (Pact
"What is Pact good for?"). For vendors use: (1) recorded real payloads as mapper fixtures (Meta's own
"Teste" sample for `leadgen_update`, `leadgen_webhook.py:139-151`), (2) wire-key assertions on what we
emit, (3) gated live probes, (4) `KB § PATTERNS/backend/boundary-contract-tests.md` for our side.

**The external-platform action ledger.** When we act on someone else's live platform (first case:
Senseys' Orbity demo tenant, 2026-10-19), every write is logged append-only with timestamp, UI
action, method + path + filter, body, status, response id, **the before-image of the affected rows,
and the exact undo**; reads are logged per page; never write before the hook is installed;
back-filled entries say honestly that no before-image exists (memory
`feedback_external_platform_action_ledger`). It lets us undo exactly what we did and prove what we did
not do. Apply the same posture to **tenant-owned systems of record** we write to — Vista edits need a
`motivo` and a dated note line in `ObsVenda` / `ObsLocacao` / `Observacoes`, mirrored into our
`imovel_historico` (memory `feedback-vista-edit-reason-and-note`). Destructive vendor actions
(`logout` on a WAHA session unlinks a real device) are never an agent's unilateral call
(memory `waha-session-recovery-ladder`).

---

## 9 · Observability per vendor

**Principle.** Each integration is a dependency with its own SLO and error budget
(`KB § PATTERNS/devops/sre-craft-canon.md`). Per vendor, track: request rate, error rate by class
(auth / permission / throttle / 5xx / timeout), latency p95, **quota consumption vs limit**, **last
inbound event at**, token health (days to expiry, `needs_reconnection` count), and version expiry.

**House today.**
- Outbound pacing/backoff logs `rate_limit[<bucket>]` at INFO/WARNING (`rate_limit.py:436-450`); the
  sync Supabase transport is shared (`http_pool.py`). There is no per-vendor metrics surface.
- Status endpoints exist per vendor (Meta `/api/meta/status` + `/scopes` with `auth_mode`,
  `oauth-patterns.md` §2 Pattern 4; Google scopes router). Each must distinguish
  "not configured" · "needs reconnection" · "awaiting App Review" · "throttled" · "operational".
- Durable inboxes are the audit trail (`conversation_messages.structured_payload`, Meta leadgen inbox,
  Vista `imoveis_sync_execucoes` on the in-flight train).
- **Proposal (surface to tooling/devops):** one `integration_health` view per org × vendor fed by those
  inboxes + the rate-limit log lines, with "silent for > expected interval" alerts. Webhook silence is
  the failure nobody notices: Meta drops after 36 h, Asaas pauses after 15 failures, Google channels
  expire.

---

## 10 · Failure-modes catalog (per vendor)

| Vendor | Failure | Signal | Response | Source |
|---|---|---|---|---|
| WhatsApp (WAHA, unofficial) | number banned / restricted | sends fail `463` (reach-out timelock) or `475` (new-contact cap); `FIRST/SECOND_WARNING` | stop outreach; do **not** restart/logout/re-pair (doesn't reset it); reply-first, `sendSeen` → typing → random delay → send; ~5–10 spam flags can ban | WAHA "How to avoid blocking"; bucket `whatsapp_groups` |
| WAHA | session stuck STARTING forever after restart | dead creds | recovery ladder `start → restart → logout+start`; logout needs the owner | memory `waha-session-recovery-ladder` |
| WAHA | inbox empties after a config change | `PUT /api/sessions/{name}` is a full REPLACE; camelCase keys | always `_session_config()` / `set_webhook` merge; read back | `KB § INTEGRATIONS/whatsapp.md` §4a |
| WAHA | double processing | `message` + `message.any` both subscribed | dedup on `provider_message_id` | `oauth-patterns.md` §5.1 |
| WhatsApp Cloud API | message refused outside the window | only templates may be sent outside the customer-service window | send an approved template; templates review ≤24 h; LOW quality ⇒ paused/disabled | Meta "Template fundamentals"; "Messaging limits" |
| WhatsApp Cloud API | throughput / limit | 80 msg/s per number; 1 msg / 6 s to the same user; portfolio-level limit 250 → … unlimited over unique users in a moving 24 h | pace per number and per recipient; watch `business_capability_update` | Meta "Cloud API overview"; "Messaging limits" |
| Meta Graph | silent empty data | Standard Access / BM-owned assets / unsubscribed Page | access-level check + introspection; System User token | `oauth-patterns.md` §2, §4.3 |
| Meta Graph | IG DM query "expired" `-2/2534084` | Standard Access on a real inbox | App Review is the only fix; honest paused state | memory `reference_meta_ig_dm_facebook_login_model` |
| Meta Graph | token dead | `190` / `102` / `467` | `needs_reconnection` | `_meta_api.py:88-89` |
| Meta Graph | throttle | `4/17/32/613` · BUC `800xx` · usage headers ≥100 | back off; stop calling; **BUC codes unclassified today** | Meta "Rate limits"; § 4 |
| Meta Lead Ads | webhook silence | missing app-level OR Page subscription; non-2xx for 36 h | both subscriptions; reconcile by `leadgen_forms` sync; `leads_retrieval` needs Advanced Access for System Users | `meta-app-verification.md` §10; memory `reference_meta_ig_dm_facebook_login_model` |
| Google OAuth | refresh dies | `invalid_grant` (6 causes + 7-day Testing) | reconnect flow; publish the app | Google "Using OAuth 2.0" |
| Google APIs | quota | 403/429 `usageLimits`; YouTube daily units | backoff ≤64 s; budget counter | Google Calendar quotas; YouTube quota |
| Google Calendar push | silence | channel expired (no auto-renew) | renew before expiry; periodic sync; 410 ⇒ full sync | Google Calendar push + sync guides |
| Vista | key leak | 401 body and transport URL contain the key | redact at the client boundary (`redact_api_key`); rotate | `KB § INTEGRATIONS/vista.md` § Credential echo |
| Vista | invisible record | `ExibirNoSite=Nao` ⇒ 200 with no data (`VistaRecordUnpublished`) | treat as "not visible to this key", not "deleted" | `KB § INTEGRATIONS/vista.md` §4.1; skill `noc-refs-sheet` §2b |
| Asaas | queue paused | 15 consecutive failures; events deleted after 14 days | 200 fast; monitor; reactivate queue | Asaas "Sobre os webhooks" |
| Any vendor | write silently ignored | unknown key accepted | wire-key assert + read-back | memory `vendor-config-silent-key-drop` |

---

## 11 · Vista CRM — a first-class integration with a planned exit

Vista (Vista Software / Loft) is One Consultoria's real-estate CRM and **today the source of truth for
imóveis** (`products/social-wiring/backend/migrations/040_imoveis.sql:20-21`). The owner has said it
will be retired at some point; until then we depend on it. Two obligations follow at once: integrate
it well, and **never deepen the coupling**, so its removal is a swap, not a rewrite.
Reference: `KB § INTEGRATIONS/vista.md` (2 119 lines, live-probe calibrated).

### 11.1 What depends on Vista today (verified in this tree, 2026-11-05)

| Surface | How it touches Vista | Coupling |
|---|---|---|
| Seed adapter | `noctusai_lib.integrations.vista` — low-level `VistaClient` + domain facade `VistaCRMAdapter` (`get_property`, `get_imovel`, `list_imoveis`, `list_imovel_fotos`), Fake + Real + `get_vista_adapter` (`vista/protocol.py:30-74`, `adapter_factory.py:23-44`) | ⭐ ACL: emits `noctusai_lib.domain.real_estate.Imovel` |
| Imóveis mirror | `social_wiring.imoveis` (one row per listing per org, `vista_raw` JSONB verbatim payload, `040_imoveis.sql:42,128-132`); daily 00:05 sync + misfire grace + startup catch-up + DB lease (`services/imoveis_sync_scheduler.py:1-60`); manual `POST /api/imoveis/sync`; **reads never hit Vista** (`routers/imoveis_router.py:10-16`) | good: mirror isolates readers |
| Julia catalogue search | reads the mirror through a column allow-list (`services/julia_busca_imoveis.py:1-5`); `julia_catalogo_config` fonte=espelho (memory `project-vista-uso-post-deploy`) | good |
| Direct live calls | `VistaRESTAdapter(...)` constructed at `imoveis_sync_scheduler.py:202-216`, `routers/imoveis_router.py:267`, `routers/settings_router.py:367`, `routers/chat_router.py:111`, `routers/whatsapp_router.py:316`, `modules/edicao_fotos/deps.py:199` (+ `services/whatsapp_intake_service.py`) | 🔴 N=6+ direct constructions bypassing the factory; each reads `settings.crm_api_key` (env) |
| Divergence policy | Vista wins; one history action per changed field (`source=vista_sync`); in-app notification only, no WhatsApp/email; data with no Vista counterpart never touched; owner-confirmed values may be written back to Vista behind a per-org switch (default OFF) (memory `feedback-vista-divergence-no-alerts`) | policy, not code coupling |
| Writes to Vista | require `motivo` + dated note line (memory `feedback-vista-edit-reason-and-note`) | |
| MCP server | `mcp/vista` (`vista.imoveis.get` etc.) | tool surface |
| Skill `noc-refs-sheet` §2b | fills `Imóvel / Valor` (`Condomínio - Preço`) per `ONExxxxx` from `vista.imoveis.get`; never overwrites a differing price; `VistaRecordUnpublished` ⇒ "não publicado no Vista" | ops procedure |
| Other products | `erp-imobiliario` (asleep, 9 files), `igig`, `p-studio`, `store` mention Vista | asleep ⇒ don't touch (product catalog rule) |
| "Uso & Custos" + per-org key | on branch `feat/train-vista-uso-ship` (folded into `feat/jl-ship`, not on this base): `services/vista_credenciais.py` + seed `vista/credentials.py` resolve the key per org from `CredentialStore` with **no env fallback** (`NOC-REMEDIATE[vista-env-keys-removed]`), sync executions ledger `imoveis_sync_execucoes`, `/admin/uso` | resolves the env-key rows above once it lands — re-verify on contact |

### 11.2 Rules while Vista is live
- **All Vista access goes through one factory** (`get_vista_adapter` or the per-org resolver on the
  train) — a new direct `VistaRESTAdapter(...)` is a 7th copy (CLAUDE.md §1 DRY: shipping the 4th
  instance is forbidden). Consolidating the existing six is the named follow-up.
- **New features read the mirror, not Vista.** A new live call needs a reason (freshness the sync
  cannot give) written in the slice.
- **New code depends on `Imovel` / `PropertyData`, never on Vista field names** (`ExibirNoSite`,
  `ObsVenda`, `Codigo`). Vista vocabulary stops at `vista/normalizers.py` / `imovel_normalizer.py`.
- **Keys:** per org in the DB, last-4 only in UI, redacted in every error path (a third HTTP path
  redacts too — `vista.md` § Credential echo).
- **Calibrate fields by probing, never by guessing** — `accepted = requested − rejected` from the
  400, the bogus-code probe for detail endpoints, `listarcampos` before declaring absence (memory
  `feedback_gated_surface_assumptions_rot`).

### 11.3 Exit plan — so retirement is a swap
1. **Ownership of data.** The mirror already holds the catalogue plus the verbatim `vista_raw`
   payload per listing (`040_imoveis.sql:130-132`) — enough to re-derive our model without Vista.
   Gaps to close before exit: clients (`/clientes`), owners (`proprietarios`), history relations
   (`historicos`, `prontuarios`), notes (`ObsVenda`/`ObsLocacao`), photos (`edicao_fotos/services/vista_fotos.py`
   pulls on demand). Plan a full **export run** into our tables/Storage (a `noctus.dev.*` tool, MCP-first)
   and keep it re-runnable until cut-over.
2. **Flip the source of truth.** Today "Vista wins" on divergence. At exit our tables become the
   source; the divergence policy is retired, the sync becomes a one-way final import, then off.
3. **The seam is the swap point.** Replacements implement `VistaCRMAdapter`'s domain contract
   (rename to a CRM-neutral `CrmAdapter` when the second implementation appears — not before) or
   simply read our own tables. Callers that already use the factory/mirror change nothing.
4. **Remove the direct calls first** (§ 11.1 🔴 rows) — every caller that bypasses the factory is a
   place the swap would have to touch.
5. **Retire in order:** live calls → sync job → MCP `mcp/vista` → skill `noc-refs-sheet` §2b source
   (re-point to our tables) → seed package (when no consumer remains) → `vista_raw` kept as archive.
6. **Contractual/LGPD:** confirm export rights with the vendor and the data-category intake for what
   we now store as controller (`KB § PATTERNS/security/lgpd.md`).

**Anti-patterns.** A new table column named after a Vista field. A FE page calling `/api/vista/...`
live. Copying Vista's `Codigo` formatting rules into a second place (codes are canonical `ONE<digits>`,
migration `062_codigo_imovel_canonical.sql`).

---

## 12 · Checklists

### 12.1 New integration (vendor)
- [ ] Seed-first discovery: `noctus.dev.kb_search` / `code_search` "<vendor>"; existing `integrations/<vendor>/`? (CLAUDE.md §1 "grep for the existing mechanism").
- [ ] Vendor doc `KB § INTEGRATIONS/<vendor>.md` created/updated: auth, endpoints used, limits, error model, version pin + expiry, sandbox, webhook shape, "verified vs transcribed" status (the `olx.md` / `imovelweb.md` legend), change log.
- [ ] Adapter = Protocol + Fake + Real + factory in the seed; domain types out; one HTTP chokepoint with `rate_limit`, timeout, redaction.
- [ ] Credentials per § 1.1; consumer uses `resolve_fake_or_refuse`.
- [ ] Status endpoint with the five honest states (§ 9).
- [ ] LGPD data-category intake before ingesting personal data (`KB § PATTERNS/security/lgpd.md`); probe field sets without reading records where possible.
- [ ] Owner-gated steps (console, App Review, verification, keys) listed with lead times; runbook in the vendor doc (`oauth-patterns.md` §6 template).
- [ ] Exit consideration: what would removal touch? (§ 11.3 shape).

### 12.2 New webhook → § 3.1. ### 12.3 OAuth app setup → § 2.3 + `KB § GUIDES/google-oauth-setup.md` / `KB § INTEGRATIONS/google-oauth-console-setup.md` / `KB § INTEGRATIONS/meta-setup.md` / `KB § INTEGRATIONS/meta-app-verification.md`.

### 12.4 Vendor version bump
- [ ] Read the vendor changelog for every version between pin and target (Meta: Graph + Marketing API; WAHA: each monthly entry).
- [ ] Change the single pinned constant (`DEFAULT_GRAPH_VERSION`, `meta_cloud_client.DEFAULT_BASE_URL`, WAHA image tag via `waha-instances.yml` + `noctus.dev.waha_instance render`).
- [ ] Re-run the gated live probes; diff real payloads against mapper fixtures; read back any config PUT.
- [ ] Update the vendor doc's pin + "available until" + change-log line, same commit.
- [ ] Deploy behind `predeploy_check`; watch the vendor's error classes for 24 h.

---

## 13 · Worked examples (grounded)

### A — WAHA inbound webhook (seed `create_whatsapp_webhook_router`)
`seed/lib/backend/noctusai_lib/integrations/whatsapp/router.py:51-149`.
- ✅ Raw body read once (`:97`), HMAC verified with WAHA's real scheme (`X-Webhook-Hmac` +
  `-Algorithm`, sha512 default, `:94-117`), then parsed (`:119-125`).
- ✅ Non-message events answer 200 `ignored` so WAHA does not retry (`:129-131`).
- ✅ Dedup on `provider_message_id` before the consumer (`:138-144`) — kills the `message` +
  `message.any` double run.
- ⚠️ Unsigned when the secret is unset: CRITICAL log at mount (`:84-88`) and `handle_unsigned_webhook`
  accepts unless `WEBHOOK_REQUIRE_SIGNATURE=1` (`webhook_signatures.py:69-87`). Fix = the seed P0.
- ⚠️ Claim without release: if `on_message` raises (`:146`), the id stays claimed for the dedup TTL
  and WAHA's retry is dropped as `duplicate`. Consumers must persist the message (durable
  `message_store` UNIQUE) **before** any fallible work inside `on_message`, or the seed grows
  `WebhookDedup.release()` used in a `try/except: release; raise`.
- ⚠️ No replay window possible: WAHA's `X-Webhook-Timestamp` is not covered by the HMAC (WAHA
  "Events"), so durable dedup is the replay defence.
- Retries are configured per webhook (`config.webhooks[].retries` — constant/linear/exponential with
  20 % jitter) and must survive config PUTs (`set_webhook` merge, `whatsapp.md` §4a).

### B — Google OAuth with PKCE as the CSRF binding (social-wiring integration accounts)
`products/social-wiring/backend/app/routers/integration_accounts_router.py`.
1. Provider built with `use_pkce=True` (`:509-525`); 503 when unconfigured (`:610-617`) — honest refusal.
2. `/start` is authenticated (`Depends(get_current_user_org)`, `:595`); `state = {org_id}:{nonce}:{marca}`
   (`:643`); the PKCE verifier is stored in Redis under the state, 10 min TTL (`:480-483,654-662`).
3. `/callback` has no JWT (Google redirect); it parses the org from the state (`:699-722`), fetches and
   deletes the verifier (single-use, `:742-750`), and exchanges with it (`:757-766`). An attacker-made
   state has no verifier, so `GoogleProvider.exchange_code` refuses (`google_provider.py:214-219`) —
   the state is effectively server-bound, and code injection without the verifier fails (RFC 7636 §4.6).
4. What to keep in mind: the binding is to the org, not to the browser session (RFC 6749 §10.12 asks
   for the user agent); acceptable here because the worst case is an attacker attaching **their own**
   account to **their own** org. A flow whose callback grants something to the *victim's* session needs
   a cookie-bound state.
5. Token bundle keeps `refresh_token` + `expires_at` (`:775-781`); persistence must never overwrite a
   stored refresh token with `None` (`google_provider.py:26-31`).
6. Gaps vs the canon: Testing-mode 7-day refresh expiry is a deployment fact the status surface should
   show; disconnect should call `revoke` (`google_provider.py:264`) before deleting.

### C — Meta Lead Ads `leadgen` receiver (social-wiring)
`products/social-wiring/backend/app/modules/meta_ads/routers/leadgen_router.py` + seed parser
`seed/lib/backend/noctusai_lib/integrations/meta/leadgen_webhook.py`.
- Two secrets kept apart (`:11-18`); GET handshake in constant time, challenge echoed as a string,
  uniform 403, rate-limited (`:104-139`).
- POST verified by `webhook_endpoint(scheme="sha256_prefixed", bypass_when_unset=False)` (`:176-186`) —
  a forged lead would write PII and spawn a CRM card (`:20-26`).
- Everything past verification is 200 (`:189-197`) because Meta retries non-2xx for 36 h and the
  durable inbox row is the recovery path.
- Two dedup layers: `record_event` (durable) + Redis `claim` with a **24 h TTL** chosen for Meta's
  retry window, not WAHA's millisecond race (`:162-169,263-266`).
- Thin payload: only `leadgen_id`; PII fetched from Graph in a worker thread, heavy fan-out after the
  response (`:246-294`) — the fix for the 2026-10-05 65 s inline stall.
- `leadgen_update` routed separately and first (`:214-222`); unrecognised content recorded (`:226-233`).
- Canon gaps to carry: `leads_retrieval` needs Advanced Access for System Users; Meta BUC `80005`
  (Lead Gen throttle) is not classified as rate-limited by `MetaGraphError` (§ 4); reconciliation for
  missed deliveries is the scheduled lead sync (`KB § INTEGRATIONS/meta-leads-checklist.md` Slice 0).

---

## Composes-with
`KB § PATTERNS/backend/backend-craft-canon.md` (§4.5 idempotency, §6 reliability) ·
`KB § PATTERNS/security/webhook-signatures.md` (5-pin contract) · `KB § PATTERNS/security/appsec-craft-canon.md` (§7 OAuth/JWT) ·
`KB § PATTERNS/common/outbound-rate-limiting.md` · `KB § PATTERNS/backend/seed-fake-real-adapter.md` ·
`KB § INTEGRATIONS/oauth-patterns.md` · `KB § PATTERNS/security/lgpd.md` · `KB § PATTERNS/devops/sre-craft-canon.md` ·
`KB § PATTERNS/backend/whatsapp-chatbot-seed.md` · `KB § MCP-SERVERS/waha.md`.

## Sources

All accessed 2026-11-05 (fetched by W2-S6 unless marked).
- RFC 6749 — The OAuth 2.0 Authorization Framework — https://www.rfc-editor.org/rfc/rfc6749.html — §3.1.2 redirect registration, §3.3 scope, §4.1.2 code lifetime/single use, §5.2 invalid_grant, §6 refresh, §10.4, §10.12 CSRF (§ 2).
- RFC 9700 — Best Current Practice for OAuth 2.0 Security — https://www.rfc-editor.org/rfc/rfc9700.html — §2.1 CSRF/redirect/mix-up, §2.1.1 PKCE + code injection, §2.1.2 implicit, §2.2.2 refresh tokens, §2.3 privilege restriction, §4.7.1 (§ 2).
- RFC 7636 — Proof Key for Code Exchange — https://www.rfc-editor.org/rfc/rfc7636.html — §4.1 verifier, §4.2 S256, §4.6, §7.1 entropy (§ 2, ex. B).
- RFC 7009 — OAuth 2.0 Token Revocation — https://www.rfc-editor.org/rfc/rfc7009.html — §2.1–§2.2 (§ 2.1).
- OpenID Connect Core 1.0 — https://openid.net/specs/openid-connect-core-1_0.html — §2 nonce, §3.1.3.7 ID token validation (§ 2).
- Standard Webhooks spec v1.0.0 — https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md (landing: https://www.standardwebhooks.com/) — headers, signed content, retries, SSRF, thin payloads (§ 3, § 6).
- RFC 6585 — Additional HTTP Status Codes — https://www.rfc-editor.org/rfc/rfc6585.html — §4 429, Retry-After MAY (§ 4).
- RFC 9110 — HTTP Semantics — https://www.rfc-editor.org/rfc/rfc9110.html — §10.2.3 Retry-After = HTTP-date / delay-seconds (§ 4).
- IETF draft-ietf-httpapi-ratelimit-headers-11 — https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/ — RateLimit fields; Retry-After precedence (§ 4).
- AWS Builders' Library — Timeouts, retries and backoff with jitter — https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter — single retry layer, jitter, idempotency (§ 4).
- Google Cloud Storage — Retry strategy — https://docs.cloud.google.com/storage/docs/retry-strategy — retryable codes, conditional idempotency, no stacked retries (§ 4, § 5).
- Martin Fowler — CircuitBreaker — https://martinfowler.com/bliki/CircuitBreaker.html (§ 4).
- Microsoft Azure Architecture Center — Anti-Corruption Layer pattern — https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer — pattern, costs, Evans attribution (§ 1). (The martinfowler.com bliki URL for ACL returned 404.)
- Pact — What is Pact good for? — https://docs.pact.io/getting_started/what_is_pact_good_for — poor fit for public/third-party APIs (§ 8); overview https://docs.pact.io/.
- Meta — Graph API changelog: versions — https://developers.facebook.com/docs/graph-api/changelog/versions — release/expiry dates v18.0–v26.0 (§ 7).
- Meta — Graph API versioning — https://developers.facebook.com/docs/graph-api/guides/versioning — ≥2-year window; expired ⇒ next-oldest (§ 7).
- Meta — Rate limits — https://developers.facebook.com/docs/graph-api/overview/rate-limiting — platform vs BUC, headers, codes 4/17/32/613/800xx, WABA limits (§ 4, § 10).
- Meta — Getting started with Webhooks — https://developers.facebook.com/docs/graph-api/webhooks/getting-started — verification, X-Hub-Signature-256, batching ≤1000, 36 h retries, mTLS (§ 3).
- Meta — App Review — https://developers.facebook.com/docs/app-review (§ 2.2).
- Meta — Access levels — https://developers.facebook.com/docs/graph-api/overview/access-levels — Standard vs Advanced, business verification since 2023-02-01, annual Data Use Checkup (§ 2.2).
- Meta — Long-lived access tokens — https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived (§ 2).
- Meta — Batch requests — https://developers.facebook.com/docs/graph-api/batch-requests (§ 4).
- Meta — Paginated results — https://developers.facebook.com/docs/graph-api/results (§ 4).
- Meta — WhatsApp Cloud API overview — https://developers.facebook.com/docs/whatsapp/cloud-api/overview/ — 80 mps, pair rate limit (§ 10).
- Meta — WhatsApp messaging limits — https://developers.facebook.com/docs/whatsapp/messaging-limits — tiers, portfolio-level, scaling path (§ 2.2, § 10).
- Meta — WhatsApp template fundamentals — https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview — categories, review ≤24 h, quality/pause (§ 10).
- WAHA — Events / webhooks — https://waha.devlike.pro/docs/how-to/events/ — headers, HMAC sha512, retries policies (§ 3, ex. A).
- WAHA — How to avoid blocking — https://waha.devlike.pro/docs/overview/how-to-avoid-blocking/ — 463/475, reply-first sequence (§ 10).
- WAHA — Changelog — https://waha.devlike.pro/docs/overview/changelog/ — YYYY.M.patch, 2026.10.1, 2026.6.1 Plus→Core (§ 7).
- Google — Using OAuth 2.0 to access Google APIs — https://developers.google.com/identity/protocols/oauth2 — refresh-token expiration causes, 7-day Testing, 100-token cap (§ 2.1).
- Google — OAuth 2.0 for web server applications — https://developers.google.com/identity/protocols/oauth2/web-server — state, offline, prompt=consent, incremental + granular consent, revoke (§ 2).
- Google Cloud Help — OAuth app verification — https://support.google.com/cloud/answer/13463073 and https://support.google.com/cloud/answer/9110914 — sensitive/restricted, annual re-verification (§ 2.2).
- Google Calendar — Manage quotas — https://developers.google.com/calendar/api/guides/quota (§ 4).
- Google Calendar — Push notifications — https://developers.google.com/calendar/api/guides/push (§ 3, § 10).
- Google Calendar — Synchronize resources efficiently — https://developers.google.com/calendar/api/guides/sync — syncToken, 410 (§ 4).
- YouTube Data API — Getting started — https://developers.google.com/youtube/v3/getting-started and Quota calculator — https://developers.google.com/youtube/v3/determine_quota_cost (§ 7).
- Stripe — Webhooks — https://docs.stripe.com/webhooks — duplicates, ordering, 2xx fast, async queue, 5-min tolerance, 3-day retries, secret rolling (§ 3).
- Stripe — Idempotent requests — https://docs.stripe.com/api/idempotent_requests (§ 5; audit-verified via backend canon).
- Asaas — Sobre os webhooks — https://docs.asaas.com/docs/sobre-os-webhooks — at-least-once, event id, `asaas-access-token`, 15-failure pause, 14-day retention (§ 3).
