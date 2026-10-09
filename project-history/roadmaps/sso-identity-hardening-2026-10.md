# sso-identity-hardening-2026-10 — core↔product identity converges on account switch and logout

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: live walkthrough 2026-10-09 — owner switched core accounts A→B; social-wiring kept acting as A (and audit rows named A).
> Decision: **ship the identity-convergence fix now (Phase 1, on dev, prod on the owner's go); defer the deploy-order-sensitive and larger hardening items behind named triggers.**

## Origin

During the SW deal-876 walkthrough the owner logged out of core as `jraphaelsst@noctusai.com` and in as `joao@one.com`. social.noctusai.com kept A's Supabase session in its own-origin localStorage — through a reload and through re-opening SW from the core card — so SW acted as A and audit rows recorded the wrong actor. Root causes (security advisor: HIGH): `SSOCallback` kept any valid local session and threw the core token away unredeemed; core logout revoked nothing (`/api/auth/logout` signed out a fresh anon client); the seed BE auth dependency let a stale `nai_session` cookie win over the bearer; framework products never sent `product_slug`, so core's audience check was skipped.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | **Fleet deploy of 7e308e43a** (the seed FE SSOCallback that accepts `#token` and sends `product_slug`) | Every AWAKE product's prod image is built from a commit ≥ 7e308e43a — `noctus.dev.deploy_verify` / image GIT_SHA per container in `deploy/fleet/active-scope.txt` | Before it, emitting a fragment or requiring the slug breaks SSO for any product still on the old SSOCallback |
| T2 | T1 fired AND P2.1 shipped | P2.1's verify recipe green in prod | Token binding builds on the fragment/launch path |
| T3 | ~~A second org-switch/role-change surface lands~~ — **retired 2026-10-09** with P2.3 (the picker never touches what the SSO cache holds) | — | — |
| T4 | Any other product/seed consumer needs the SSO session cache | grep for `SSOSessionCache` outside core | Then the scoping must live in the lib, not a core subclass (DRY) |
| T5 | Owner or walkthrough hits "logged into core as A, /login as B without logout" | Report, or audit row mismatch after a /login | Core /login currently doesn't end a live session first |

**Today's status (2026-10-09)**: **T1 FIRED** — 7e308e43a is in the fleet deploy of 23e84e520 (owner go; deploy_verify 8/8) ⇒ P2.1 is unblocked. T2, T4, T5 not fired; T3 retired.

## Phase 1 — identity convergence (SHIPPED to dev 2026-10-09)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P1.1 | Cookie vs bearer naming different users → 401 + clear cookie; one cookie-attribute helper | `seed/lib/backend/noctusai_lib/api/auth/session/{dep,cookie}.py`, `seed/framework/backend/noctusai_seed/auth_router.py` (313b4cae0, 29745f284) | **shipped — prod 23e84e520, smoke-verified 2026-10-09** | In prod SW: with a stale `nai_session` for A and a B bearer, any API call returns 401 and `Set-Cookie: nai_session=""; Max-Age=0` |
| P1.2 | SSOCallback always redeems; account-switch interstitial; no silent sign-out on redeem failure; `#token`+`?token`; `productSlug` sent; boot/focus `getUser()` check | `seed/lib/frontend/src/{components/SSOCallback.tsx,auth.ts,identity.ts,env.ts}`, `seed/framework/frontend/{src/app.tsx,vite.config.factory.ts}` (7e308e43a) | **shipped — prod 23e84e520, smoke-verified 2026-10-09** | Prod: SW open as A → core logout → core login as B → click SW card → interstitial names A and B → confirm → SW header shows B; audit row of the next action names B |
| P1.3 | Core logout revokes globally (owner choice: "Sair de todos os dispositivos"); change-password revoke uses the JWT; SSO cache keyed (email, org_id, product) | `products/core/backend/app/routers/{auth,sso}.py`, core FE auth-context + layouts (a8f4d8d7d, a8301b78f) | **shipped — prod 23e84e520, smoke-verified 2026-10-09** | Prod: log out of core with SW open in another tab → within one focus/60s SW returns to login; a second device's core session is gone |

**Behavior guarantee**: a product never keeps acting as a user core no longer has signed in once (a) a card click happens or (b) core logged out and the product boots/refocuses. A network/5xx failure of the auth server never logs anyone out.

**Why ship now**: wrong-actor audit rows are an integrity failure on live CRM data.

## Phase 2 — deploy-order-gated + hardening (DEFERRED)

| # | Title | Files | Trigger | Verify recipe (write it now, run it when it ships) |
|---|---|---|---|---|
| P2.1 | Core emits the SSO token as a URL **fragment** (`/sso#token=`) in `Dashboard.tsx` launch + `GET /api/sso/launch`; `/api/sso/session` **requires** `product_slug` (401 if absent) | `products/core/frontend/src/pages/Dashboard.tsx`, `products/core/backend/app/routers/sso.py`, `schemas/sso.py` | **T1** | Prod: card click URL contains `#token=` and no `?token=`; edge/serve_spa access log for `/sso` carries no token; `curl` POST `/api/sso/session` without `product_slug` → exactly 401; every awake product's card still lands logged in |
| P2.2 | Browser-bind the SSO token: launch sets HttpOnly/Secure/SameSite=Strict nonce cookie on core; token carries `bnd` = hash(nonce); redeem (`credentials:'include'`, CORS allow_credentials for product origins) requires the match | core `sso.py` + launch, seed `SSOCallback` redeem fetch | **T2** | Prod: a token minted in browser X fails to redeem in browser Y (401) — login-CSRF link no longer swaps the victim's session; normal card click still works |
| P2.3 | ~~Flush the SSO session cache wherever the effective org changes~~ | — | **CLOSED 2026-10-09 — not needed** (see decision log) | — |
| P2.4 | Promote the (email, org_id, product)-scoped cache into the lib `SSOSessionCache`; drop the core subclass | `seed/lib/backend/.../auth` SSOSessionCache, core `sso.py` | **T4** | Unit: lib cache keyed by scope; prod: core SSO still redeems, no 429 regression on two-product launch |
| P2.5 | Core `/login` ends an existing live session (revoke via the logout path) before signing in a different user | core FE login page + auth-context | **T5** | Prod: logged in as A, visit /login and sign in as B without logging out → A's product sessions are revoked (SW returns to login on focus) |

## Anti-goals (explicit non-goals)

- ❌ "Ask core for its current identity from the product." Core's session lives in core's own-origin localStorage; a product can't read it — convergence is via token redeem + server-side revoke.
- ❌ "BroadcastChannel for cross-product logout." Same-origin only; useless across product subdomains.
- ❌ "Sign out on any `getUser()` error." Only auth rejections; an auth-server outage must never log out the fleet.
- ❌ "Per-browser precise revoke" for core logout — the owner chose global (2026-10-09); revisit only if users complain about other devices.

## Open questions (to revisit at trigger time)

- **Q1**: Stateless access-token verification paths (PostgREST/RLS, product backends verifying JWT locally) honour a revoked session until JWT expiry (default 3600s). Add a `session_id` existence check on audit-writing paths, or shorten JWT expiry? Revisit with P2.2.
- **Q2**: Cookie-session-mode products (`useSessionAuthInit`) get no boot `getUser()` check — none exist today; revisit when the first one goes live.

## Decision log

- **2026-10-09**: P2.3 (flush the SSO cache on org switch) CLOSED as not needed, T3 retired — evidence from the org-picker session (noc-4): (1) the picker is metadata-free: it writes only `public.platform_org_selections`, and `effective_org.py` never consults `user_metadata` (org-picker CONTRACT L114), so core's SSO session cache holds nothing the picker changes; (2) a selection is bound to the token's `session_id`, so reusing a cached session within the TTL keeps it valid — a flush would END the selection; (3) a flush would need a cross-process hook for zero behaviour change.
- **2026-10-09**: Phase 1 live in prod (23e84e520) and smoke-verified in the owner's browser: card-click A→B switch showed the interstitial and switched SW to B; core logout → SW signed out on reload (0 auth tokens); a garbage token on a live session showed the error screen without signing out. Cosmetic follow-ups fixed on `feat/core-header-and-sso-copy` (pt-BR accents in SSOCallback; the "Sair de todos os dispositivos" label missing on 4 core page headers — DRY'd into one CoreHeader). T1 fired ⇒ P2.1 is next.

- **2026-10-09**: Owner chose global logout scope ("All devices") over per-browser precise revoke and core-only.
- **2026-10-09**: Fragment token + required `product_slug` deferred to T1 — deploy-order safety (old SSOCallback reads only `?token` and omits the slug).
- **2026-10-09**: Account-switch replaces the session only after an explicit interstitial (security advisor: F1 widens login-CSRF to victims with a session; interstitial now, token binding P2.2 later).
- **2026-10-09**: Phase 1 kept out of noc-4's concurrent prod bless (bless target moved to a pre-SSO commit; prod stayed at 06f5ccc5c) — SSO ships on the owner's own go, with the full predeploy (fleet-wide seed).

## Retrospective (filled at first trigger fire)

*To be filled when Phase 2 fires.*

## Composes with

- `KB § PATTERNS/frontend/core-url-routing.md` — product launch URLs from core.
- `KB § PATTERNS/frontend/org-admin-ux-gate.md` — UX role gates read the same SSO user_metadata.
- `KB § PATTERNS/common/methodology-execution-discipline.md` — verdict-channel integrity (Phase 1 was verified on the merged tip from a clean shell).

## File trail

- Phase 1 commits: 313b4cae0, 29745f284, 7e308e43a, a8f4d8d7d, a8301b78f (dev).
- This doc.
