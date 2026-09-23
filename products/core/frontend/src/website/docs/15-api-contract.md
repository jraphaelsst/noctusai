# 15 · Build contract v1 (FE ↔ BE ↔ serving)

> Authored 2026-09-23 by the tech-lead **before** dispatch (skill `noc-contract-first`). All three build slices (backend, website, admin) build **to this file**; any change goes through the tech-lead and bumps this doc. Owner authorization for the build and the prod deploy: 2026-09-23 ("go all the way to prod").

## 0 · Decisions taken for v1 (owner delegated: "go all the way")

| # | Decision | v1 answer |
|---|---|---|
| D1 | App host / root | **Host split**: the website owns `/` on **`noctusai.com`** (and `www.` → 301 apex). The logged app stays **unchanged at `core.noctusai.com`** (dashboard still at `/` there). On the apex, app paths **301 to `https://core.noctusai.com<same path+query>`**. **No `/app` move**: zero SSO/return-URL blast radius. Supersedes the `/app` plan in [08 §3](08-technical-architecture.md#3-moving-the-dashboard-to-app) for v1 |
| D2 | Seed seams | **Not needed in v1** (the host split removes the need for `appBasePath`). The website ships its own SSR-safe theme hook. **No seed changes in v1** |
| D3 | i18n / consent / analytics organs | Built **website-local** under `src/website/`, each file marked `NOC-REMEDIATE[seed-promotion]` (named destination: a seed organ once a 2nd consumer exists) |
| D4 | Leads model | **Core-local** `website_leads` (v1); seed `domain/leads` triage stays open (N=2 with `orbity.leads`) |
| D5 | SSR mode | The runtime image has no Node, so there is no on-request SSR. **Build-time prerender** (node stage) + **FastAPI post-processing** at request time: strips admin-hidden sections by marker, injects the public settings JSON, and applies per-page meta. Dynamic, DB-driven parts (curated products, FAQ, trust items, pricing) hydrate from the injected JSON |
| D6 | Hero primary CTA | WhatsApp |
| D7 | Rebrand | **Bootstrap identity** (neutral night palette + Inter/JetBrains Mono + procedural three.js scene). The Higgsfield exploration waits for owner permission; the identity swap later is a token/asset change |
| D8 | Tracking | Consent infra ships; GA4/Meta Pixel/Plausible load **only if an id is configured AND consent is granted**. IDs start empty ⇒ nothing third-party loads at launch. The privacy text update stays open for compliance |
| D9 | Capture archive | Stays out of the repo |
| D10 | Currency / retention / alert number | BRL in both languages; lead retention 18 months (documented, job later); WAHA alert only if `WEBSITE_SALES_WHATSAPP` env is set |
| D11 | Waitlist → sign-up | Manual for now (admin sees waitlist leads) |
| — | Blog | **Deferred to v1.1**: section `news` default off, no `/blog` routes in v1 |

## 1 · Database (core migration `052_website.sql`, schema `public`)

```sql
website_settings (
  id          bigserial primary key,
  version     int not null unique,          -- monotonically increasing; current = max(version)
  data        jsonb not null,               -- WebsiteSettings (§2)
  created_at  timestamptz not null default now(),
  created_by  uuid null references noctus_users(id)
)
website_leads (
  id uuid pk default gen_random_uuid(),
  created_at, updated_at timestamptz,
  source text not null check (source in ('waitlist','brief','contact','signup_intent')),
  name text not null, email text null, phone_e164 text null,
  company text null, profile text null check (profile in ('smb','enterprise','developer','solo') or profile is null),
  product_interest text[] not null default '{}', message text null,
  locale text not null default 'pt-BR' check (locale in ('pt-BR','en')),
  utm jsonb not null default '{}', landing_path text null, referrer text null,
  consent jsonb not null,                   -- {marketing: bool, text_version: str, at: iso, ip_hash: str}
  stage text not null default 'novo' check (stage in ('novo','contatado','qualificado','proposta','ganho','perdido','descartado')),
  owner_user_id uuid null references noctus_users(id), owner_agent text null,
  score int null, next_action text null, next_action_at timestamptz null, lost_reason text null,
  dedupe_key text not null                  -- lower(email) or phone_e164; index (not unique): repeats merge by appending an activity
)
website_lead_activities (
  id uuid pk, lead_id uuid not null references website_leads(id) on delete cascade,
  at timestamptz not null default now(),
  kind text not null check (kind in ('created','form_submit','note','stage_change','whatsapp_out','whatsapp_in','email_out','call','agent_action','handoff','fanout_failed')),
  actor text not null,                      -- 'user:<uuid>' | 'agent:<name>' | 'system'
  payload jsonb not null default '{}'
)
website_events (
  id bigserial pk, at timestamptz default now(), anon_id text null, session_id text null,
  event text not null, path text null, props jsonb not null default '{}'   -- NO PII
)
```

- **RLS enabled on all four, with no anon or authenticated policies.** Access is backend-only via the service-role client (house pattern). Follow the repo's service-role/RLS conventions and schema-exposure rules.
- **Role:** `noctus_users.role` accepts `'marketing'` (free TEXT today; if a CHECK exists, extend it). SQL helper `public.is_website_editor(uid uuid) returns bool` = role in (`admin`,`marketing`).

## 2 · `WebsiteSettings` JSON (the single shape FE and BE share)

```ts
type L10n = { pt: string; en: string };
type WebsiteSettings = {
  site_enabled: boolean;          // default true at launch (kill switch)
  signup_enabled: boolean;        // default true (current behaviour)
  whatsapp: { number_e164: string | null; default_message: L10n; float_enabled: boolean };
  sections: {                     // home section switches (07-page-specs)
    audiences: boolean; products: boolean; custom_builds: boolean; trust: boolean;
    social_proof: boolean;        // default false; BE refuses true when social_proof_items is empty (422)
    pricing: boolean; news: boolean /* default false; v1.1 */; faq: boolean; hero_update_card: boolean /* default false */;
  };
  products: Array<{
    slug: string;                 // must exist in the FE build's product content (§4) — BE validates shape only
    visible: boolean; order: number;
    state: 'disponivel' | 'lista_de_espera' | 'em_breve';
    tagline?: L10n;               // optional override of the build-time copy
  }>;
  trust_items: Array<{ key: string; icon: string; text: L10n; verified_by: string | null; verified_at: string | null }>;
  social_proof_items: Array<{ kind: 'logo' | 'testimonial' | 'metric'; name: string; text?: L10n; image_url?: string; consent_ref: string }>;
  faq: Array<{ q: L10n; a: L10n }>;
  tracking: { plausible_domain: string | null; ga4_id: string | null; meta_pixel_id: string | null };
};
```

- **Defaults, single source.** The FE owns `src/website/content/defaults.ts` (a complete `WebsiteSettings`). The prerender step emits it as `dist/_site/settings.defaults.json`. When `website_settings` has no rows, the BE reads that file (`SERVE_SPA_DIR/_site/settings.defaults.json`) as version 0. The BE never hardcodes defaults.
- **Public subset** (what anonymous clients see): the full object **minus** `trust_items` without `verified_at` (filtered out), `trust_items[].verified_by`, and `social_proof_items[].consent_ref`. `social_proof_items` is emptied when `sections.social_proof` is false. `products` is filtered to `visible`.

## 3 · HTTP API

Envelope: success = `{"data": …}` (+ `"total"` on lists); errors = FastAPI `{"detail": "<code or message>"}`. Money in BRL numbers. Timestamps ISO-8601 UTC.

### Public (no auth; rate-limited per IP with the core `limiter`)

| Method + path | Request | Success | Errors |
|---|---|---|---|
| `GET /api/website/settings` | — | `200 {data: PublicWebsiteSettings, version: int}` | — |
| `GET /api/website/plans` | — | `200 {data: [{id, slug, nome, descricao, price_monthly, price_yearly, max_users, max_products, features, is_custom}]}` (only `ativo`, ordered by `price_monthly`) | — |
| `POST /api/website/leads` | `{source: 'waitlist'\|'brief'\|'contact', name (1-120), email?, phone? (any BR/intl format; BE normalizes to E.164, default +55), company?, profile?, product_interest?: string[], message? (≤2000), locale: 'pt-BR'\|'en', consent_marketing: bool, consent_text_version: string, utm?: object, landing_path?, referrer?, turnstile_token?}`. At least one of email/phone is required. Extra fields → 422 | `201 {data: {id, whatsapp_url: string\|null}}`. `whatsapp_url` = `https://wa.me/<number>?text=<urlencoded prefill>` when the WhatsApp number is set (for "Continuar no WhatsApp") | `422` validation · `403 {"detail":"turnstile_failed"}` (only when Turnstile is configured) · `429` |
| `POST /api/website/events` | `{event: string (1-64, [a-z_]), anon_id?: string, session_id?: string, path?: string, props?: object (≤2 KB)}` | `204` | `422` · `429` |

**Side effects of `POST /leads` (state after the call):**
1. The lead row exists (or an existing lead with the same `dedupe_key` got a `form_submit` activity and updated fields), with a `created` or `form_submit` activity.
2. Fan-out runs **after commit, async, best-effort**:
   - e-mail notify via seed `integrations/email` to `WEBSITE_LEADS_NOTIFY_EMAIL` (if set);
   - WAHA text alert to `WEBSITE_SALES_WHATSAPP` (if set);
   - `outbound_webhook` POST to `WEBSITE_LEADS_WEBHOOK_URL` (if set; for n8n).
   Each failure appends a `fanout_failed` activity with `{channel, error}`. **Never silent, never blocks the 201.**

**Events used by the FE:** `page_view`, `cta_click {cta, section, product?}`, `whatsapp_click {section, product?}`, `waitlist_submit`, `brief_submit`, `signup_start`, `theme_change {theme}`, `locale_change {locale}`, `hero3d_opt_in`, `consent {analytics, marketing}`.

### Admin (auth: `Authorization: Bearer`; dependency `get_website_editor` = admin **or** marketing; `get_current_admin` where marked 🔒)

| Method + path | Request | Success | Errors |
|---|---|---|---|
| `GET /api/admin/website/settings` | — | `200 {data: {version, settings: WebsiteSettings, created_at, created_by}}` | 401 · 403 |
| `PUT /api/admin/website/settings` | `{settings: WebsiteSettings, expected_version: int}` | `200 {data: {version, settings, created_at, created_by}}` (new row = version+1; audit-logged) | `409 {"detail":"version_conflict"}` · `403 {"detail":"admin_only_field"}` if a **marketing** user changes `site_enabled` or `signup_enabled` · `422` (shape; `social_proof` on with 0 items) |
| `GET /api/admin/website/settings/history` | — | `200 {data: [{version, created_at, created_by}]}` (desc, ≤50) | |
| `POST /api/admin/website/settings/rollback` 🔒 | `{version: int}` | `200 {data: {version (new), settings, …}}` (copies the old data as a new version) | 404 |
| `GET /api/admin/website/leads` | query `stage?, source?, q? (name/email/phone/company ilike), limit (≤200, default 50), offset` | `200 {data: [Lead], total}` ordered `created_at desc` | |
| `GET /api/admin/website/leads/{id}` | — | `200 {data: Lead & {activities: Activity[]}}` (activities desc) | 404 |
| `PATCH /api/admin/website/leads/{id}` | any of `{stage, owner_user_id, next_action, next_action_at, lost_reason, score}` | `200 {data: Lead}`; a stage change appends `stage_change {from, to}` with `actor user:<id>` | 404 · 422 |
| `POST /api/admin/website/leads/{id}/activities` | `{kind: 'note'\|'call'\|'whatsapp_out'\|'email_out', body: string (1-5000)}` | `201 {data: Activity}` | 404 · 422 |
| `GET /api/admin/website/leads/export.csv` 🔒 | same filters as list | `200 text/csv` (audit-logged) | 403 for marketing |
| `GET /api/admin/website/stats` | — | `200 {data: {new_today, new_7d, by_source: {src: n}, by_stage: {stage: n}, events_7d: {event: n}}}` | |

`Lead` = the `website_leads` row fields exactly as in §1 (`consent` included). `Activity` = the `website_lead_activities` row.

### Changed existing endpoint
- `POST /api/auth/signup`: when the current `signup_enabled` is false → **`403 {"detail":"signup_closed"}`** before any user creation. Invites (`/invite/:token` flows) are unaffected.
- `GET /api/auth/me` (or whatever core uses to feed `auth-context`) must already return `role`. Marketing users need `role: 'marketing'` visible to the FE.

## 4 · Website build output (FE website slice → BE serving slice)

The core `npm run build` becomes: app build (unchanged) **then** the website build + prerender, producing:

```
dist/_site/
  manifest.json            # {"routes": [{"path": "/", "lang": "pt-BR", "file": "index.html", "alt": "/en", "product": null}, …],
                           #  "product_routes": {"<slug>": {"pt": "/produtos/<slug>", "en": "/en/products/<slug>"}},
                           #  "built_at": iso}
  settings.defaults.json   # WebsiteSettings defaults (§2)
  <route>/index.html       # one per route × language, fully rendered HTML (all sections present)
  assets/…                 # website JS/CSS/fonts/images (Vite base = "/_site/")
  og/…                     # per-page OG images (static PNG/SVG→PNG generated at build, or one per section type)
```

- **Routes v1:**
  - pt-BR: `/`, `/produtos`, `/produtos/<slug>` (every slug in the FE product content), `/solucoes`, `/precos`, `/contato`, `/lista-de-espera`, `/sobre`, `/404`;
  - EN twins: `/en`, `/en/products`, `/en/products/<slug>`, `/en/solutions`, `/en/pricing`, `/en/contact`, `/en/waitlist`, `/en/about`, `/en/404`.
- **Section markers** in every prerendered page: `<!--nx:section:KEY-->…<!--/nx:section:KEY-->` around each switchable home section (keys = `WebsiteSettings.sections` keys). Also `<!--nx:product:SLUG-->…<!--/nx:product:SLUG-->` around each product card/chapter.
- **Settings injection point:** exactly one `<script id="nx-settings" type="application/json">__NX_SETTINGS__</script>` in `<head>`. The BE replaces `__NX_SETTINGS__` with the JSON-escaped public settings (escape `<` as `<`). The FE reads it synchronously on hydrate; when absent (local dev) it falls back to `defaults.ts`.
- **Meta:** the prerender writes the complete `<title>`, meta description, canonical (`https://noctusai.com<path>`), hreflang pt-BR/en/x-default, OG/Twitter and JSON-LD into each HTML. The BE does not rewrite meta in v1.
- **Theme no-flash script:** inline in `<head>`, sets `data-theme` on the website root before paint (reads localStorage `nx.theme` = `system|light|dark`).
- **No `window` or `document` at module scope** anywhere in website code (SSR-safe). three.js is only reachable via dynamic `import()` from `src/website/hero3d/`.

## 5 · Serving (BE slice): `app/routers/website_html.py`, registered **before** the SPA mount

- **Hosts.** `WEBSITE_HOSTS` env (default `noctusai.com,www.noctusai.com`); `CORE_APP_ORIGIN` env (default `https://core.noctusai.com`). Local testing: requests with `?__site=1` or header `X-NX-Site: 1` are treated as website-host **only when `ENVIRONMENT != production`**.
- **Request on a website host:**
  1. `www.` → 301 to the apex, same path.
  2. `site_enabled == false` → fall through to today's behaviour (SPA app shell + legacy `Landing.tsx`) for everything.
  3. Path in `manifest.routes` (with or without a trailing slash) → serve that HTML after:
     - stripping hidden sections (`sections[key] == false`) and hidden products (`!visible`) by marker;
     - injecting the settings JSON;
     - adding `Cache-Control: public, max-age=60`.
     A product route whose slug isn't visible → **404** (serve `/404` HTML with status 404).
  4. `/sitemap.xml` (all visible routes, with `xhtml:link` hreflang alternates), `/robots.txt` (allow all, sitemap line; **disallow** `/api/`), `/llms.txt` (plain-text site map + one-line description per page, pt-BR + EN).
  5. `/api/*`, `/_site/*`, `/assets/*`, `/consent*`, `/favicon*`, static files, `/invite/*` → untouched (fall through). `/invite/*` stays on the apex because invite e-mails may carry apex links; the SPA handles it.
  6. Any other path → **301** to `CORE_APP_ORIGIN + path + ?query` (e.g. `/login`, `/admin/*`, `/pricing`, `/billing`, `/settings*`, `/team`, `/onboarding`, `/checkout/*`, `/org-settings`, `/api-keys`). Unknown non-app paths get the website 404 instead: an app-path allowlist is derived from the core route table (don't hand-maintain; see the lockfile/slug-drift rule). If derivation isn't feasible, 301 everything not matched (documented).
- **Request on any other host** (e.g. `core.noctusai.com`) → unchanged. Optional: `X-Robots-Tag: noindex` on HTML responses from non-website hosts.
- **Settings read** is cached in-process for 30 s and invalidated on `PUT`/rollback in the same process.

## 6 · Admin UI (admin slice)

- Sidebar group **Website** (key `website`): Documentação (exists), **Configurações** `/admin/website/settings`, **Leads** `/admin/website/leads`.
- **Marketing users** see **only** the Website group. `CoreLayout` lets `role === 'marketing'` reach `/admin/website/*` and nothing else under `/admin`.
- **Configurações** tabs:
  - **Geral:** `site_enabled`, `signup_enabled` (disabled for marketing), WhatsApp number + default message pt/EN + float toggle.
  - **Seções:** a switch per key; `social_proof` is disabled with a hint while there are 0 items.
  - **Produtos:** order (drag or up/down), visible, state, tagline override pt/EN; the slug list comes from the current settings.
  - **Confiança:** trust items with verified_by/at.
  - **Prova social:** items + consent_ref.
  - **FAQ:** pt/EN pairs.
  - **Rastreamento:** ids + a warning that the privacy text must be updated before enabling GA4/Pixel.
  - **Histórico:** versions + rollback (admin).

  Save sends `expected_version`; on 409 show "Outra pessoa salvou antes — recarregue".
- **Leads:**
  - table (filters: stage, source, search; pagination);
  - stats strip from `/stats`;
  - detail drawer with the activity timeline, stage select, next action, a note composer, and "Abrir WhatsApp" (`https://wa.me/<phone_e164 digits>`);
  - CSV export button (admin only).
- Honest loading/empty/error states (`showSkeleton = isPending && !data`).

## 7 · Acceptance (end-to-end, run by the tech-lead after integration)

1. `curl -H 'Host: noctusai.com' /` → 200 HTML containing `<h1`, `hreflang`, and the `nx-settings` JSON (not the placeholder).
2. Toggle `sections.pricing=false` via `PUT` → the home HTML no longer contains the pricing marker content.
3. `curl -H 'Host: noctusai.com' /login` → 301 to `https://core.noctusai.com/login`.
4. `POST /api/website/leads` (waitlist) → 201, then the lead is visible via `GET /api/admin/website/leads`.
5. `PUT signup_enabled=false` → `POST /api/auth/signup` 403 `signup_closed`, then restore.
6. `curl -H 'Host: core.noctusai.com' /` → app shell exactly as before.
7. `/sitemap.xml`, `/robots.txt`, `/llms.txt` → 200.
8. The app bundle (`dist/assets/index-*.js`) has no `WebGLRenderer`.
