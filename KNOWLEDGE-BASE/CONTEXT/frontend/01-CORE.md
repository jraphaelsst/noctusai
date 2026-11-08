# 01 — Core Frontend Context

> Path: `products/core/frontend/src/` · Port: 5173 (`vite.config.ts` → `createViteConfig({ port: 5173 })`) · 36 authenticated routes + 1 public · API: same-origin (`VITE_CORE_API_URL` only as a split-origin override)
> Standard frontend patterns (toast, hooks, auth init, dates): see `../PATTERNS/frontend/frontend.md`; craft baseline: `../PATTERNS/frontend/frontend-craft-canon.md`.

> **Refreshed 2026-11-05 (always-doc-the-trim).** The previous text said core used "React Router v6, React Context for auth (no Zustand, no TanStack Query — simpler than product frontends). Simple fetch-based API client", listed 20 pages, and described `ProtectedRoute`/`AdminRoute` guards. That predated core's migration onto the seed framework (`core-seed-wiring` Phase 4). Source of truth now: `products/core/frontend/src/main.tsx` (routes), `src/lib/auth-context.tsx` + `src/lib/seed-auth-adapter.tsx` (auth), `src/lib/api.ts` (client), `package.json` (versions) — re-verify there before trusting a count below.

## Overview

Platform management frontend (identity provider, billing, org/team admin, platform admin, the noctusai.com website). Built through the seed like every product: `createProductApp({ authProvider: coreAuthProvider, Layout: CoreLayout, Login, Landing, routes, … })` (`src/main.tsx:58-106`) — the framework owns the router, providers, `ErrorBoundary` and `Suspense`; core owns auth + layout branching (`src/main.tsx:1-9`).

Stack (`package.json`): React `^18.3.1` (under `React.StrictMode`, `src/main.tsx:108-111`) · react-router-dom `^7` · `@tanstack/react-query` `^5.83` with the seed's org-scoped client · Zustand `^5` · Vite `^8` · vitest + Testing Library · `@playwright/test`.

## Auth (`lib/auth-context.tsx`, `lib/seed-auth-adapter.tsx`)

Core IS the identity provider other products delegate to, so it supplies its own `CustomAuthProvider` (`seed-auth-adapter.tsx:18`) instead of the seed's Supabase provider. Custom JWT + refresh token in `localStorage` (`noctus_token`, `noctus_refresh_token` — `lib/api.ts:23-25,169-184`). OAuth flow: parses URL hash `#access_token=...` → `POST /api/auth/oauth/callback` → stores token (`auth-context.tsx:133-157`). `useAuth()` (`auth-context.tsx:218`) exposes `{ user, organization, isAdmin, isMarketing, loading, … }`.

## API client (`lib/api.ts`)

`createApiClient` from `@noctusai/lib/api` with refresh-with-backoff; base URL = `window.location.origin` (single-container house model), `VITE_CORE_API_URL` as override (`lib/api.ts:12-20`) — the one sanctioned hand-roll of the core URL (`KB § PATTERNS/frontend/core-url-routing.md`).

## Server state

TanStack Query via entity hooks (`src/hooks/`: `useTeam` → `teamKeys` `:96`, `useBrandIdentity` → `brandKeys` `:29`, `useTemplates` → `templateKeys` `:18`, `useProductStateActions`; `src/lib/credits.ts` → `creditKeys` `:179`); ~10 files call `useQuery`/`useMutation`. Writes follow `mutation-cache-writes.md` (`useTeam.cacheWrites.test.ts`, `useBrandIdentity.cacheWrites.test.tsx`).

## Routes (`src/main.tsx:68-105`)

**Public**: `/invite/:token` (AcceptInvite) + seed-provided Login / Landing / consent routes.
**User**: Dashboard `/`, Pricing, Billing, Checkout success/cancel, Team, Account settings, Security, Org settings (+ `/identidade`, `/creditos`), API keys, Onboarding.
**Admin** (`/admin/*`): dashboard, users, orgs, subs, api-keys, plans, products, billing, webhooks, analytics, settings, templates, audit-digest, website docs/settings/leads, fleet, operação, financeiro, créditos.

## Route gating

No `ProtectedRoute`/`AdminRoute` components and no admin gate in `CoreLayout`: **admin is not rendered, not hidden.** `createProductApp({ NotFound: CatchAll })` — `pages/CatchAll` lazy-loads ONE of two privileged bundles chosen by the server-confirmed role from `/api/auth/me` (`user.role === 'admin'` = the platform role `get_current_admin` / `platform_admin_required` read, never an org/product admin): `admin/PlatformAdminApp` (full route table `admin/routes.ts`, nav `admin/navConfig.ts`, admin API clients `lib/*.admin.ts` via `admin/AdminApis`) or, for `marketing`, `admin/WebsiteAdminApp` (`admin/websiteConfig.ts` only — it never receives a platform-admin string). Anyone else gets the plain `pages/NotFound`, byte-identical to an unknown path (no redirect, no "forbidden", no bundle request). The nav is the seed `Sidebar` organ over the module groups in canonical order (`orderNavGroups`: CRM, Redes Sociais, ERP, CMS, CoreStudio, Banib, Emissões, Integrações, Configurações; then Operação, Modelos da plataforma; standalone Painel); the not-yet-built modules are disabled "Em breve" stubs shown to platform admins only. ONE predicate, `admin/access.ts` `canReach(role, href)`, registers the routes AND prunes the nav. `vite.config.ts` emits every privileged chunk (admin, admin libs, the internal `website/docs`) under `_p/<hash>.js` with an opaque name, and `src/build-output.test.ts` builds and asserts the PUBLIC output has zero admin paths/components/labels/`/api/admin/` literals (positive control: `_p/` has them). **Interim, honestly:** `_p/*` is still statically served, so this hides names, it is not access control; serving the bundle from an authenticated route (URL only in the admin `/me` payload) is the open follow-up. The org-tier spend read moved to `GET /api/orgs/{org_id}/llm-spend` so `/api/admin/*` is platform-only (and out of OpenAPI); the legacy admin-path alias carries `NOC-REMEDIATE[llm-spend-legacy-admin-path]`.

## Website

`src/website/` is the noctusai.com marketing site (prerendered; settings injected server-side as JSON) — read its docs first → `KB § CONTEXT/PRODUCTS/core/WEBSITE.md`.

## Known follow-ups (2026-11-05)

- Route components use plain `React.lazy` (`src/main.tsx:19-56`), not `lazyWithReload` — a mid-session deploy breaks unloaded routes (`frontend-craft-canon.md` §9).
- ~~`FaqAccordion` re-serialises admin-editable FAQ JSON-LD without escaping `<`~~ fixed 2026-11-05 (`safeJsonLd`); the JSON-LD now lives in `src/website/components/SiteFaq.tsx:26` over the seed `Faq` organ (`frontend-craft-canon.md` §11).
- Hand-rolled modal in `src/pages/admin/AdminPlans.tsx:176` (`frontend-craft-canon.md` WE1).
