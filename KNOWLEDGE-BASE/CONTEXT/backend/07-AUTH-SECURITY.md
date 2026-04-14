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

If proactive refresh fails: API call returns 401 → `createApiClient`'s `onTokenExpired()` forces `refreshSession()` → retries once → if retry fails → redirect to login.

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
