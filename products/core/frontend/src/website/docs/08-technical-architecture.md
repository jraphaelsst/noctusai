# 08 · Technical architecture — the website inside core

Source: Phase-0 architecture audit (architect advisor, 2026-09-23). File and line references are from the audit and must be re-verified before each slice starts (the codebase is the source of truth).

## 1. Principles

1. **Lives in `products/core`, isolated.** All website code goes under `products/core/frontend/src/website/`, with its **own Vite entry**. The website never imports app pages; the app never imports website code.
2. **Seed changes are additive seams with backward-compatible defaults.** The owner's concern ("the seed is probably gonna break things") applies to building the site *as* a seed product. Seed seams whose default is today's behaviour change nothing for the other products; they only make the core change possible without a fork. **Each seed seam below needs owner approval ([14 · Open decisions](14-build-plan.md#open-decisions)).** Each is proven on core first (pilot), with fleet tests green.
3. **Kill switch, not big-bang.** The website can be switched off in one click, with no deploy (§5).
4. **Prod-first safety.** Core is live (it's in both `build-scope.txt` and `active-scope.txt`), so `predeploy_check`, green CI and `deploy_image` auto-rollback are mandatory.

## 2. Routing today (evidence)

- **Core config.** `products/core/frontend/src/main.tsx:47-83` passes `Landing`, sets `unauthRedirect: '/'` and maps `'/'` to Dashboard.
- **Seed router** (`seed/framework/frontend/src/app.tsx`):
  - `/landing` → `/` (l.281).
  - A logged-out visitor sees `Landing` only at `/`, and every other path is sent back to `/`. The deep link is lost and no return URL is kept (l.225-233).
  - The seed mounts `/settings/ai` unprefixed (l.167).
  - **There is no base-path seam.**
- **Serving.** `_mount_spa` (`seed/framework/backend/noctusai_seed/app.py:466-597`) is `StaticFiles(html=True)`, mounted **last**, so registered routes win. An unknown extensionless path falls back to `index.html` with no-cache. `api/` and `_*` paths are never served that fallback.

## 3. Moving the dashboard to `/app`

**Seed seam (S1).** Add `appBasePath` to `createProductApp`, default `''`. It prefixes authenticated routes, internal redirects and the seed-mounted routes. Also add a **`returnTo`** on the logged-out redirect, which fixes the lost deep link fleet-wide. Core then:
- sets `appBasePath: '/app'`;
- removes `Landing` from the app config;
- sets `unauthRedirect: '/login'`.

**Blast radius (audit):**

| Class | Items |
|---|---|
| **Must change (core)** | `Login.tsx:50`; `Onboarding.tsx:113,144`; `AcceptInvite.tsx:147,168`; `CoreLayout.tsx:33`; `navigate('/')` in Pricing (149, 222), CheckoutSuccess (21), CheckoutCancel (27), AccountSettings (41), APIKeys (69), TeamManagement (161), OrgSettings (91), BillingSettings (174); `Layout.tsx:93` `brandHref`; Stripe success/cancel URLs `Pricing.tsx:129-130`; e2e `dashboard.spec.ts:15,25,33`, `auth.spec.ts:65,117` |
| **Must change (fleet, via seed)** | "Voltar ao NoctusAI" `BackToCore` (`layout.tsx:238`), SSOCallback links (`SSOCallback.tsx:202,231`), Header `platformUrl` (`layout.tsx:460`), and **26 product files** using `href={CORE_URL}`. Add an `env.CORE_APP_URL` getter (`seed/lib/frontend/src/env.ts`) and apply it with an **AST codemod** (never regex) |
| **Safe as-is** | Logout → CORE_URL (landing on the website is fine); `onExpired`; core session expiry → `/login`; invite e-mail `/invite/{token}`; OAuth `redirect_to=/login`; SSO → products; consent routes |
| **Covered by server 301s** | `/billing`, `/team`, `/settings*`, `/org-settings`, `/api-keys`, `/admin/*`, `/checkout/*`, `/onboarding`, legacy `/pricing` → `/app/…` (bookmarks and in-flight Stripe sessions) |
| **Pre-existing bug (fix on contact)** | The backend's fallback checkout URLs point to `/billing/success` and `/billing/cancel` (`billing_service.py:125-126`, `billing.py:229-230`). No such frontend route exists and there's no NotFound page, so users land on a blank page |

**Canonical host, OPEN.** `noctusai.com` and `core.noctusai.com` both reach `core:8000` (`deploy/tunnel/ingress.yml:44-51`); `VITE_CORE_URL` = `core.*`. Tokens live in `localStorage`, which is per origin, so logging in on one host doesn't log you in on the other. Options:
- **(a)** The app stays at `core.noctusai.com/app` and the apex serves only the website, with 301s from apex `/app/*` to `core.*`.
- **(b)** Everything moves to the apex, and `core.*` 301s there.

Either way, `core.*` public pages get `noindex` or a 301 plus canonical.

## 4. Prerendering

- **Stack:** React 18, react-router 7 (library mode), Vite 8. There's no precedent in the repo (no prerender, `renderToString`, `og:` or hreflang code).
- **Chosen approach:** a separate **website entry** built twice, once as a client build and once with `vite build --ssr`. A Node prerender script renders every public route × language with `StaticRouter` + `renderToString` into `dist/_site/<lang>/<path>/index.html`, and the client hydrates.
  - It's wired through core's `package.json` `build` script and the `extend` option of `vite.config.factory.ts` (lines 41, 357). **No seed fork.**
  - Headless-browser prerendering is rejected: it would need Chromium in the seed-propagated Docker image.
- **SSR hazards (seed fix S1):**
  - `useTheme` reads `localStorage` in its `useState` initializer (`useTheme.ts:30`). It needs a `typeof window` guard plus the inline no-flash head script.
  - Anything touching `window` or `document` at module scope is banned in website code (lint rule).
- **Prerendered data.** Static copy is baked at build time from `website_settings` and copy snapshots. **Settings or copy changes made in the admin take effect without a redeploy:** the website HTML router (§5) renders from the DB on request, with a short cache and a purge on save. Build-time prerendering then covers only the static pages, and DB-backed pages get server rendering through the same SSR bundle. **DECISION for the build slice:**
  - either (i) SSR on request with a cache (always fresh);
  - or (ii) prerender plus a rebuild-on-publish hook.

  The recommendation is **(i)**. It uses the same bundle, and it's what makes the admin toggles immediate.

## 5. Serving, meta injection & the kill switch

A **core-local FastAPI "website router"** is registered *before* the SPA mount. It owns:
- `/`, `/en`, and every public path in [05](05-information-architecture.md#sitemap);
- `/blog/*`;
- `/sitemap.xml`, `/robots.txt`, `/rss.xml`, `/llms.txt`;
- the legacy 301s.

It:
1. reads `website_settings` (cached);
2. returns the SSR'd HTML with per-page `<title>`, meta, canonical, hreflang, OG and JSON-LD injected, including DB-backed blog posts;
3. drops hidden sections and pages (they 404, or 301 to the parent if they were ever public).

**Kill switch.** When `website_settings.site_enabled = false`, the router serves the **app shell `index.html`** and the legacy `Landing.tsx` renders exactly as today. Switching back on is instant. Login, SSO and consent routes are never owned by this router.

## 6. Bundle isolation

- three.js (and R3F, if chosen) is imported **only** via dynamic `import()` from `src/website/hero3d/`.
- **Gate 1 (new keeper):** no static import of `three` or `@react-three/*` outside `src/website/hero3d/`.
- **Gate 2 (post-deploy):** `noctus.dev.spa_smoke(products=['core'], expect_absent=['WebGLRenderer'])` against the **app** bundle.
- Budgets live in [09](09-seo-performance-a11y.md#budgets).

## 7. Reuse / retire

| Existing | Fate |
|---|---|
| `pages/Landing.tsx` | Becomes the **kill-switch fallback**. Fix its stale docblock (it still says `/landing`). Its hardcoded `PRODUCTS` stays as-is while it's only a fallback |
| `components/LandingFooter` | Reference only. The website footer is new (rebrand) |
| `pages/Pricing.tsx` (authenticated) | Stays in the app (`/app/pricing`). The website needs a **public plans endpoint**, because `/api/plans` requires a user (`plans.py:24-31`) |
| `platform_settings` (key/value with `is_secret`) | **Not reused.** Use a dedicated `website_settings`, so a public read endpoint never touches a table that holds secrets |

## 8. Seed-first inventory (what exists vs. what's built)

| Capability | State | Plan |
|---|---|---|
| i18n | ABSENT fleet-wide | Small **seed** primitive (the consent banner needs pt/EN too, so it's consumer #2) |
| Theme | PARTIAL (`useTheme`, not SSR-safe) | Seed fix (S1) |
| Cookie/LGPD banner | ABSENT | **Seed organ** `ConsentBanner` |
| Analytics (consent-gated loaders + first-party events) | ABSENT | **Seed organ** |
| Markdown renderer | ABSENT | **Seed organ** `MarkdownRenderer`: built in the docs-viewer slice for this very page |
| WhatsApp send (WAHA) | EXISTS (`whatsapp/client.py:330` + Fake) | Consume |
| Outbound webhook (n8n fan-out) | EXISTS (`outbound_webhook`, Fake+Real+factory) | Consume (the n8n adapter manages workflows; wrong shape for this) |
| Turnstile | EXISTS | Consume on every public form |
| E-mail | PARTIAL (Resend helper, no Protocol/Fake; core duplicates it) | Formalize Protocol + Fake + Real + factory **first** (3rd instance) |
| Leads model | PRODUCT-LOCAL (`orbity.leads` + activities) | N=2 with the website: **triage now**; likely a seed `domain/leads` |
| Roles | `noctus_users.role` is free TEXT; RLS + `get_current_admin` hardcode `admin` | Add `marketing` + an `is_website_editor()` SQL helper + a backend dependency; **role-aware shell** for the Website group (the admin shell currently gates `/admin/*` on `isAdmin`) |

## 9. Directory layout (target)

```
products/core/frontend/src/website/
  entry-client.tsx · entry-server.tsx · routes.tsx
  i18n/ (pt-BR.json, en.json)        tokens/ (site.css — scoped [data-surface="site"])
  components/ (Header, MegaMenu, CtaPair, AudienceCard, ProductChapter, FauxUiPanel,
               ArchitectureDiagram, PricingCard, FaqAccordion, PostCard, LocaleBar,
               WhatsAppFloat, Footer …)
  sections/ (Hero, Audiences, Products, CustomBuilds, Trust, SocialProof, Pricing, News, Faq, ClosingCta)
  pages/ (Home, ProductIndex, Product, Solutions, Pricing, Blog, Article, News, About, Contact, Waitlist, Legal, NotFound)
  hero3d/ (lazy scene chunk + poster assets)
  docs/  ← this documentation
products/core/frontend/src/pages/admin/website/  ← Documentação, Configurações, Blog, Leads
products/core/backend/…/website/  ← website router, public settings/plans/leads endpoints, admin CRUD
```
