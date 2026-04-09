# 06 — Infrastructure Context

> Deployment: Local dev + VPS (Hostinger) for n8n/WAHA
> Containerization: Docker Compose for local dev

---

## Port Map

| Service | Port | URL |
|---------|------|-----|
| Core Backend | 8000 | `http://localhost:8000` |
| ERP Backend | 8001 | `http://localhost:8001` |
| PF Backend | 8002 | `http://localhost:8002` |
| Core Frontend | 5173 | `http://localhost:5173` |
| ERP Frontend | 8080 | `http://localhost:8080` |
| PF Frontend | 8090 | `http://localhost:8090` |

---

## Local Development

### start.sh

Startup script that:
1. Creates root venv if not present
2. Installs Python dependencies from root `requirements.txt`
3. Starts Core Backend (uvicorn :8000)
4. Starts ERP Backend (uvicorn :8001)
5. Starts PF Backend (uvicorn :8002)
6. Starts Core Frontend (vite :5173)
7. Starts ERP Frontend (vite :8080)
8. Starts PF Frontend (vite :8090)

### Docker Compose (`docker-compose.yml`)

6 services for local containerized development:
- `core-backend` — FastAPI on :8000
- `erp-backend` — FastAPI on :8001
- `pf-backend` — FastAPI on :8002
- `core-frontend` — Vite on :5173
- `erp-frontend` — Vite on :8080
- `pf-frontend` — Vite on :8090

All services share the root `.env` file.

---

## VPS (Hostinger)

| Service | Domain | Purpose |
|---------|--------|---------|
| n8n | `n8n.noctusai.com` | Agentic workflow orchestration |
| WAHA | `waha.noctusai.com` | WhatsApp HTTP API |

- **Server**: `72.61.28.36`
- **Runtime**: Docker containers
- **SSL**: Let's Encrypt via reverse proxy

---

## Configuration Architecture

### Single Root `.env`

All backends read from one `.env` at repo root. Each backend's `config.py` resolves the path via:

```python
env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
```

Pydantic Settings silently ignores missing `.env`, so CI/Docker that inject env vars directly work without it.

### Frontend Env

Each frontend has its own `.env` with `VITE_`-prefixed vars (Vite convention — these end up in browser bundles):

- Core: `VITE_CORE_API_URL=http://localhost:8000`
- ERP: `VITE_BACKEND_API_URL=http://localhost:8001`
- PF: `VITE_BACKEND_API_URL=http://localhost:8002`

---

## CORS

Each backend configures CORS for its respective frontend:

- Core Backend (`cors_origins`): `http://localhost:5173`
- ERP Backend (`cors_origins`): `http://localhost:8080`

Configurable via `CORS_ORIGINS` env var (comma-separated).

---

## Supabase Schema Configuration

- **ERP backend** (`database.py`): `ClientOptions(schema="erp")` — all `.table()` and `.rpc()` calls target `erp` schema
- **ERP frontend** (`client.ts`): `db: { schema: 'erp' }` — all direct `.from()` calls target `erp` schema
- **PF backend** (`database.py`): `ClientOptions(schema="personal-finance")` — all calls target `personal-finance` schema
- **PF frontend** (`client.ts`): `db: { schema: 'personal-finance' }` — all calls target `personal-finance` schema
- **Core backend**: defaults to `public` schema
- **Supabase Dashboard**: `erp` and `personal-finance` must be in "Exposed schemas" (Project Settings → API) for PostgREST to accept the schema headers

---

## External Service Dependencies

| Service | Used By | Purpose | Auth |
|---------|---------|---------|------|
| Supabase | All backends | Database, auth, storage | `SUPABASE_URL` + keys |
| OpenAI | ERP backend | AI descriptions, embeddings, scoring | `OPENAI_API_KEY` |
| Stripe | Core backend | Billing, subscriptions | `STRIPE_SECRET_KEY` |
| WAHA | ERP backend | WhatsApp messaging (self-hosted) | `WAHA_API_URL` + key |
| Meta Business API | ERP backend | WhatsApp Cloud API messaging | `WHATSAPP_API_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` |
| Meta Graph API | ERP backend | Facebook Lead Ads + campaign sync | Stored in `erp.meta_config` per org |
| Resend | Both backends | Email delivery | `RESEND_API_KEY` (org_settings → env fallback) |
| ClickSign | ERP backend | Digital signatures | `CLICKSIGN_API_TOKEN` (org_settings → env) |
| DocuSign | ERP backend | Digital signatures | `DOCUSIGN_INTEGRATION_KEY` + `DOCUSIGN_ACCOUNT_ID` |
| D4Sign | ERP backend | Digital signatures | `D4SIGN_API_TOKEN` + `D4SIGN_CRYPT_KEY` |
| n8n | External | Workflow orchestration | Webhook URLs |
| Sentry | Optional | Error tracking | `SENTRY_DSN` |
| Redis | Optional | Caching, job queue (production) | `REDIS_URL` |

All external integrations follow a **dry-run pattern**: when credentials are not configured, services log actions and return mock responses. This allows development without real API keys.

**Credential resolution chain**: `org_settings` table → `platform_settings` table → environment variables. The settings router exposes `GET /api/settings/resolve/{key}` which follows this chain.

---

## Python Virtual Environment

Single root-level `venv/` shared by all backends:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Root `requirements.txt` is the merged superset. Per-backend `requirements.txt` files exist for independent Docker deploys.
