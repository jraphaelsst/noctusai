# 04 — Core Frontend Context

> Path: `core/frontend/src/`
> Dev server: Vite on port **5173**
> API target: `VITE_CORE_API_URL` (default: `http://localhost:8000`)

---

## Overview

Platform management frontend with user-facing pages (dashboard, billing, team, settings) and an admin panel for platform-wide management. Uses React Router v6, React Context for auth (no Zustand), and a simple fetch-based API client.

---

## State Management

| Layer | Technology |
|-------|-----------|
| Auth state | React Context (`AuthProvider` + `useAuth()`) |
| Component state | React `useState` |
| Server state | Direct `api.get()`/`api.post()` into local state |

No Zustand, no TanStack Query — simpler than ERP frontend.

---

## Auth (`lib/auth-context.tsx`)

**AuthState**:
```typescript
{
  user: { id, nome, email, role, org_id }
  organization: { id, nome, slug, plano, category? }
  isAdmin: boolean  // user.role === "admin"
  loading: boolean
}
```

**Key functions**: `useAuth()`, `logout()`, `refresh()`, `handleOAuthCallback()`

**Token**: Stored in `localStorage['noctus_token']`, sent as `Authorization: Bearer` header.

**OAuth flow**: Parses URL hash `#access_token=...` → calls `POST /api/auth/oauth/callback` → stores token.

---

## API Client (`lib/api.ts`)

- Methods: `get()`, `post()`, `patch()`, `delete()`
- Token management: `setToken()`, `clearToken()`, `getToken()`
- Base URL: `VITE_CORE_API_URL` (default `http://localhost:8000`)

---

## Pages (20)

### Public
| Page | Route | Purpose |
|------|-------|---------|
| `Login` | `/login` | Email/password + OAuth (Google, Azure) |
| `AcceptInvite` | `/invite/:token` | Accept team invitation |
| `CheckoutSuccess` | `/checkout/success` | Post-payment confirmation |
| `CheckoutCancel` | `/checkout/cancel` | Payment cancellation |

### Protected User Pages
| Page | Route | Purpose |
|------|-------|---------|
| `Dashboard` | `/` | Products overview, subscriptions |
| `Pricing` | `/pricing` | Plan selection |
| `BillingSettings` | `/billing` | Subscription and payment management |
| `Onboarding` | `/onboarding` | 4-step setup wizard |
| `TeamManagement` | `/team` | Members, roles, invitations |
| `AccountSettings` | `/settings` | User profile and preferences |
| `OrgSettings` | `/org-settings` | Organization configuration |

### Admin Pages (protected by `AdminRoute`)
| Page | Route | Purpose |
|------|-------|---------|
| `AdminDashboard` | `/admin` | Platform overview KPIs |
| `AdminOrganizations` | `/admin/orgs` | Manage organizations |
| `AdminSubscriptions` | `/admin/subs` | Manage subscriptions |
| `AdminApiKeys` | `/admin/api-keys` | API key management |
| `AdminPlans` | `/admin/plans` | Plan tier definitions |
| `AdminBilling` | `/admin/billing` | Billing analytics |
| `AdminWebhooks` | `/admin/webhooks` | Webhook endpoints |
| `AdminAnalytics` | `/admin/analytics` | MRR, churn, platform metrics |
| `AdminSettings` | `/admin/settings` | Platform-level settings |

---

## Components

| Component | Purpose |
|-----------|---------|
| `AdminLayout.tsx` | Admin sidebar layout (9 nav items, mobile-responsive) |
| `NotificationBell.tsx` | Dropdown notification center (polls every 30s) |

---

## Route Guards

| Guard | Logic |
|-------|-------|
| `ProtectedRoute` | Checks `localStorage['noctus_token']` exists, redirects to `/login` |
| `AdminRoute` | Checks `isAdmin` from auth context, redirects to `/` |

---

## Directory Structure

```
core/frontend/src/
├── main.tsx              # Router config, route guards
├── index.css             # Global styles
├── components/
│   ├── AdminLayout.tsx
│   └── NotificationBell.tsx
├── lib/
│   ├── api.ts            # Fetch-based API client
│   └── auth-context.tsx  # React Context for auth
└── pages/
    ├── Login.tsx
    ├── Dashboard.tsx
    ├── Pricing.tsx
    ├── BillingSettings.tsx
    ├── Onboarding.tsx
    ├── TeamManagement.tsx
    ├── AccountSettings.tsx
    ├── OrgSettings.tsx
    ├── AcceptInvite.tsx
    ├── CheckoutSuccess.tsx
    ├── CheckoutCancel.tsx
    └── admin/
        ├── AdminDashboard.tsx
        ├── AdminOrganizations.tsx
        ├── AdminSubscriptions.tsx
        ├── AdminApiKeys.tsx
        ├── AdminPlans.tsx
        ├── AdminBilling.tsx
        ├── AdminWebhooks.tsx
        ├── AdminAnalytics.tsx
        └── AdminSettings.tsx
```
