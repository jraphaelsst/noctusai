# 14 · Build plan

> **Superseded for v1 by [15 · Build contract](15-api-contract.md).** The owner authorized the build + prod deploy on 2026-09-23. The v1 answers to D1–D11 are in 15 §0 (notably D1 = host split: the website owns `noctusai.com/`, the app stays on `core.noctusai.com`, no `/app` move). The waves below remain the roadmap for everything v1 defers (seed promotion, blog, marketing copy editor, rebrand).

## Open decisions

| # | Decision | Options / recommendation | Blocks |
|---|---|---|---|
| D1 | **Canonical host for the app** | (a) The app stays at `core.noctusai.com/app` and the apex serves only the website. (b) Everything moves to the apex and `core.*` 301s there. **Recommendation: (a)**. It's the smaller change: tokens are stored per origin and `VITE_CORE_URL` is already `core.*`. | S5, S6, S9 |
| D2 | **Seed seams** (`appBasePath` + `returnTo`, SSR-safe `useTheme`, `CORE_APP_URL` getter) | Additive, with defaults that leave every other product unchanged; proven on core first. **Recommendation: approve.** The alternative is a core-local fork of the seed router | S1 → S5, S6, S9 |
| D3 | **New seed organs** (i18n, ConsentBanner, analytics loaders, MarkdownRenderer) vs. core-local | Other products (ERP and academia landings, knowledge-extractor) will need them. **Recommendation: seed**, per the componentize-everything rule | S2 |
| D4 | **Leads model**: seed `domain/leads` vs. core-local | It would be the 2nd instance after `orbity.leads`, so it needs triage (`noc-triage`) | S3, S4 |
| D5 | **SSR mode**: on-request SSR with cache vs. prerender + rebuild on publish | **Recommendation: on-request SSR + cache.** Admin toggles then take effect immediately ([08 §4](08-technical-architecture.md#4-prerendering)) | S5, S7 |
| D6 | **Hero primary CTA**: WhatsApp vs. sign-up/waitlist | **Recommendation: WhatsApp** in the hero; the header keeps sign-up/waitlist | S7 copy |
| D7 | **Rebrand direction** (Constellation / Aurora / Night grid) + faces + palette | Higgsfield exploration, **with owner permission per session** | S7 visual layer, S12 |
| D8 | **Privacy text + analytics timing** (GA4/Pixel vs. the current "strictly-necessary only" text; whether cookieless analytics runs before consent) | compliance-reviewer + owner | S2 analytics, launch |
| D9 | **Capture archive home** (~58 MB of tiles/frames) | Private bucket + signed URLs (recommended) vs. discard | none (docs) |
| D10 | EN pricing currency (BRL vs. USD) · lead retention months · internal WhatsApp alert number | Owner | S4, S7 |
| D11 | **Waitlist ↔ sign-up relation**: when sign-up reopens, invite waitlisters automatically? | Owner | S4 |

## Waves & slices

C1 means no overlapping files; C2 means the overlap is additive only; C3 means the slices must be sequenced. Every slice has its own worktree and branch-pointer, and integration happens after the gates.

**Wave 0 · done / in flight**
- **Docs + reference research:** this document set (`feat/noctus-website-docs`).
- **S0 Docs viewer:** the seed `MarkdownRenderer` organ + the **Website → Documentação** sidebar item and page (`feat/website-docs-viewer`, frontend-engineer).

**Wave 1 · foundations (parallel)**
| Slice | Owner | Class | Scope |
|---|---|---|---|
| S1 | engineer-seed | C1 | Seed seams: `appBasePath` + `returnTo`, SSR-safe `useTheme` + no-flash head script, `env.CORE_APP_URL` (D2) |
| S2 | engineer-seed | C1 | Seed organs: i18n primitive, `ConsentBanner` (equal reject/accept, bottom bar), consent-gated analytics loaders + first-party event client (D3, D8) |
| S3 | engineer-seed | C1 | E-mail Protocol + Fake + Real + factory (formalize; core's duplicate becomes a consumer); leads domain per D4 |
| S4 | backend-engineer | C1 | **Contract first** (`noc-contract-first`). Migrations: `website_settings` (versioned), `leads`, `lead_activities`, `site_events`, `blog_posts`, `marketing` role + `is_website_editor()`. Routers: public settings (subset), **public plans**, leads (Turnstile, dedupe, fan-out via WAHA / e-mail / `outbound_webhook`), `signup_enabled` enforcement on `/api/auth/signup`, admin CRUD. The OpenAPI contract is published before any frontend slice |

**Wave 2 · routing + site**
| Slice | Owner | Class | Scope |
|---|---|---|---|
| S5 | backend-engineer | C3 after S1, S4 | Website router: SSR/meta injection, sitemap/robots/rss/llms.txt, hreflang, legacy 301s, kill switch; plus the checkout-URL bug fix |
| S6 | frontend-engineer | C3 after S1 | The app moves to `/app`: role-aware shell, `navigate('/')` sweep, Stripe URLs, e2e updates (auth, SSO round-trip, logged-out → website) |
| S7 | frontend-engineer | C1 | Website entry: SSR pipeline, scoped tokens (bootstrap values until D7), header/footer/mega-menu, all sections + pages from [07](07-page-specs.md), i18n, theme switch, consent integration, WhatsApp float, forms |
| S8 | frontend-engineer | C1 | `hero3d/`: poster pipeline, lazy scene, HUD labels, theme uniforms, opt-in on mobile, budgets (D7 motif; bootstrap scene until approved) |

**Wave 3 · operations**
| Slice | Owner | Class | Scope |
|---|---|---|---|
| S9 | frontend-engineer | C3 after S1 | **AST codemod** of the 26 fleet `href={CORE_URL}` sites → `env.CORE_APP_URL` (pilot on 3 products first) |
| S10 | frontend-engineer | C2 against S4's contract | Admin pages: **Configurações**, **Blog** (CMS + preview + publish), **Leads** (board, table, detail, dashboard strip, export). Each sidebar item is added only in the slice that makes it real |
| S11 | devops-engineer | C1 | Gates: bundle-isolation keeper (no static `three` outside `hero3d/`), `spa_smoke expect_absent=['WebGLRenderer']`, canonical-host / `noindex` on `core.*` (D1), Lighthouse CI budget, private bucket for covers + archive (D9) |
| S12 | tech-lead + owner | — | Rebrand exploration via Higgsfield (**permission per session**) → identity approval → token values + motif assets swapped in |
| S13 | compliance-reviewer + security | advisory | Consent text update, LGPD flag intake, threat model for the public forms + lead endpoints (spam, enumeration, PII) |

## Gates

Every slice passes these:
- the scoped test suites;
- `tsc` + `vite build`;
- the relevant keepers;
- **per-branch green ≠ integration green**: re-run on the merged tip.

Website slices also pass:
1. **SEO:** every public route has one H1, a unique title and meta, a canonical, reciprocal hreflang and valid JSON-LD (an automated check over the SSR output).
2. **No-JS:** a SSR snapshot of each route shows full content (no hidden sections).
3. **Budgets:** Lighthouse mobile ≥ 90 performance, 100 SEO, ≥ 95 a11y and best practices, verified with Chrome DevTools MCP locally and in CI.
4. **Isolation:** the app bundle has no `WebGLRenderer`, and the website bundle doesn't import app pages.
5. **Auth regressions:** the e2e suite covers login, logout, SSO round-trip from a product, invite accept and Stripe checkout return. Auth tests assert a strict `== 401`.
6. **Consent:** 0 third-party requests before consent (network trace).

## Rollout (prod-first: core is live)

1. **Ship backend + admin with `site_enabled = false`**, so visitors keep seeing the legacy landing. `predeploy_check` + green CI + `deploy_image` auto-rollback.
2. **Move the app to `/app` with the 301s** as its own deploy, and watch the SSO smoke (`noctus.dev.sso_smoke`) and the fleet smoke.
3. **Ship the website runtime** (still disabled). Verify with the internal preview (admin-only flag).
4. **Owner flips `site_enabled`** after reviewing the live preview. The kill switch stays one click away.
5. Submit the sitemaps (Search Console), check hreflang reports, monitor CWV for 2 weeks.

## Follow-ups

- `noctus.dev.site_reference_capture` MCP tool (if research repeats; [13](13-tooling-and-mcp-policy.md#reference-capture-tooling)).
- Migrate knowledge-extractor's pre-wrap methodology page to the seed `MarkdownRenderer` (consumer #2).
- Retire the dead `defaultOpen` config across products' `NAV_GROUPS` (the seed `Sidebar` ignores it).
- v1.1: Novidades, Desenvolvedores, pillar long-reads, the "Pergunte à IA" section (front door for the lead-closing agent), and a cost calculator on `/precos`.
- The app adopts the website brand (a separate project, after the rebrand settles).
