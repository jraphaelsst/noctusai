# 07 — Authentication & Session Security

> Token lifecycle, activity tracking, session management, and security policies.

---

## Token Architecture

| Token | Lifetime | Storage | Renewal |
|-------|----------|---------|---------|
| **Supabase JWT (access token)** | 30 min (configurable in Supabase Dashboard) | Products: Supabase SDK memory. Core: `localStorage noctus_token` | Proactive via activity refresh + reactive via 401 retry |
| **Supabase refresh token** | Permanent (until session revoked) | Products: Supabase SDK. Core: `localStorage noctus_refresh_token` | Rotated on each use by Supabase |
| **SSO token** | 5 min (`sso_token_expiration_minutes`) | Never stored — one-time use in URL | Not renewed — exchanged once for Supabase session |

---

## Activity-Based Token Refresh

Shared hook: `useActivityRefresh` (`shared/frontend/src/design-system/useActivityRefresh.ts`)

### Two-Tier Activity Model

**Tier 1 — Direct Interaction** (proves a human is present):
- `mousemove` (throttled 1x/sec), `keydown`, `scroll`, `click`, `touchstart`
- Resets the full activity timer

**Tier 2 — Passive Presence** (tab visible, no proof of human):
- `visibilitychange` (tab visible), `focus` (window focused)
- Only counts as active for **3 minutes** after the last direct interaction
- After 3 min without direct interaction, passive presence is ignored
- **This is the "unattended screen" protection**

### Refresh Behavior

| Condition | Action |
|-----------|--------|
| User active (direct interaction within 5 min) | Token refreshed |
| User reading (no interaction, tab visible, within 3 min of last interaction) | Token refreshed |
| User reading (no interaction, tab visible, >3 min since last interaction) | **NOT refreshed** |
| User away (no interaction for 5+ min) | **NOT refreshed** → token expires |
| Browser offline | Skip refresh |
| Another tab just refreshed | Skip (dedup via localStorage) |
| Previous refresh failed | Wait 30s backoff before retrying |

### Configuration

```ts
useActivityRefresh({
  onRefresh: async () => { await supabase.auth.refreshSession(); },
  intervalMs: 5 * 60 * 1000,      // 5 min refresh cycle
  readingTimeoutMs: 3 * 60 * 1000, // 3 min passive presence window
  enabled: !!user,                  // only when authenticated
});
```

### Per-Product Wiring

| Product | Location | Refresh Method |
|---------|----------|---------------|
| Core | `lib/auth-context.tsx` | `POST /api/auth/refresh` with stored refresh_token |
| ERP | `components/layout/Layout.tsx` | `supabase.auth.refreshSession()` |
| PF | `components/layout/Layout.tsx` | `supabase.auth.refreshSession()` |
| Therapy | `components/auth/AuthProvider.tsx` | `supabase.auth.refreshSession()` |

---

## Reactive 401 Retry (Fallback)

If the proactive refresh fails or the token expires between refresh cycles:

1. API call returns 401
2. Shared `createApiClient` calls `onTokenExpired()` callback
3. Callback forces `supabase.auth.refreshSession()` (or `POST /api/auth/refresh` for Core)
4. Retries the original request once with the fresh token
5. If retry fails → user is redirected to login

---

## Logout Behavior

Controlled by `products.logout_behavior` column in the database:

| Product | Behavior | What happens |
|---------|----------|-------------|
| ERP | `redirect` | Redirects to NoctusAI dashboard, SSO stays active |
| PF | `redirect` | Same — redirects to Core, no sign out |
| Therapy | `signout` | Actually signs out (direct Supabase Auth, no SSO) |
| Core | `signout` | Clears tokens, signs out from Supabase |

Configurable via admin panel: `/admin/logout-behavior`

---

## Security Policies

### Session Invalidation on Password Change
When a user changes their password, all other active sessions are revoked via `supabase.auth.admin.signOut(user_id, 'others')`. Only the current session survives.

### Rate Limiting on Auth Endpoints

| Endpoint | Limit |
|----------|-------|
| `POST /api/auth/login` | 10/minute |
| `POST /api/auth/refresh` | 10/minute |
| `POST /api/auth/change-password` | 5/minute |
| `POST /api/auth/signup` | 5/minute |

### Concurrent Session Cap
Max 5 active sessions per user. On the 6th login, the oldest session is revoked. Prevents credential sharing and limits blast radius.

### Audit Logging for Auth Events
All auth events logged to `audit_logs` table:
- `login` — successful login (IP, user-agent)
- `token_refresh` — proactive token refresh
- `password_change` — password changed
- `session_expired` — token expired without renewal
- `session_revoked` — session forcefully terminated

### Last Activity Tracking
`noctus_users.last_active_at` updated on each token refresh. Visible in admin Users page as "last seen X ago".

### Leaked Password Protection
Supabase Auth checks passwords against HaveIBeenPwned.org on creation/change. Configured in Supabase Dashboard.

---

## Security Timeline (User Walks Away)

```
0:00  User clicks (direct interaction)     → timer reset
3:00  No interaction, tab still visible    → passive presence EXPIRES
5:00  Refresh cycle fires                  → inactive for 5 min → SKIP refresh
30:00 JWT expires (30 min lifetime)        → session dead
30:01 Any API call returns 401             → reactive retry → refresh token used
      If user returns and moves mouse      → new JWT issued, session continues
      If user doesn't return               → session stays expired
```

Worst-case exposure for unattended screen: **30 minutes** (JWT lifetime).
With 1-hour JWT: 63 minutes. With 15-min JWT: 18 minutes.
