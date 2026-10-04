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
- **A dead session signs out with scope `"local"`** (`createDeadSessionHandler`). The supabase-js default `"global"` revokes EVERY refresh token the user holds — one product tab judging its session dead logged the user out of core and every other product.

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
