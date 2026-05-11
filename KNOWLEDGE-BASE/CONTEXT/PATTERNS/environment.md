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

**When adding a new product**, add its frontend port to `CORS_ORIGINS` in root `.env`. Otherwise, the product's frontend will hit CORS errors hitting its own backend.

Current ports: 5173 (Core), 8080 (ERP), 8090 (PF), 8095 (Therapy), 8100 (Seed), 8110 (Daily Life), 8120 (Mailing).

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
