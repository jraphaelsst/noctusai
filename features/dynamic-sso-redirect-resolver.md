# Feature — dynamic-sso-redirect-resolver

> **What this is.** Replaces hardcoded `http://localhost:<port>` URLs in cross-product redirects with an environment-aware seed-side resolver. Lives in `noctusai_lib.api.product_urls` so every product inherits it via the seed by default — no per-product wiring. Resolution order: per-product env var → platform-wide pattern env var → DB fallback (`public.products.url_base`). Works for existing products and new ones the moment they're scaffolded.

- **Created:** 2026-05-05
- **Owner:** rapha
- **Trigger:** User directive 2026-05-05 — *"Do something dynamic that's adaptable to others, guarantee it's a system that manages that, not hardcode. For seed, so it's expanded to products existing and new ones by default wiring."*

## What was hardcoded

The URLs used by Core to redirect into a product (post-login + dashboard tile click) came from `public.products.url_base`, which is populated at scaffold time as `http://localhost:<frontend_port>`:

- `products/core/backend/app/routers/sso.py:195` — `f"{product.data['url_base']}/sso?token={sso_token}"` (the `RedirectResponse` from `GET /api/sso/launch/{slug}`).
- `products/core/backend/app/routers/auth.py:185-192` — products list returned to the frontend dashboard; tile click reads `product.url_base` directly.

When the platform deploys to Cloudflare (or any non-localhost host), every row's `url_base` would have to be rewritten in the live DB to match. Brittle, error-prone, and breaks the "seed-first / no per-product hand-edits" philosophy.

## Resolution order (seed-side resolver)

`noctusai_lib.api.product_urls.resolve_product_url(slug, *, db_url_base)`:

1. **Per-product env var** `PRODUCT_URL_<UPPER_SLUG_UNDERSCORED>` — slugs with hyphens become underscores: `media-scheduling` → `PRODUCT_URL_MEDIA_SCHEDULING`. Highest priority — pin a single product to a specific URL without touching anything else.
2. **Pattern** `PRODUCT_URL_PATTERN` — supports `{slug}` and `{slug_underscored}` placeholders. One pattern covers a fleet of products with a uniform host scheme. Examples:
   - `PRODUCT_URL_PATTERN=https://{slug}.noctus.ai` → `https://media-scheduling.noctus.ai` for slug `media-scheduling`.
   - `PRODUCT_URL_PATTERN=https://app.noctus.ai/{slug}` → `https://app.noctus.ai/media-scheduling`.
   - `PRODUCT_URL_PATTERN=https://app.example.com/{slug_underscored}` → `https://app.example.com/media_scheduling`.
3. **DB fallback** — `public.products.url_base` (typically `http://localhost:<port>` from the scaffold tool's seed-row migration). Dev default; deployments override via env.

When all three are absent, raises `ValueError` with a message naming both env knobs + the DB column. **Silent fallback to `localhost:8000` is forbidden** per platform rule — caller must surface the gap.

## Wiring

- **Resolver:** `seed/lib/backend/noctusai_lib/api/product_urls.py` (new, ~90 lines).
- **Tests:** `seed/lib/backend/tests/test_product_urls.py` — 12 cases covering each layer of the resolution order, slash stripping, empty-slug handling, missing-everything raise.
- **Backend integrations:**
  - `products/core/backend/app/routers/sso.py:195` — `GET /api/sso/launch/{slug}` redirect uses resolver.
  - `products/core/backend/app/routers/auth.py:185-192` — `GET /api/auth/me` products list resolves each row's `url_base` before returning to frontend, so dashboard tile clicks pick up the resolved URL automatically. Resolver-failure is logged at WARNING and falls through to the raw DB value (the dashboard must render even when one product's URL config is gappy — Core itself shouldn't 500).

The frontend (`Dashboard.tsx`, `AdminProducts.tsx`) is unchanged — it already renders whatever `url_base` the API returns, so resolving server-side is fully transparent.

## Default-wiring proof

- **Existing products** (core, erp-imobiliario, personal-finance, therapy-platform, daily-life, mailing, adconnect, dev-team, media-scheduling) — all routed through the resolver via the two backend call sites. No per-product code change needed.
- **Future products** — `noctus.dev.scaffold_product` continues to seed `url_base = http://localhost:<port>` (dev default). The resolver picks up env overrides automatically the moment the new slug exists in DB. No additional wiring step on scaffold.

## Files touched

- `seed/lib/backend/noctusai_lib/api/product_urls.py` — new resolver.
- `seed/lib/backend/tests/test_product_urls.py` — 12 new tests.
- `products/core/backend/app/routers/sso.py` — import + use resolver in `/launch/{slug}` redirect.
- `products/core/backend/app/routers/auth.py` — import + use resolver in `/me` products list. Failure logged at WARNING, falls back to raw DB value (Core stays up).

## Tests

- 12 resolver unit tests pass (`seed/lib/backend/tests/test_product_urls.py`).
- 53/53 core auth + sso router tests pass after wiring (`products/core/backend/tests/routers/test_auth_router.py`, `test_sso_router.py`). One unrelated pre-existing failure in `test_test_accounts_router.py` (`public.plans.is_active` schema drift) is unaffected by these changes.

## Methodology rule (durable)

> Cross-product URLs are resolved through `noctusai_lib.api.product_urls.resolve_product_url`, never constructed by direct DB-column reads or by hardcoded localhost paths. Every new endpoint that emits a cross-product URL routes through the resolver. Adding a new endpoint that bypasses the resolver = silent-error shape: it'll return localhost URLs in production environments where the env override isn't visible.

## Sub-tasks

- [x] Resolver implemented in `noctusai_lib.api.product_urls`.
- [x] Tests (12 cases) — pass.
- [x] `sso.py:195` wired through resolver.
- [x] `auth.py:185-192` wired through resolver with WARNING-log fallback.
- [x] Core router tests (auth + sso) green: 53/53.
- [x] Frontend untouched — verified by reading `Dashboard.tsx:64` and `AdminProducts.tsx` URL usages (read-only consumption of the API response).
- [x] Feature documented (this file).

## Out of scope (deferred)

- **`.env.example` edit** — repo has no `.env.example`. Inline examples live in this feature doc + the resolver's docstring.
- **Frontend equivalent for self-hosted vite proxy** — current frontend reads its own `VITE_BACKEND_API_URL` from the build, set per-product. Not part of cross-product URL resolution. Future work.
- **Wildcard pattern with port substitution** — could add `{port}` placeholder for multi-port deploys; not needed yet.
- **Caching** — env lookups are O(1); no caching layer needed.
