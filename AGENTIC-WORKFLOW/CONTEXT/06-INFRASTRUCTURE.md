# 06 — Infrastructure Context

> Deployment: Local dev + VPS (Hostinger) for n8n/WAHA
> Containerization: Docker Compose for local dev

---

## Port Map

| Service | Port | URL |
|---------|------|-----|
| Core Backend | 8000 | `http://localhost:8000` |
| ERP Backend | 8001 | `http://localhost:8001` |
| Core Frontend | 5173 | `http://localhost:5173` |
| ERP Frontend | 8080 | `http://localhost:8080` |

---

## Local Development

### start.sh

Startup script that:
1. Creates root venv if not present
2. Installs Python dependencies from root `requirements.txt`
3. Starts Core Backend (uvicorn :8000)
4. Starts ERP Backend (uvicorn :8001)
5. Starts Core Frontend (vite :5173)
6. Starts ERP Frontend (vite :8080)

### Docker Compose (`docker-compose.yml`)

4 services for local containerized development:
- `core-backend` — FastAPI on :8000
- `erp-backend` — FastAPI on :8001
- `core-frontend` — Vite on :5173
- `erp-frontend` — Vite on :8080

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

---

## CORS

Each backend configures CORS for its respective frontend:

- Core Backend (`cors_origins`): `http://localhost:5173`
- ERP Backend (`cors_origins`): `http://localhost:8080`

Configurable via `CORS_ORIGINS` env var (comma-separated).

---

## External Service Dependencies

| Service | Used By | Purpose | Auth |
|---------|---------|---------|------|
| Supabase | Both backends | Database, auth, storage | `SUPABASE_URL` + keys |
| OpenAI | ERP backend | AI descriptions, embeddings, scoring | `OPENAI_API_KEY` |
| Stripe | Core backend | Billing, subscriptions | `STRIPE_SECRET_KEY` |
| WAHA | ERP backend | WhatsApp messaging | `WAHA_API_URL` + key |
| n8n | External | Workflow orchestration | Webhook URLs |
| Resend | Core backend | Email delivery | `RESEND_API_KEY` |
| Sentry | Optional | Error tracking | `SENTRY_DSN` |
| Redis | Optional | Caching | `REDIS_URL` |

---

## Python Virtual Environment

Single root-level `venv/` shared by all backends:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Root `requirements.txt` is the merged superset. Per-backend `requirements.txt` files exist for independent Docker deploys.
