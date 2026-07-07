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

## Slices

| # | Slice | Status |
|---|---|---|
| 1a | **Seed the durable session store** — `RedisSessionStore` (Real) + `make_session_store` factory + exports + 10 tests (fakeredis). Closes the seed-fake-real-adapter contract. | ✅ built + tested on `feat/seed-cookie-session-router` (28 auth tests green) |
| 1b | **Promote the `/api/auth/{login,me,logout}` router into the seed** (parameterized) + wire `_get_session_store` via the factory; repoint social-wiring to CONSUME the seed router (no fork) — and it gets durable Redis sessions as a bonus. | ⏳ next |
| 2 | **ERP backend** — mount the seed auth router; resolve the caller via the session. **DECISION NEEDED** (below). | ⏳ blocked on decision |
| 3 | **ERP frontend** — swap to `useSessionAuthInit` / `loginWithSession` / `logoutSession`; migrate the 14 direct-`supabase` call sites → backend API. | ⏳ |
| 4 | Deploy (Redis-backed sessions in prod) + verify in prod shape. | ⏳ |

## Decisions

- **2026-07-07** — Direction: full ERP migration to seed cookie session. Session store durability: **Redis** (fleet already runs it; survives deploys). ✅ built in 1a.
- **OPEN (gates Slice 2) — how the ERP backend makes org-scoped DB calls once the FE no longer sends the user JWT.** `AuthContext` carries identity (`org_id`, `user_id`) but NOT a Supabase access token. Two options:
  - **(a) Preserve RLS (RECOMMENDED):** backend exchanges the server-held refresh token → a short-lived user access token → RLS-scoped Supabase client. Keeps the RLS safety net (an app bug can't leak cross-org). More work.
  - **(b) Service-role + `AuthContext.org_id` filtering:** app-enforced org isolation. Simpler, but **drops RLS** as the backstop — an app bug becomes a cross-org data leak. Runs counter to the platform's RLS discipline.
  Recommend (a); likely wants a `security` advisor review before build.

## Retrospective (fill on close)

- _pending_
