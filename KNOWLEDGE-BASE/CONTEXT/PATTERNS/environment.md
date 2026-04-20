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

## Restart rules

- Backend code change → uvicorn `--reload` picks it up.
- **`.env` change** → uvicorn does NOT pick it up. Kill + restart the backend.
- Frontend code change → Vite HMR, no restart.
- `vite.config.ts` change → restart Vite.

---

See also:
- `../05-INFRASTRUCTURE.md` — ports, deployment, self-hosted services
