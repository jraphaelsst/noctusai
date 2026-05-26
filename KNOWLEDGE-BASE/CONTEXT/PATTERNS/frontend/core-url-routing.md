# Core-URL routing — the MANDATORY system for product↔core linking

> **One-line rule.** A product frontend resolves core's URL through the **canonical seed getter** `env.CORE_URL` / `env.CORE_API_URL` (`@noctusai/lib`). **Never** hand-roll `import.meta.env.VITE_CORE_* || "<literal>"`. New products inherit a working SSO + cross-product nav **by construction**; the `check_handrolled_core_url` keeper blocks any regression.

This is the front-door doc for "how does a product reach core?" — SSO callback, the
"back to dashboard" nav link, any product→core XHR. It exists because the resolution
recurred wrong N≥3× and caused a prod SSO outage (2026-05-25). Sibling depth:
`boundary-contract-tests.md` B1 (build-injection), `seed-canonical-defaults.md`
(why a default must be the canonical answer), `dev-prod-parity.md` (VITE is baked).

---

## 1 · Why core needs a *resolved* URL at all

core is the **identity provider + launcher**. Every product:
- exchanges the SSO token at **core's backend** (`POST ${coreApiUrl}/api/sso/session`),
- links back to **core's frontend** (the dashboard, login redirect, accept-invite).

core is **same-origin** (FE + API on one host — the single-container house model):
`core.noctusai.com` in prod, `localhost:8000` (the house port) in dev. So there is
really **one** core URL. The wart that caused the bugs: a separate
`VITE_CORE_API_URL` existed but was baked for only `core`/`erp` — every other product
baked only `VITE_CORE_URL`.

## 2 · The two layers of the routing system

| Layer | Where | Resolves | Source of truth |
|---|---|---|---|
| **Frontend → core** | product SPA | core's URL (SSO XHR + nav) | seed getter `env.CORE_URL` / `env.CORE_API_URL` (`seed/lib/frontend/src/env.ts`) |
| **Launcher → product** | core backend | each product's tile URL | `resolve_product_url(slug, db_url_base)` → `PRODUCT_URL_<SLUG>` env ∨ `PRODUCT_URL_PATTERN` ∨ `public.products.url_base` (the **house** port) |

This doc is primarily the **frontend → core** layer (the mandatory rule). The
launcher → product layer is covered by [[reference_cross_product_nav_url_resolution]]
+ [[feedback_product_url_base_house_port]] (dev `url_base` = the house port, never the
vestigial frontend port).

## 3 · The canonical getter (the ONE resolution site)

`seed/lib/frontend/src/env.ts`:

```ts
get CORE_URL()     { return getViteVar('VITE_CORE_URL') || 'http://localhost:8000'; }
get CORE_API_URL() { return getViteVar('VITE_CORE_API_URL') || getViteVar('VITE_CORE_URL') || 'http://localhost:8000'; }
```

- `CORE_API_URL` falls back **VITE_CORE_API_URL → VITE_CORE_URL → house port** — so a
  product baking only `VITE_CORE_URL` (the prod norm) still resolves the SSO XHR target.
- `CORE_URL` defaults to the **house port `8000`** (NOT the dead pre-house vite port
  `5173`).
- `getViteVar` is **dynamic** `import.meta.env['VITE_CORE_*']` access. This is
  **prod-safe**: `createProductSupabase` reads `env.SUPABASE_*` the same way and Supabase
  auth works in prod (vite populates a runtime `import.meta.env` object dynamic access
  resolves). `vite.config.factory` `define` only rewrites `VITE_BACKEND_API_URL` +
  `VITE_PRODUCT_SCHEMA`; everything else loads via `envDir: repoRoot`.

**Consumers** (`seed/framework/frontend/src/app.tsx` SSOCallback, `layout.tsx`
BackToCore, every product `Login`/`Landing`/`AcceptInvite`/`LLMPreferences` +
`Configuracoes` core-XHR) read the getter:

```ts
import { env } from "@noctusai/lib";
const CORE_URL = env.CORE_URL;                 // nav
<SSOCallback coreApiUrl={env.CORE_API_URL} coreUrl={env.CORE_URL} />  // SSO
```

## 4 · MANDATORY — what you may and may not write

✅ **DO** `import { env } from "@noctusai/lib"` and use `env.CORE_URL` / `env.CORE_API_URL`.
❌ **DON'T** write `import.meta.env.VITE_CORE_URL || "http://localhost:5173"` (nav) or
`import.meta.env.VITE_CORE_API_URL || "http://localhost:8000"` (SSO/XHR) — the
hand-rolled `|| <literal>` default is exactly the recurrence.

**Carve-out (the ONE legitimate hand-roll):** `products/core/frontend/src/lib/api.ts`.
core is same-origin *to itself*, so its api client reads `VITE_CORE_API_URL` with a
`window.location.origin` fallback (NOT `VITE_CORE_URL`). Nothing else.

## 5 · Enforcement — `check_handrolled_core_url` (Stage-4 keeper)

Per-product compliance detector (`mcp/noctusai/tools/noctus/dev/compliance.py`,
colocated `tests/test_handrolled_core_url.py`). Flags any
`import.meta.env.VITE_CORE_*` in `products/<slug>/frontend/src/**` (severity **high**),
carving out only core's `lib/api.ts`. Part of `check_all_products` → the
regression-baseline gate ([[compliance-regression-baseline]]) → CI-red on any new
hand-rolled instance. **This is what makes the rule mandatory, not merely documented.**

## 6 · New-product guarantee (why you won't bump into this again)

A scaffolded product gets working SSO + nav **by construction**, no per-product wiring:
1. The **SSO callback** lives in `seed/framework/frontend/src/app.tsx` → inherited; it
   reads `env.CORE_API_URL` / `env.CORE_URL`.
2. The **template** (`products/seed/` → auto-synced `templates/product-seed/`) ships
   `Login`/`Landing`/`AcceptInvite` already consuming `env.CORE_URL`.
3. The product Dockerfile bakes `ARG VITE_CORE_URL`; `build-and-push.yml` sets
   `VITE_CORE_URL=https://core.noctusai.com` ⇒ prod resolves the real core.
4. core CORS allows the new origin in prod via `@registry:all` → `PRODUCT_URL_<SLUG>`;
   in dev via the `.env` `CORS_ORIGINS` house-port band.

**Residual manual steps at deploy time** (NOT scaffold-time): set the new product's
`PRODUCT_URL_<SLUG>` in the VPS `.env` (prod nav + CORS), and ensure its house port is
within the dev `.env` `CORS_ORIGINS` band. See [[feedback_product_url_base_house_port]].

## 7 · The recurrence (provenance)

Born 2026-05-25 (`feat/seed-core-url-resolver` `5021ce0c` + `feat/core-url-routing-mandatory`).
The seed shipped the getters but **nobody consumed them** — every product hand-rolled
`import.meta.env.VITE_CORE_* || <literal>`, the wrong default propagated by copy-paste
precedent. Two failure modes, one root: SSO-XHR (`localhost:8000` → "Failed to fetch"
in prod) + nav (`localhost:5173` → dead link). Fix = correct getters + drive every
consumer to them (all products, pilots + non-pilots) + the keeper. Siblings:
[[feedback_sso_core_url_seed_resolution]] · [[feedback_product_url_base_house_port]] ·
`boundary-contract-tests.md` B1.

## 8 · Verifying the live chain (dynamic e2e)

The keeper (`check_handrolled_core_url`) + by-construction seed guarantee SSO
**statically**. To verify a **LIVE deployed** core's SSO end-to-end, run
`noctus.dev.sso_smoke` — it drives the full chain a product's `SSOCallback`
uses: Supabase magic-link login → `POST /api/sso/token` (license-checked) →
`POST /api/sso/session` → `GET /api/auth/me`. `status='pass'|'fail'|
'not_configured'` (honest — no creds ⇒ `not_configured`, never a faked pass).
Needs Supabase creds + `NOCTUS_SSO_SMOKE_EMAIL` (a test account whose org holds
a non-expired license for the probed product). **Two gotchas it encodes:**
(1) core sits behind Cloudflare — a non-browser `User-Agent` is **WAF-banned
(error 1010)**, so every programmatic core caller MUST send a browser UA (same
rule as the Hostinger MCP); (2) the SSO license check enforces **expiry**
(`fim`), so an expired-license org correctly 403s at `/api/sso/token`.
