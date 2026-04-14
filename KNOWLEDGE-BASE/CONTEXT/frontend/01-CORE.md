# 04 — Core Frontend Context

> Path: `core/frontend/src/` · Port: 5173 · API: `VITE_CORE_API_URL`

## Overview

Platform management frontend. React Router v6, React Context for auth (no Zustand, no TanStack Query — simpler than product frontends). Simple fetch-based API client.

## Auth (`lib/auth-context.tsx`)

Token stored in `localStorage['noctus_token']`. OAuth flow: parses URL hash `#access_token=...` → `POST /api/auth/oauth/callback` → stores token. Provides `useAuth()` with `{ user, organization, isAdmin, loading }`.

## Pages (20)

**Public**: Login, AcceptInvite, CheckoutSuccess, CheckoutCancel
**User**: Dashboard (products overview), Pricing, BillingSettings, Onboarding (4-step), TeamManagement, AccountSettings, OrgSettings
**Admin** (via `AdminRoute`): AdminDashboard, AdminOrgs, AdminSubs, AdminApiKeys, AdminPlans, AdminBilling, AdminWebhooks, AdminAnalytics, AdminSettings

## Route Guards

- `ProtectedRoute` — checks `localStorage['noctus_token']`
- `AdminRoute` — checks `isAdmin` from auth context
