# 07 — Authentication & Session Security

## Token Architecture

| Token | Lifetime | Renewal |
|-------|----------|---------|
| Supabase JWT (access) | 30 min | Proactive (activity refresh) + reactive (401 retry) |
| Supabase refresh token | Permanent (until revoked) | Rotated on each use |
| SSO token | 5 min | One-time use, exchanged for Supabase session |

## Activity-Based Token Refresh

Shared hook: `useActivityRefresh` (5 min refresh cycle).

**Two-tier model**:
- **Direct interaction** (mouse, key, scroll, click, touch) → resets activity timer
- **Passive presence** (tab visible, window focused) → only counts for **3 min** after last direct interaction (unattended screen protection)

**Result**: user who walks away stops getting refreshes after ~3 min. JWT expires after 30 min. If they return and interact → new JWT issued via refresh token.

**Cross-tab dedup**: localStorage flag prevents multiple tabs from refreshing simultaneously. Failed refresh → 30s backoff.

## Reactive 401 Retry

If proactive refresh fails: API call returns 401 → `createApiClient`'s `onTokenExpired()` forces a refresh (single-flight across concurrent 401s) → retries once → if the session is authoritatively dead → `onUnauthenticated` → login.

**A deploy must never log anyone out (2026-10-03 — the owner was logged out by 3 prod deploys in a day).** Every deploy swaps the container AND restarts the cloudflared tunnel, so for seconds requests answer Cloudflare 502/530 or fail at the network layer. The contract that keeps sessions alive:

- **Backend: 401 iff the auth provider REJECTED the token.** `noctusai_lib.api.auth.validate_bearer_token` is the one place a Supabase access token becomes a user (lib `_get_current_user`, framework `ProductDependencies.get_current_user`, p-studio). GoTrue answering a 4xx (≠408/429 — `bad_jwt` comes back 401/403) or no user ⇒ 401; a transport failure, an Auth 5xx/429, or anything unclassifiable ⇒ **503 + `Retry-After`**. gotrue wraps every transport failure + 502/503/504 into `AuthRetryableError`, which is neither `OSError` nor `TimeoutError` — the 2026-08-18 `(TimeoutError, OSError) → 503` branch was dead in prod because its tests raised an `OSError` the real client never raises. Core's `/api/auth/refresh` uses the same classifier (`is_authoritative_token_rejection`).
- **Frontend: `onTokenExpired` has three outcomes** — token (retry), `null` (refresh REFUSED ⇒ dead ⇒ `onUnauthenticated`), **throw** (refresh UNANSWERED ⇒ keep the session; the 401 propagates, no logout). `refreshWithBackoff` (`@noctusai/lib/api`) retries transient attempts (`isTransientHttpStatus`: network/0, 408, 425, 429, 5xx incl. CF 52x) at 0.5s/1.5s/4s — inside Supabase's 10s refresh-token reuse window — then throws `TransientAuthError`. Seed products get it via `createSupabaseTokenRefresher` (`@noctusai/lib/auth`, wired by `createProductInfra`); core wires `refreshWithBackoff` around its `/api/auth/refresh` call.
- **A dead session is CONFIRMED with GoTrue before anything is destroyed (2026-10-13).** `createDeadSessionHandler` (`@noctusai/lib/auth`) treats a refresh-unrecoverable 401 as a *claim*, then asks `supabase.auth.getUser()` (a server round-trip): `dead` (no local session, or 401/403 `session_not_found`/`bad_jwt`, other non-transient 4xx) ⇒ clear the store + `signOut({ scope: "local" })`; `alive` or `transient` (network/408/425/429/5xx/throw) ⇒ NO sign-out, NO `setUser(null)`, a `console.warn` with the path, the caller's 401 propagates. Only a 401 ever reaches it — 403s (`mfa_required`, `org_sem_licenca`) and 409s (`org_selection_*`) never do (pinned in `sessionRefresh.test.ts`). **Why:** `signOut({ scope: "local" })` is NOT a local-only purge — supabase-js still calls GoTrue `/logout?scope=local`, which DELETES the current session server-side, and every tab of a product shares that session, so one tab's false verdict logged the owner out everywhere (prod, social-wiring). `"local"` is still required over the default `"global"` (which also revokes core's and other products' sessions).
- **Every backend 401 logs why.** `noctusai_lib.api.auth._reasons.log_auth_401(reason, **non-secret fields)` emits `auth_401 reason=<code> cid=<correlation id> ...` (missing_authorization_header, authorization_not_bearer, provider_rejected [+status/code], provider_returned_no_user, session_cookie_unrecognised, api_token_invalid_or_revoked, bearer_not_recognised, sso_*, ...). Never log tokens (token *shape* only).

## Logout Behavior

Configurable per product via `products.logout_behavior` column:
- ERP/PF: `redirect` (back to Core dashboard, SSO stays active)
- Therapy/Core: `signout` (full sign out)

## Security Policies

- **Password change**: all other sessions revoked via `signOut(user_id, 'others')`
- **Rate limiting**: login 10/min, signup 5/min, change-password 5/min
- **Concurrent sessions**: max 5 per user (oldest revoked on 6th)
- **Audit logging**: login, token_refresh, password_change, session_expired, session_revoked
- **Last activity**: `noctus_users.last_active_at` updated on each refresh
- **Leaked password protection**: HaveIBeenPwned via Supabase Auth
