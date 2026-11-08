# sso-session-lifecycle-2026-11 — login only at core; every product entry is a fresh, product-bound session

> **Design record** (MADR-shaped, per `KB § PATTERNS/architect/architecture-craft-canon.md` §3/§14).
> Status: **proposed** — direction owner-approved 2026-11-08; the items in "Owner decisions" are open.
> Evidence base: `origin/dev` @ `9e459623b` (local `dev` checkout is behind; `BackToCore.tsx`,
> `product-landing.ts`, `sso_regime.py` exist only on origin/dev). GoTrue source: `supabase/auth`
> master @ `35307ce6c1ca` (2026-11-06). Supabase docs read 2026-11-08.
> **Unverified** items are marked ⚠ and never used as the basis of a verdict without saying so.
> Composes with: `project-history/roadmaps/sso-identity-hardening-2026-10.md` (P2.x, T6, Q1) and
> `project-history/roadmaps/core-host-retirement-2026-11.md` (core host → apex; this record never hard-codes a host —
> everything goes through `env.CORE_URL` / `resolve_product_url("core")`).

## Tier

**T2 overall** (new seam in the seed auth dependency, new public core endpoint, new table, change to the
seed's unauthenticated routing default). **T3 parts**: the Supabase API-key/IP-forwarding change (provider
config) and the one-shot sweep of legacy product sessions (touches live users) need the owner's recorded go.

## Context (what the code does today)

| Fact | Evidence |
|---|---|
| Each origin holds its own GoTrue session. Core: `localStorage` `noctus_token` / refresh, refresh **proxied through core's backend** | `products/core/frontend/src/lib/api.ts:23`, `:71` (`/api/auth/refresh`); `products/core/backend/app/routers/auth.py:345` |
| Every SSO redemption mints a fresh session: admin `generate_link(magiclink)` + `verify_otp` on a throwaway anon client | `products/core/backend/app/routers/sso.py:419-477` (`_generate_session`) |
| The mint lock is per **(email, org, product)** and in-process | `sso.py:431-437` |
| `_session_cache` is now only a lock map (no `get`/`set` callers); the "above 60s Supabase rate limit" comments are stale | `sso.py:46-53`, `:112`; grep of `_session_cache.get(`/`.set(` in `products/core/backend/app` = 0 |
| Rate-limit classifier treats `"user not allowed"` as a rate limit | `sso.py:402-416` |
| `/token`, `/launch`, `/session` limited 20/min per visitor IP (`CF-Connecting-IP`) | `sso.py:178,272,522`; `seed/lib/backend/noctusai_lib/api/rate_limit.py` `client_ip_key` |
| `GET /api/sso/launch/{slug}` authenticates via the `Authorization` **header**; no browser caller exists (tests only) | `sso.py:271-276`; `git grep sso/launch` → only tests |
| Core's launcher opens products in a **new tab** via `POST /api/sso/token` → `redirect_url` | `products/core/frontend/src/pages/Dashboard.tsx:105-108` |
| Return target is catalog-derived + same-site guarded; `next` is path-only | `products/core/backend/app/sso_regime.py:47-66`, `:210-216`; `seed/lib/frontend/src/components/SSOCallback.tsx:99-106` |
| Products mount their own password `Login`, `ForgotPassword`, `AcceptInvite`; Landing "Entrar" → product `/login` | `seed/framework/frontend/src/app.tsx:428,468,469`; `products/agents/frontend/src/pages/Login.tsx` (`LoginForm` + `supabase`); `products/{agents,social-wiring}/frontend/src/pages/Landing.tsx:98/100` |
| Product with no session → Landing (or `unauthRedirect`); no re-SSO | `app.tsx:344-366`; `seed/lib/frontend/src/auth.ts:446-466` |
| "Sair" = `signOut({scope:'global'})` → product landing `/` | `seed/framework/frontend/src/layout.tsx:266`, `:425-435`; `product-landing.ts:13-22` |
| "Voltar" = a plain `<a href={CORE_APP_HOME}>` — revokes nothing | `seed/framework/frontend/src/components/BackToCore.tsx:10-20`; `layout.tsx:258,487` |
| Session-ending contract: only explicit "Sair" may hit the server | `seed/lib/frontend/src/session-ending.ts:1-30` (its line 25 still says `core.noctusai.com` — drift vs the apex roadmap) |
| Core login enforces a cap of **5** sessions/user, deleting the **oldest** | `products/core/backend/migrations/006_session_cap.sql`; `auth.py:178` |
| Precedent: rows bound to the token's `session_id` + `EXISTS auth.sessions` in RLS | `products/core/backend/migrations/070_platform_org_selections.sql:336-338`; `072_audit_acting_write.sql:83`; `app/services/brand/service.py:138-142` |
| Active fleet: `agents, core, monica, seed, social-wiring` — all `live` ⇒ the legacy (query-token) regime currently serves **no awake product**; orbity/p-studio are asleep | `deploy/fleet/active-scope.txt` == `deploy/fleet/build-scope.txt` (origin/dev); `sso_regime.py:34-38` |
| Supabase: one hosted project `nyplttplcoyiiqjrvtiw`, **Free plan** (owner won't pay for Pro) | memory `reference_supabase_projects_architecture.md` |

---

## A. Rate limit on the mint

**Verdict: keep `generate_link(magiclink)` + `verify_otp` as the mint. Fix what actually bites: the
`/verify` limit is counted per IP, and all of it comes from core's one server IP. Mint less, serialize
per user, and classify GoTrue errors by code.**

### What actually limits it (vendor-verified)

| Call | Limiter | Evidence |
|---|---|---|
| `POST /admin/generate_link` | **None.** Admin routes have no `limitHandler`; `adminGenerateLink` does no `MaxFrequency` check | GoTrue `internal/api/api.go:368-403`; `internal/api/mail.go` `adminGenerateLink` (magiclink branch sets `RecoveryToken`/`RecoverySentAt`, creates a one-time token, no frequency check) |
| `POST /verify` (what `verify_otp` calls) | `limiterOpts.Verify`, **IP-keyed**, default 30 / 5 min, burst 30 ("Verification requests … IP address … customizable") | `api.go:270`; `internal/conf/configuration.go:487` (`RATE_LIMIT_VERIFY` default 30); Supabase docs *Auth → Rate limits* |
| `POST /token` (core's password login + core's **proxied** refresh) | IP-keyed, 150 / 5 min, burst 30 | docs (same page); `configuration.go:488` |
| `GET /user` (every backend's token validation) | **not** limited (only `PUT /user` is) | `api.go:281-283` |
| How the IP is chosen | `Sb-Forwarded-For` if forwarding is enabled **and** the request uses a **secret key** (`sb_secret_…`; "legacy anon/service_role … not supported"), else the edge IP | `internal/api/middleware.go` `performRateLimiting`; docs (IP Address Forwarding, `security_sb_forwarded_for_enabled`) |

So:
- **The limit that bites is project-wide in practice.** Every mint's `/verify` originates from core's
  server, so the whole fleet shares one bucket of 30 burst, refilling about 6/min. A single user looping
  core→product→core→product is fine. Roughly 6 or more entries per minute fleet-wide, sustained, returns
  429 `over_request_rate_limit`.
- **There is no per-email 60 s limit on the admin mint.** The "60 seconds per email" in `sso.py:46-49`,
  `:112`, `:407-408` is not supported by current GoTrue source. ⚠ Unverified: the Auth version the hosted
  project runs (dashboard). It may also have been true of an older release.
- **"User not allowed" is `ErrorCodeNotAdmin`** (`internal/api/auth.go:93`). It means the admin client did
  not carry service_role, which is the poisoning incident documented at `sso.py:449-457`. Turning it into
  a retryable 429 (`sso.py:415`) hides a misconfiguration behind a 60 s countdown.
- **Real side effects of the mint, found in the source:**
  1. The magiclink mint writes the user's single `recovery_token` slot. Two concurrent mints for one user
     into two products overwrite each other. The lock is per product (`sso.py:436`), so it does not
     prevent this, and the losing `verify_otp` fails as an expired token, which surfaces as a 500.
  2. A mint invalidates a password-reset email that is still pending.
  3. A mint sets `recovery_sent_at`, so the user's own "esqueci a senha" within 60 s gets 429
     `over_email_send_rate_limit` (`mail.go:402,487` `validateSentWithinFrequencyLimit`).

### Options weighed

| Option | Verdict | Why |
|---|---|---|
| **A1. Keep generate_link + verify_otp, hardened** | **CHOSEN** | Only GA way to create a real, revocable GoTrue session for an existing user server-side. Keeps PostgREST RLS (`auth.uid()`), supabase-js refresh, `session_id`-bound features (`070:336-338`, `072:83`), `amr`/`aal` |
| A2. Custom JWT signed by core | Rejected | No refresh token → re-SSO every expiry; nothing to revoke (Voltar/Sair become client-only); breaks `session_id`-bound org-picker and audit RLS; MFA `aal` meaningless; needs the project signing secret in core (⚠ not possible at all if the project moves to asymmetric signing keys — unverified) |
| A3. Supabase admin "create session" | Does not exist | Admin routes enumerated: `api.go:368-460` (users, factors, passkeys, generate_link, sso providers, oauth clients, custom providers) |
| A4. Core holds one session per (user, product) and re-hands it out | Rejected — already tried | Re-issuing a pair to two holders makes GoTrue reuse-detection revoke the chain; that is the 2026-10-22 incident (`sso.py:422-427`) |
| A5. Supabase OAuth 2.1 server (products as OAuth clients, PKCE, `client_id` claim) | **Revisit trigger** | Right long-term shape (also answers B). Docs: "OAuth 2.1 server is in beta"; tokens carry `client_id`, usable in RLS. Beta ⇒ not for a prod auth path now |

### The hardening (slice S1)
1. **Mint less (structural).** Re-entry mints only when the product origin has **no** session (D). Background tabs never mint (D, multi-tab). Voltar's revoke is the only thing that forces a re-mint.
2. **Per-end-user bucket.** Send `Sb-Forwarded-For: <CF-Connecting-IP>` on the `verify_otp` call (and on core's proxied `/token` login/refresh). This needs core's server-side Supabase calls on a **secret key** and forwarding enabled. That is an **owner decision** (provider config, T3). Interim if declined: raise `rate_limit_verify` via the Management API (`PATCH /v1/projects/{ref}/config/auth`). ⚠ Whether the Free plan allows it is unverified. The bucket stays shared.
3. **Serialize per email, not per product**, around generate_link→verify (the recovery slot is per user). Retry the pair once on GoTrue `otp_expired`. ⚠ The in-process lock is enough only if core runs one worker; worker count is unverified.
4. **Classify by GoTrue `code`, not substrings.** `over_request_rate_limit` → 429 with `Retry-After: 10` (refill ≈ 1 per 10 s at 30/5 min). `not_admin` → loud 500 ("admin client is not service_role"), never 429. Drop the `"user not allowed"` and `"60 seconds"` matches.
5. **Telemetry:** one `sso_mint` log line per mint with `outcome` + GoTrue `code` (never tokens). Alert on any `over_request_rate_limit`.

**Cost:** one core file (`routers/sso.py`) plus its tests. The `Sb-Forwarded-For` part also needs a key
rotation in core's env.

---

## B. Product-session scope at core

**Verdict: yes, a product session is accepted by core's entire API, including admin routes. Bind it:
a server-side registry `session_id → product` is written at mint. The seed auth dependency reads it, and
core accepts product sessions only on routes that declare it. Refuse with 403, never 401.**

### Evidence
- Core's `get_current_user` is the framework dependency (`products/core/backend/app/dependencies.py:44-50`). It validates via GoTrue `GET /user` (`seed/lib/backend/noctusai_lib/api/auth/__init__.py:200-225`), so **any** live session of the shared project passes.
- The license gate is a no-op for core (`seed/lib/backend/noctusai_lib/domain/licensing.py:394`, docstring "No gate / core … no-op").
- Tokens carry **no product claim**. They are minted by `verify_otp` (`sso.py:458-463`). The only product context goes into `user_metadata` (`sso.py:626-641`), which is per user, last writer wins, and never an authz input (memory `feedback_rls_never_key_on_user_metadata`).
- Admin routes check `noctus_users.role` plus `require_admin_assurance` (`dependencies.py:63-88`). The fleet MFA default is seeded `'off'` (`migrations/060_mfa_policy.sql:50`; ⚠ the live row is unverified). An SSO-minted session is `aal1` (GoTrue `verify.go:185,285` issue with `models.OTP`).
- ⇒ **An XSS on any product origin, run against a platform admin's product session, gets core's admin API.**
- Product frontends **do** legitimately call core with their product session: `POST /api/sso/token` (bell, `seed/framework/frontend/src/infra.tsx:149`), `GET/PUT /api/me/consents` (`useConsents.ts:73`, `useUpdateConsent.ts:48`), `GET /api/brand/current` (`BrandProvider.tsx:161`), `/api/admin/llm-spend/{org}` (`useLLMSpend.ts:68`; router `admin_llm_spend.py:37`), `/api/platform/credentials`. So a blanket "core refuses product sessions" would break products.

### Options
| Option | Verdict |
|---|---|
| **B1. Registry `public.sso_product_sessions(session_id uuid PK, user_id, product_slug, jti, minted_at)`**, written in `_generate_session` from the new access token's `session_id`. The seed dependency resolves `session_product` (cached with the token, same 30 s TTL). Core routes opt in with `@product_session_ok(reason=…)`. Default: refuse with **403 `sessao_de_produto`** | **CHOSEN.** Complete by construction (product sessions are born in exactly one place). Same `session_id`-binding idiom as `070`/`072`. Also gives a place to record core's assurance level at mint (E, MFA) |
| B2. Custom Access Token Hook adds `noc_product` | Rejected now. The first token is issued **inside** `verify` before core knows the `session_id`, so the first access token (up to the JWT expiry) lacks the claim. The hook is project-wide, so a hook failure blocks every login. Docs: hook input carries `session_id`, `authentication_method` |
| B3. Discriminate by `amr` (`otp` = SSO) | Rejected. Core's own recovery/OTP logins are also `otp` (verify issues `models.OTP` for magiclink **and** recovery) |
| B4. OAuth 2.1 `client_id` claim | Revisit at GA (see A5) |

**Why 403 and not 401:** a 401 that refresh cannot fix makes every seed SPA declare the session dead and
log the user out (`__init__.py` block comment above `:161`). A product session wandering onto a core-only
route is a refusal, not a death.

**Product side (same seam, observe first):** product backends may refuse a session bound to a **different** product (403). They accept core sessions and their own.

**PostgREST gap (named, not solved here):** B1 guards the backends, not direct PostgREST reads. Platform-admin RLS policies can add `NOT public.is_product_session()` (a `STABLE SECURITY DEFINER` lookup on `auth.jwt()->>'session_id'`, evaluated once per statement via `(select …)`). ⚠ Which policies key on platform-admin was not counted. Destination: `NOC-REMEDIATE[sso-product-session-postgrest]` in S8.

**Transition (expand → migrate → contract):** sessions minted before the registry are unregistered and look exactly like core sessions.
- Phase 1 (observe) only logs `product_session_on_core_route`.
- Before enforcing, run a **measured** sweep. First count, then delete `auth.sessions` whose AMR is `otp`, created before the cutover, and absent from the registry. ⚠ Confirm core has no OTP-born logins today (core `Login.tsx` shows password/signup/OAuth only) by reading the AMR distribution first.
- Once D has shipped, swept users silently re-enter and get a registered session.

**Cost:**
- One indexed PK lookup per token per process per 30 s, folded into the existing worker hop. Fails closed with 503 (like the license gate).
- One table (service-only tier, RLS on, no client policies).
- One decorator on about 5 core routes.

---

## C. Voltar's server revoke

**Verdict: Voltar = `supabase.auth.signOut({ scope: 'local' })` on the product origin. Add **no** new
per-request revocation check: seed backends already check revocation on every token-cache miss. Keep
the `auth.sessions` existence check only on audit and sensitive writes, as today.**

### Evidence
- `scope=local` makes GoTrue delete **that** session row (`internal/models/sessions.go:369-371` `LogoutSession`). supabase-js clears local storage **before** the request, so leaving never depends on the network (`auth-js GoTrueClient.ts` `_signOut`, scope `local` branch).
- GoTrue `GET /user` loads the session named by the JWT's `session_id`. A deleted session answers **403 `session_not_found`** (`internal/api/auth.go:173-182`). Every seed backend validates through `GET /user` (`__init__.py:225`), with a **30 s positive cache** (`token_cache.py:49`, owner-approved 2026-10-21).
- ⇒ **After Voltar, the revoked product token is refused by every backend within 30 s or less**, and immediately on a process where it is not cached.
- Direct PostgREST reads honour the JWT until `exp` (Supabase *Sessions* doc: check `session_id` against `auth.sessions` "only for the most sensitive actions"). ⚠ The project's JWT expiry is not in the repo. The roadmap Q1 assumes the 3600 s default; read it from the dashboard.
- Threat fit: Voltar is a navigation by the same user in the same browser, not a security boundary. A stolen token is not stopped by the victim pressing Voltar. B and an exp-bounded token are the controls for theft.

### Options and cost
| Option | Cost | Verdict |
|---|---|---|
| Per-request `auth.sessions` check in every RLS policy | +1 PK probe per statement on every read; every policy rewritten | Rejected (disproportionate) |
| Shorten JWT expiry | More refreshes. Core's refresh is **proxied** (`api.ts:71`), so it shares core's IP bucket on `/token` (150/5 min) | Not before A's `Sb-Forwarded-For` lands |
| **As-is backends + session check on audit/sensitive writes (existing `070:338` idiom)** | 0 new | **CHOSEN** |

**Contract change:** `session-ending.ts` gains a third ending, `leaveProduct` (explicit, **local**
scope, never global), next to `endSessionLocally` (expiry, no server call) and `signOutExplicitly` (Sair,
global). Its header comment is updated, including the stale `core.noctusai.com` on line 25.

---

## D. Silent re-entry for a product with no session

**Verdict: a seed `ReentryGate` in the unauthenticated branch sends the tab to the core **frontend**
route `CORE_URL/login?produto=<slug>&next=<path>&prompt=none|login`. Core either launches immediately
(it has a session) or shows login (`prompt=login`), or bounces back with `#sso=login_required`
(`prompt=none`). Loop-guarded, visibility-lazy, one tab at a time.**

**Why not `/api/sso/launch/{slug}`:** it authenticates from the `Authorization` header (`sso.py:271-276`),
and core's session lives in core-origin localStorage (`api.ts:23`). A top-level navigation cannot carry
it. Core's FE must mint via `POST /api/sso/token` (same-origin, so the P2.2 bind cookie is set as today)
and then `location.replace(redirect_url + withNextPath)`.

### Decision table (seed, `reentry.ts`; marker key `noctus:entry` in product-origin localStorage)
| Situation | Marker | Action |
|---|---|---|
| Fresh visit, **protected path**, no session | any | → core `prompt=login` (owner item 4) |
| Fresh visit, `/`, no session | absent / `signed-out` | Landing (strangers and crawlers never bounce) |
| Fresh visit, `/`, no session | `left` / `active` | → core `prompt=none` |
| Tab loses its session (SIGNED_OUT confirmed, `auth.ts:464`) | `left` (Voltar elsewhere) / `active` (revoked elsewhere) | Wait until `visibilityState==='visible'`, then → core `prompt=login` keeping the path |
| Tab loses its session | `signed-out` (Sair) | → product landing `/` (owner item 5) |
| Back from core with `#sso=login_required` | — | Set marker `signed-out`, show Landing, no error |

The marker is written by:
- `SSOCallback` success → `active`
- `leaveProduct` → `left`
- `goToProductLanding` after Sair → `signed-out`

### Loop and failure guards
- `prompt=none` with no core session returns via a catalog-resolved URL. It never loops, because the return sets `signed-out`.
- Per-tab `sessionStorage` counter: 3 core round trips within 2 min without a successful redeem → stop and show "Entrar" (no auto-redirect).
- Core-side refusals (403 no license, 409 cross-site, `sso.py:207-221`) render on **core** and never bounce back.
- A 429 on redeem is already handled by `SSOCallback`'s countdown (`SSOCallback.tsx:184-185`).

### Multi-tab
- supabase-js broadcasts `SIGNED_OUT` to every tab of the same storage key (`GoTrueClient.ts:537-560`, `5257`). The seed then re-reads storage (`auth.ts:446-466`). This is why Voltar in one tab ends the others.
- Hidden tabs do **nothing**. Only a visible tab re-enters, under `navigator.locks.request('noctus-reentry:<slug>', {ifAvailable:true})`. Core FE already uses Web Locks for refresh (`api.ts:48-58`).
- A `noctus:reentry-inflight` timestamp (60 s) stops two side-by-side visible windows from minting twice.
- When the winning tab's `SSOCallback` stores the new pair, supabase-js broadcasts `SIGNED_IN` and the other tabs adopt it with no core round trip.
- Net: N tabs → 1 mint, no error screen.

**Cost:** seed FE only (one new module, `app.tsx` branch, small hooks in `auth.ts`, `SSOCallback.tsx`, `product-landing.ts`). Every product inherits it with zero per-product code.

---

## E. Central login page

**Verdict:**
- Login lives at **core `/login?produto=<slug>&next=<path>[&prompt=none]`**.
- The return target is a **catalog slug, never a URL**. Core resolves the URL server-side through `resolve_launch_base` plus the same-site guard (`sso_regime.py:47-52,210-216`), and `next` stays path-only (`SSOCallback.tsx:99-106`).
- That is the allowlist, with no open redirect by construction: there is no URL parameter to abuse.

- **Product identity ("Entrar no Agentes"):** new public endpoint `GET /api/sso/produto/{slug}` → `{slug, nome, icone, landing_url}`. It covers only `ativo` catalog rows and returns 404 otherwise. Rate-limited per visitor IP. Access tier `public`, category `auth` (`KB § PATTERNS/security/access-tiers.md`). `landing_url` is the `prompt=none` bounce target. It lives in a **new router file** so it does not collide with `sso.py`.
- **Already logged in at core:** instant entry (`/api/sso/token` → `location.replace`). Core's api client refreshes first if needed.
- **Login form:** today `Login.tsx` always goes to `/` after login (`Login.tsx:82,101`). It must carry `produto`/`next` through password login, the MFA challenge (`Login.tsx:27-29,71-74`) and **OAuth** (`oauth.py:56` fixes `redirect_to=/login`). Stash them in `sessionStorage` before leaving for the provider and consume them on return. The P2.5 "different user ends the live session" rule stays.
- **Forgot password:** core has none today (no `resetPasswordForEmail` in core FE). Add core `/esqueci-senha?produto=&next=`. It calls `resetPasswordForEmail(email, {redirectTo: CORE_URL/redefinir-senha?produto=&next=})`, and after the reset launches the product.
  - ⚠ The core URL must be in Supabase Auth's Redirect URLs (unverified).
  - The UI must show GoTrue's 429 `over_email_send_rate_limit` as a countdown, because a mint in the previous 60 s triggers it (A).
- **Invites:** product team invites are accepted by the product backend (`/api/team/accept`), and the accept page already sends credentials to core (`products/agents/frontend/src/pages/AcceptInvite.tsx` `loginPath={CORE_URL}/login`). Change it to `?produto=<slug>&next=/accept-invite/<token>`. Acceptance logic stays where the token is validated; **credential entry is only at core**.
- **Seed default:** `/login` and `/forgot-password` on every product become seed-owned redirects to core (replacing `app.tsx:428,469`). Every existing Landing "Entrar" `href="/login"` therefore works with zero product edits. The product `Login`/`ForgotPassword` props are deprecated, then removed.
- **MFA (future):** product sessions minted by SSO are always `aal1`, even when core's session is `aal2`. Turning `enforce` on for product admin routes would therefore lock admins out of products. Precondition: carry core's `aal` in the SSO token and record it in the B1 registry, then let the product gate read the recorded assurance. Owner decision (below).

---

## F. Migration plan (contract-first; ordered so a logged-in user is never stranded)

**Contract (written first, both sides build against it):**
- Core FE route `/login?produto&next&prompt`
- `GET /api/sso/produto/{slug}` schema
- Marker values `active | left | signed-out`
- Bounce fragment `#sso=login_required`
- `403 {code:"sessao_de_produto"}`
- Registry columns

Location: `products/core/CONTRACTS/sso-entry.md` (⚠ confirm the house contract path per `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md`).

| # | Slice | Files (seed vs core) | Collision | Tests | Ship gate |
|---|---|---|---|---|---|
| S1 | **Mint hardening** (A1 items 3-5; `Sb-Forwarded-For` behind a dormant setting) | core: `products/core/backend/app/routers/sso.py`, `app/config.py`; tests `tests/routers/test_sso_router.py` | C1 | "user not allowed" ⇒ 500 not 429; `over_request_rate_limit` ⇒ 429 `Retry-After: 10`; concurrent mints for one email in two products both succeed (retry on `otp_expired`); lock is per email | anytime |
| S2 | **Registry, observe** (B1 expand) | core: `migrations/1xx_sso_product_sessions.sql`, new `app/services/product_sessions.py` (+1 call line in `sso.py`); seed: new `seed/lib/backend/noctusai_lib/api/auth/session_audience.py`, `seed/framework/backend/noctusai_seed/dependencies.py` | C2 with S1 on `sso.py` (one additive line) → merge S1 first | mint writes a row; lookup cached with the token; observe never blocks; table service-only (access-tier keepers); registry outage ⇒ 503 not 401 | after S1; starts the telemetry window |
| S3 | **Central login (dormant)** (E) | core FE: `src/pages/Login.tsx`, new `EsqueciSenha.tsx`/`RedefinirSenha.tsx`, `src/main.tsx` routes; core BE: new `app/routers/sso_public.py`, `app/schemas/sso.py` (additive) | C1 | logged-in + `produto` ⇒ one `/api/sso/token` then `replace`; `prompt=none` without session ⇒ `landing_url#sso=login_required`; unknown/inactive slug ⇒ error on core, no redirect; non-path `next` dropped; OAuth round trip keeps `produto`; MFA path keeps `produto`; endpoint 404 for inactive, 409 cross-site | nothing points at it yet ⇒ safe |
| S4 | **Seed entry + re-entry** (D, seed `/login` → core) | seed: new `seed/lib/frontend/src/reentry.ts`, `seed/framework/frontend/src/app.tsx`, `seed/lib/frontend/src/auth.ts`, `seed/lib/frontend/src/components/SSOCallback.tsx`, `seed/framework/frontend/src/product-landing.ts` | C1 vs S3 (contract-first, parallel build) | decision-table unit tests; hidden tab never navigates; lock ⇒ one navigation for N visible tabs; loop guard stops at 3; `#sso=login_required` ⇒ Landing + `signed-out`; Sair ⇒ other tabs → `/`; `/login` ⇒ core URL with slug | **deploy only after S3 is live**; pilot all 3 active products |
| S5 | **Voltar revokes** (C) | seed: `seed/lib/frontend/src/session-ending.ts` (`leaveProduct`), `seed/framework/frontend/src/components/BackToCore.tsx` (primary click ⇒ leave; middle-click/new tab ⇒ plain navigation, no revoke), `seed/framework/frontend/src/layout.tsx` | C1 vs S4 (disjoint files) | `leaveProduct` calls `signOut({scope:'local'})`, **never global**; revoke failure still clears + navigates; marker `left`; other tab re-enters on focus; `LOGOUT_SCOPE` untouched | **after S4** (otherwise sibling tabs fall to Landing; not stranded, but ugly) |
| S6 | **Product password forms removed** (3 pilots) | products: `products/{agents,monica,social-wiring}/frontend/src/{App.tsx,pages/Login.tsx,pages/ForgotPassword.tsx,pages/AcceptInvite.tsx}`; keeper `check_no_product_password_form` (tooling-engineer) | C1 per product ⇒ 3 parallel | keeper red on `signInWithPassword` / `LoginForm` / `resetPasswordForEmail` under `products/*/frontend/src` (core exempt); invite page links `produto`+`next` | after S4 |
| S7 | **Declare the product-callable surface + session-cap fix** | core: `@product_session_ok(reason=…)` on `/api/sso/token`, `/api/me/consents` (GET/PUT), `/api/brand/current`, `/api/admin/llm-spend/{org}`, `/api/platform/credentials`; `migrations/1xx_session_cap_excludes_product_sessions.sql` (cap counts core sessions only, or owner raises it); keeper `check_product_session_surface` | C1 | registered product session ⇒ exactly 403 `sessao_de_produto` on an admin route; 200 on each declared route; core session unaffected | still observe |
| S8 | **Enforce** (B contract) + legacy sweep + PostgREST follow-up | seed `session_audience.py` flag flip; one-shot sweep migration (dry-run count, owner go); `NOC-REMEDIATE[sso-product-session-postgrest]` destination | C1 | `product_session_on_core_route` false-positive count = 0 for 7 days before the flip | owner go |
| S9 | **Cleanup** | core: retire `GET /api/sso/launch/{slug}` + tests (no browser caller); stale comments `sso.py:46-53,112`; delete the legacy regime when `sso_legacy_redeem`=0 (existing roadmap exit criterion); `session-ending.ts:25` host | C1 | — | last |

**Order:** S1 → S2 → (S3 ∥ S4 build) → deploy S3 → deploy S4 → S5 → S6 → S7 → S8 → S9.

**Why nobody is stranded:**
- Before S4, nothing in the products changes.
- S4 only adds re-entry where the user previously saw Landing.
- Old product bundles keep working: the regime, `/api/sso/session` and `/api/sso/token` are unchanged.
- The S8 sweep runs only after S4, so a swept session silently re-enters.
- A password change (`auth.py:312-319`, scope `others`) or a global Sair now also lands every product tab in re-entry instead of a dead end.

**Legacy regime:** no awake product is legacy today. A woken orbity/p-studio must be rebuilt anyway (promotion guard, roadmap 2026-10-10). This plan adds nothing to the legacy branch.

---

## Quality-attribute scenarios (measurable)

- **Security:** a product-session token sent to `PATCH /api/admin/*` on core returns 403 `sessao_de_produto` in 100% of requests after S8. Confirmed by S7 tests plus a prod smoke.
- **Availability:** at 15 product entries per minute fleet-wide, `sso_mint outcome=rate_limited` = 0 (after `Sb-Forwarded-For`, or the raised limit).
- **Usability:** with 3 tabs of one product open, after Voltar in tab 1, focusing tab 2 lands back on its own path in under 3 s p95, with no login prompt and no error, while core is signed in. At most one mint per focus.

## Consequences (trade-off points)

**Good:**
- A single credential surface.
- Product sessions are revocable per product and bound to their product.
- Re-entry becomes invisible.

**Bad:**
- Each product entry after Voltar costs a mint.
- A registry lookup on cache misses.
- Core becomes the single point for entry: a core outage blocks entry, though not sessions already open.

**Neutral:**
- The launcher still opens products in a new tab (`Dashboard.tsx:107`), so Voltar leaves the user with two core tabs.

## Confirmation (fitness functions)

- `check_no_product_password_form` (S6)
- `check_product_session_surface` (S7)
- S1 classifier tests
- Access-tier keepers on the new endpoint and the table
- `sso_smoke` extended with "Voltar → re-entry" and "product token on core admin ⇒ 403"
- Daily `sso_mint` / `product_session_on_core_route` counts

## Revisit triggers

1. Supabase OAuth 2.1 server leaves beta: replace the mint and B1 with `client_id`.
2. Move to Supabase Pro: session time-box, inactivity timeout.
3. `sso_mint` rate-limited outcomes are above 0 for a week after S1.
4. A second identity source verifies SSO tokens (existing `NOC-REMEDIATE[security]` audience binding).
5. Product admin MFA is set to `enforce`.

## Unverified (⚠), to be measured, not assumed

- The hosted project's Auth version (the "60 s per email" may be historical).
- The project JWT expiry.
- The live `mfa_policy` row.
- Whether the Free plan can change `rate_limit_verify`.
- Which API key type core uses today.
- Core's uvicorn worker count.
- Supabase Redirect URLs.
- Whether OTP-born core sessions exist (AMR distribution, before the sweep).
- Whether an FK to `auth.sessions` is acceptable (otherwise a TTL purge).

## Owner decisions needed (plain terms)

1. **Supabase key switch.** All logins into products currently share one per-IP limit at Supabase, about 30 entries per 5 minutes for everyone combined. The fix that gives each person their own allowance needs core to use Supabase's new "secret" key and a setting turned on. Alternative: just raise the shared limit. Which one?
2. **Product sessions and core admin.** Should a session opened inside a product be blocked from core's admin functions? Recommended: yes, except the five small things products already ask core for. Enforcing it needs a one-time sign-out of old product sessions; users would silently re-enter.
3. **Background tabs.** When Voltar closes a product in all its tabs, should the other tabs re-enter only when you look at them? Recommended: yes, so hidden tabs never use up logins.
4. **Product home page for visitors.** A stranger sees the product's public page. A browser that was recently inside the product is silently taken back in. OK?
5. **Session limit.** Core login keeps at most 5 sessions per person and deletes the oldest. With one session per product entry, should product sessions stop counting toward that limit, or should the limit be raised?
6. **Two-factor for product admin areas (later).** Sessions opened in products count as "single-factor" even when the core login used two factors. Before two-factor is made mandatory inside products, core needs to pass its two-factor status along. OK to plan it that way?
7. **Remove the unused launch address.** `GET /api/sso/launch` has no browser caller and is an extra way to create logins. OK to delete?
