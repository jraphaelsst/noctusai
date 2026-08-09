# Environment & Configuration

## Single root `.env`

**Everything lives in one `.env` at the repo root** — backends AND frontends. No per-product `.env` files.

Backend vars (typical):
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `JWT_SECRET`
- `RESEND_API_KEY`
- `CORS_ORIGINS` (comma-separated — include every product frontend port)

Frontend vars (VITE-prefixed):
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`
- `VITE_CORE_URL`
- `VITE_CORE_API_URL`

## Vite config factory

`createViteConfig()` sets `envDir` to the repo root so all frontends read from the same `.env`.

Product-specific vars (`VITE_BACKEND_API_URL`) are **injected by the factory** based on the port config — never hardcoded in `.env`.

```ts
// products/<name>/frontend/vite.config.ts
import { createViteConfig } from '@noctusai/seed/vite-config';
export default createViteConfig({ port: 8080 });  // 3 lines. That's it.
```

## Security: VITE_ prefix = public only

Vite embeds all `VITE_*` variables in the client JS bundle. They are **visible to any browser user**.

- ✅ `VITE_SUPABASE_URL` (public) — fine.
- ✅ `VITE_SUPABASE_PUBLISHABLE_KEY` (publishable / anon key) — fine.
- ❌ `VITE_STRIPE_SECRET_KEY` — **never**. This would leak the secret.
- ❌ `VITE_ANY_SECRET` — always wrong.

Secrets live in non-prefixed vars (backend-only).

## CORS_ORIGINS cascade

`CORS_ORIGINS` in root `.env` overrides each product's `ProductSettings.cors_origins` default (pydantic-settings precedence).

**Three resolution modes**, handled inside `BaseAppSettings.cors_origins_list`:

1. **Plain comma-separated** — `"http://localhost:5173,http://localhost:8080"`.
   Split on `,`, strip whitespace. Backward-compatible default.
2. **`"*"` wildcard** — returns `["*"]`. **Forbidden when `allow_credentials=True`** (MDN auth-replay anti-pattern). Seed `app_factory.py` enforces a guard at mount time.
3. **`"@registry:<mode>"` sentinel** — resolves at property-read time against the platform `start.sh PRODUCTS` registry (single source of truth for product → port mapping). See `noctusai_lib.config.cors_registry`.

   - `"@registry:all"` → every product frontend + localhost alts (`5173`, `3000`). SSO-bridge shape — use for products that accept inbound XHR from every frontend (currently CORE).
   - `"@registry:own:<slug>"` → that product's own frontend + localhost alts. Single-product shape.

**Why the sentinel exists.** When a new product joins `start.sh PRODUCTS`, the platform-wide CORS list MUST auto-grow. Hardcoded enumerations don't. The sentinel keeps the per-product code count for "what frontends exist" at **0**.

**When adding a new product**, no `.env` edit needed — just add the product to `start.sh PRODUCTS=(...)` between the `BEGIN_PRODUCTS_REGISTRY` / `END_PRODUCTS_REGISTRY` sentinels (`noctus.dev.scaffold_product` does this for you). Every consumer with `cors_origins = "@registry:all"` picks up the new frontend automatically.

**Manual override.** Setting `CORS_ORIGINS=...` in `.env` still wins (pydantic-settings precedence) — useful for one-off testing or pinning to a specific subset.

**Adopters:**
- `products/core/backend/app/config.py` → `cors_origins = "@registry:all"` (SSO-bridge).
- Other products still carry hardcoded enumerations — per-product migration deferred until the seam is exercised on N=2 consumers. File a follow-up project when surfacing.

Current ports (mirroring `start.sh` — re-derive rather than trust this line): 5173 (Core), 8080 (ERP), 8090 (PF), 8095 (Therapy), 8100 (Seed), 8110 (Daily Life), 8123 (Dev Team), 8130 (AdConnect), 8140 (Orbity), 8150 (Knowledge Extractor), 8160 (Social Wiring), 8170 (IgIg) — plus `3000` (Next/React default) as a universal localhost alt.

### CORS wildcard+credentials guard — auth-replay defense

`seed/lib/backend/noctusai_lib/api/app_factory.py::configure_app()` **refuses to boot** when `cors_origins='*'` AND `allow_credentials=True`. Browsers reflect ANY `Origin` header and forward credentials (cookies, `Authorization` header) when both flags are mounted — that combination lets any third-party site replay an authenticated user's tokens. **Refuse at boot, not at request time** (boot crash is loud; request-time misconfig is invisible until exploited).

Symptom at startup:
```
RuntimeError: CORS misconfiguration: cors_origins='*' is incompatible with
allow_credentials=True (auth-replay vulnerability). Enumerate cors_origins
explicitly. Product: <name>. Override for local dev only via
NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS=1.
```

**Fix the configuration, not the guard.** Enumerate the real origins in `CORS_ORIGINS` (e.g. `https://app.example.com,https://admin.example.com`). Public-read APIs that legitimately need `*` must pass `allow_credentials=False` to `configure_app(...)`.

**Escape hatch for local dev only**: `NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS=1` allows the combination AND emits a LOUD `WARNING` log on every boot. NEVER use in production. The override accepts `1` / `true` / `yes` (any case); any other value still blocks.

Legitimate combinations:
- enumerated origins + `allow_credentials=True` → production shape ✓
- `*` + `allow_credentials=False` → public-read API ✓
- enumerated origins + `allow_credentials=False` → public-read with explicit allowlist ✓
- `*` + `allow_credentials=True` → **refused at boot** ✗

Tests live in `seed/lib/backend/tests/api/test_cors_wildcard_credentials_guard.py`.

## Restart rules

- Backend code change → uvicorn `--reload` picks it up.
- **`.env` change** → uvicorn does NOT pick it up. Kill + restart the backend.
- Frontend code change → Vite HMR, no restart.
- `vite.config.ts` change → restart Vite.

---

See also:
- `../05-INFRASTRUCTURE.md` — ports, deployment, self-hosted services
