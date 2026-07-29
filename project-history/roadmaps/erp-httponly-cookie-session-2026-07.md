# Roadmap — Migrate ERP off localStorage tokens → httpOnly cookie session

**Slug:** `erp-httponly-cookie-session` · **Opened:** 2026-07-07 · **Owner:** tech-lead (Raphael)

## Goal

Stop storing Supabase access + refresh tokens in the browser's `localStorage`
(`sb-<ref>-auth-token`, set by `persistSession:true` in
`seed/lib/frontend/src/supabase.ts:51`). Move the ERP to the seed's **httpOnly,
Secure, SameSite=strict cookie session** (`nai_session` + `/api/auth/{login,me,logout}`
+ server-side session store). The browser holds only an opaque session id.

## Why

1. **Security (user-raised).** `localStorage` is JS-readable → XSS / a malicious dep can
   exfiltrate the **refresh token** (long-lived → full impersonation). httpOnly cookies are
   unreadable by JS. Root fix, not a patch.
2. **Logout reliability.** The 2026-07-07 logout whack-a-mole is a *symptom* of client-side
   session storage. Server-side sessions = one reliable invalidation path.

## Evidence / scope (measured 2026-07-07)

- **ERP FE direct-`supabase` surface is SMALL: 14 call sites / 9 files.** ERP already runs on
  **61 backend routers** — nearly all data already flows through the backend API.
- **Seed cookie-session was HALF-shipped (×2):** (a) `/api/auth/{login,me,logout}` route handlers
  lived only in `social-wiring` (a fork), NOT the seed; (b) the `SessionStore` shipped
  **Protocol + Fake only** — no Real, no factory. Even social-wiring ran the in-memory
  `FakeSessionStore` (`dependencies.py:169`, `TODO: swap to RedisSessionStore`), so **cookie
  sessions died on every restart fleet-wide**.

## Slices (reshaped by the 2026-07-07 security review)

| # | Slice | Status |
|---|---|---|
| 1a | **Seed the durable session store** — `RedisSessionStore` (Real) + `make_session_store` factory + exports + 10 tests. | ✅ on `dev` (`f7cc6267`); **hardened by 1a′** |
| 1a′ | **Harden the store** — encrypt refresh token (+ cached access token) at rest; add `access_token`/`access_expires_at` fields; `read_tokens`/`write_tokens` server-side accessors; `require_encryption` factory guard; key-rotation read path. | ✅ (2026-07-08, `feat/seed-token-exchanger-store-hardening`) — `enc` flag + Fernet reuse (`security.encrypted_tokens`); `settings.session_encryption_key`; 18 tests. Redis DB/ACL isolation + LGPD-flag = deploy-time (Slice 4). |
| 1x | **Seed `SupabaseTokenExchanger`** (Protocol+Fake+Real+factory) — refresh→access on a THROWAWAY anon client (SEC-1); cache access token + near-expiry refresh under a per-session Redis lock (SEC-2); write back the rotated refresh token. Unit-test with a Fake exchanger. | ✅ (2026-07-08, same branch) — `token_exchange.py`; SEC-1 in `make_default_refresh_fn` (throwaway anon), SEC-2 cache + `nai_lock:<sid>` `SET NX EX` serialization + rotation write-back; 15 tests incl. concurrent-calls-→-one-refresh. **Real refresh path = prod-shape-verified in Slice 4** (Fake exchanger used in unit tests). |
| 1b | **Promote `/api/auth/{login,me,logout}` router into the seed**; logout also **revokes upstream** via GoTrue sign-out (SEC-4); wire `_get_session_store` via the factory; repoint social-wiring to CONSUME it (no fork). | ✅ **SHIPPED 2026-07-16** (`04c897b1` + `5a4faa29` + `c27c48ac`). Seed framework 132/132; social-wiring backend **1044/1044** (the "821" baseline below is stale — the suite grew with youtube/mailchimp/media_creation); `test_auth_router.py`'s 9 tests pass unchanged, no coverage deleted; the 398-line fork is gone. **Two real bugs caught in-flight, both would have shipped silently:** (1) `create_auth_router` hardcoded `FakeApiTokenResolver()` (always-empty) with `legacy_jwt_resolver=None` — naively adding `"auth"` to `standard_routers=[...]` **exactly as this row's note below instructed** would have 401'd every api-token + legacy-JWT path in social-wiring. Fixed with `api_token_resolver`/`legacy_jwt_resolver` override kwargs, consumed via a direct factory call from the module-registration seam (the registry's fixed 4-arg `_build_auth_router` signature has no per-product override seam). (2) `redis_url` defaults to a reachable Redis with no `session_encryption_key` field, so SEC-3's `require_encryption=True` guard refused to boot — added the field + a test-only generated key so the suite exercises the REAL Redis-backed encrypted store instead of masking it behind a Fake. *Historical note (2026-07-08):* **DONE:** the SEC-4 mechanism — `session_revoke.py` `SessionRevoker` (Protocol+Fake+Real+factory); `make_default_revoke_fn` = throwaway-anon-client `refresh_session`→`sign_out(scope=local)` (SEC-1 reuse); best-effort-but-logged (never raises into logout, returns bool); 9 tests. **BANKED for a fresh session** (needs FE contract + prod-shape): (i) create `noctusai_seed/auth_router.py` = `create_auth_router(deps, settings)` factory promoting login/me/logout + api-tokens from `products/social-wiring/backend/app/routers/auth.py` (398 ln), DECOUPLED from `app.*` imports; login's SEC-1 anon-client sign-in already correct there; logout calls the new `SessionRevoker` (the SEC-4 gap: current logout only `store.delete`+`delete_cookie`, line 234-237); (ii) register `"auth"` in `noctusai_seed/routers.py` `_STANDARD_ROUTERS` + the 3-leg maintenance contract (registry / `test_build_standard_routers` drift-guard / `03-SEED-ARCHITECTURE.md § Standard routers`); (iii) wire the session store + `TokenExchanger` + `SessionRevoker` into the seed `deps` object via `make_session_store(require_encryption)` / `make_token_exchanger` / `make_session_revoker` (social-wiring `dependencies.py:157` `_get_session_store` still returns `FakeSessionStore()` w/ TODO); (iv) repoint social-wiring `main.py` (77-114) to `standard_routers=["auth", ...]`, delete its `app/routers/auth.py` fork. |
| 1b′ | **Seed `createProductLayout` cookie-mode seam** — NEW, discovered 2026-07-16, **blocks Slice 3**. `createProductLayout` (`seed/framework/frontend/src/layout.tsx`) hard-binds Supabase-JS for logout (`auth.signOut`), password change (`auth.updateUser`), session-extend (`auth.refreshSession`) and page-status nav gating (a `.from()` RLS read). `ProductLayoutConfig.supabase` is non-optional; `LayoutEnrichment` exposes only `onUpdateProfile`. **The third half-shipped dimension of this seed** (the other two are BE-side and already logged above). | 🟡 IN PROGRESS (`feat/seed-layout-session-seam`) |
| 2 | **ERP backend** — mount the seed router; RLS client per request via the exchanger; ensure the **minted access token** (not the session id) reaches `set_session` (SEC-6); pass `check_auth_session_mutation_on_shared_client`. | ⏳ **NEVER DISPATCHED** — the 2026-07-15 wave dispatched 1b + 3 but skipped 2, so Slice 3 was briefed to build a frontend against endpoints nothing mounts on ERP. Also collides with the org-source-of-truth fan-out in `products/erp-imobiliario/backend/` — must not run beside it. **A PARTIAL ATTEMPT EXISTS, PRESERVED NOT LANDED** (2026-07-29, `3e66541d` on `feat/erp-be-mount-auth-router`, ~420 lines: `dependencies.py`, `main.py`, `migrations/040_api_tokens.sql`, `requirements.txt` +cryptography, `tests/test_auth_session_unified.py`). It had been sitting UNCOMMITTED in a prunable worktree; it is now committed on its own branch purely so it cannot be lost. **Do not cherry-pick it**: 1b′ is still in progress, its migration number 040 now collides (erp is at 042 ⇒ needs 043), and SEC-6 is unverified against it. Resuming = re-dispatching Slice 2 against current `dev`. |
| 3 | **ERP frontend** — swap to `useSessionAuthInit` / `loginWithSession` / `logoutSession`; migrate the direct-`supabase` call sites → backend API. | 🔴 **BLOCKED on 1b′** — partial delivery `83f0022e` (role-grant off a client-side RLS bypass onto the existing `POST /api/profiles/{user_id}/roles`; dead import dropped; tsc 89 pre-existing errors before AND after, zero new). **Scope re-measured: ~19 call sites / 13 files, NOT 14/9.** |
| 4 | Deploy (Redis-backed sessions in prod, persistence ON) + verify in **prod shape** (Fake store hides the exchange — dev-green is a false-green). | ⏳ |

### 🔴 The Slice-3 blocker, stated plainly (2026-07-16)

Swapping a product's `AuthProvider` to cookie-session mode **while `Layout` stays Supabase-JS-bound** makes
the header "Sair" button a **silent no-op**: `signOut()` fires against a session that was never established,
the `nai_session` cookie is never cleared, and the user is still redirected to `/login`. They *look* logged
out while their session stays live.

**That is a worse security posture than the localStorage tokens this roadmap exists to remove** — the
migration would regress its own goal #2 (logout reliability). Engineer C stopped rather than ship it, and
declined to fork `createProductLayout` inside ERP (cross-cutting; would fork a seam every product mounts).
Both calls were correct. Slice 3 cannot re-dispatch until 1b′ lands.

**Related finding — the "first consumer" precedent is weaker than the seed doc claims.** `03-SEED-ARCHITECTURE.md`
cites social-wiring as the first consumer of `createSessionAuthProvider`, but social-wiring's `App.tsx` still
passes legacy `{supabase, useAuthStore}` to BOTH `createProductLayout` and `createProductApp` — only
`Login.tsx` calls `loginWithSession()`. That is a **login-only bolt-on**: its own logout, boot-restore and
Layout remain Supabase-JS-bound. So no product has ever run this pattern end-to-end. Treat "social-wiring
does it" as unproven when reasoning about Slice 2/3.

## Decisions

- **2026-07-07** — Direction: full ERP migration to seed cookie session. Durability: **Redis** (fleet runs it). ✅ 1a built.
- **2026-07-07 — RESOLVED (was OPEN):** ERP backend keeps **RLS via token exchange** (option a), NOT service-role + app-filtering. Confirmed by the user + the security review (dropping RLS = any app bug becomes a cross-org leak with no backstop).

## Security requirements — from the 2026-07-07 `security` advisor threat model (BUILD GATES)

Sound direction, but **items 1–3 are blocking**; build the seed exchanger + harden the store BEFORE Slice 2 touches the 61 ERP routers. **SEC-1/2/3 now landed at the seed layer (2026-07-08); SEC-4/5/6 are Slice 1b/2 consumer wiring; SEC-7 is Slice 4 deploy.**

- ✅ 🔴 **SEC-1** — refresh→access exchange MUST run on a **throwaway `create_client(url, anon_key)`**, never the shared admin singleton (`set_session` on it downgrades every later admin call to `authenticated` process-wide — the 2026-05-23 core prod outage). Keeper exists: `check_auth_session_mutation_on_shared_client`. **DONE:** `token_exchange.make_default_refresh_fn` constructs a throwaway anon client per refresh; the exchange never touches `get_admin_client()`. Real-path prod-shape verify deferred to Slice 4.
- ✅ 🔴 **SEC-2** — **NO per-request `refresh_session`.** Supabase rotates + runs reuse-detection → replay outside ~10s revokes the whole token family. Cache access token + expiry in the session record; refresh only near-expiry under a per-session Redis lock (`SET nai_lock:<sid> NX EX 5`); **write the rotated refresh token back**. **DONE:** `SupabaseTokenExchanger` — cache fast-path (`_is_fresh`, 60s skew), `nai_lock:<sid>` `SET NX EX` with compare-and-delete release + wait-for-publish on contention, rotated refresh written back via `store.write_tokens`. Test `test_concurrent_calls_trigger_single_refresh` proves 6 concurrent calls → 1 upstream refresh.
- ✅ 🔴 **SEC-3** — refresh token is currently **plaintext** in shared fleet Redis (LLM cache + rate-limiter share it) → a Redis read harvests every user's impersonation credential. **Encrypt at rest** (Fernet/AES-GCM, app-held key; reuse the `bytea`-credential muscle). Dedicated Redis DB/ACL; LGPD-flag the store. **DONE (crypto leg):** `RedisSessionStore(encryption_key=...)` Fernet-encrypts `refresh_token` + cached `access_token` (reuses `security.encrypted_tokens`), `enc` per-row flag + `extra_decrypt_keys` rotation read path, `make_session_store(require_encryption=True)` refuses a plaintext Redis store; key = `settings.session_encryption_key`. **Deferred to Slice 4 (deploy):** dedicated Redis DB/ACL isolation + LGPD-flag registration (ops config, not code).
- 🟠 **SEC-4** — logout (+ password-change) must **revoke upstream** (GoTrue sign-out), not just delete the Redis row; best-effort-but-logged (no silent swallow).
- 🟠 **SEC-5** — `SameSite=strict` is NOT enough across `*.noctusai.com` subdomains. Prefer **same-origin host-only cookie** (the ERP already serves FE+API from one container → viable); else add an anti-CSRF token on mutating verbs. Pair `allow_credentials=True` with an exact origin allowlist.
- 🟠 **SEC-6** — ensure the **minted access token** (not the opaque session id) reaches `set_session`; add a keeper/assert that a cookie-derived `AuthContext` never hits `set_session` as-is. Verify in prod shape.
- 🟡 **SEC-7** — cap absolute session lifetime (sliding TTL has no max today); confirm Redis persistence (AOF/RDB) ON, else a Redis restart logs everyone out. Sessions **cannot** degrade-to-miss like the LLM cache.
- 🟡 **SEC-8** — session-id entropy (256-bit) + cookie-over-bearer priority + `caller_kind` split are all correct; keep those invariants.

## Retrospective (fill on close)

- _pending_
