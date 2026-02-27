# 06 — Tech Stack: Mandatory Technologies & Conventions

> **Opinionated by design. Every choice is deliberate and serves the CDD+TDD methodology.**

---

## Stack Overview

| Layer | Technology | Role |
|---|---|---|
| **Orchestration** | n8n (self-hosted) | Agentic workflow engine, MCP client/server |
| **LLM** | Claude / GPT (configurable) | Agent brain, reasoning, tool selection |
| **Frontend** | React 18 + TypeScript + Vite | Web application UI |
| **Styling** | Tailwind CSS + shadcn/ui | Utility-first styling, component library |
| **Routing** | React Router v6 | Client-side routing |
| **Server State** | TanStack Query (React Query) | Data fetching, caching, sync (ERP) |
| **Client State** | Zustand | Global UI state (ERP); React Context (Core) |
| **Backend** | Python 3.11+ / FastAPI | REST API, async-first |
| **Database** | Supabase (PostgreSQL + RLS) | Primary datastore, auth, storage, client SDK |
| **Migrations** | Raw SQL files | Database schema versioning via `migrations/` |
| **Messaging** | WAHA (WhatsApp HTTP API) | WhatsApp integration |
| **Backend Tests** | pytest + httpx | API and service testing |
| **Frontend Tests** | Vitest + React Testing Library | Component and integration testing |
| **E2E Tests** | Playwright | Critical user flow testing |
| **Agent Evals** | Custom harness (Python) | Skill and agent behavior validation |
| **Deployment** | Docker / VPS (Hostinger) | Application hosting |

---

## Orchestration Layer: n8n

n8n is the core orchestration engine for all agentic workflows.

**Instance:** Self-hosted on VPS (Hostinger) at `n8n.noctusai.com`

**Key nodes for agentic workflows:**
- **AI Agent Node** — The central hub connecting LLM + Memory + Tools
- **MCP Client Tool** — Consumes tools from external MCP Servers
- **MCP Trigger** — Exposes n8n workflows as MCP Servers
- **Chat Trigger** — Entry point for conversational workflows
- **Webhook / Webhook Response** — HTTP-based triggers for external integrations
- **Code Node (JavaScript/Python)** — Custom logic when needed
- **IF / Switch / Router** — Conditional flow control
- **Wait / Retry** — Async handling and rate-limit management

**Memory options:**
- Window Buffer Memory — Simple last-N messages (good for short sessions)
- Postgres Chat Memory — Persistent memory backed by Supabase (good for long sessions)
- Custom memory via Code node — Full control over what's remembered

---

## Frontend

**React 18 + TypeScript + Vite**

- Functional components with hooks only — no class components
- Strict TypeScript configuration
- Vite for fast dev server and optimized builds

**Tailwind CSS + shadcn/ui**

- Utility-first styling, no inline styles
- shadcn/ui for pre-built accessible components
- Mobile-first responsive design with Tailwind breakpoints

**React Router v6** for client-side routing

**TanStack Query** for server state management (ERP product)

**Zustand** for global UI state (ERP product); React Context for auth (both products)

---

## Backend

**Python 3.11+ with FastAPI**

- Async-first design using `async def` endpoints
- Pydantic v2 for request/response validation (standalone schemas, not SQLModel)
- RESTful API with `/api/` prefix convention
- Uvicorn as ASGI server
- Environment variables via `.env` at repo root (never hardcode)
- CORS middleware configured for frontend origin

**Supabase client** for database access

- `get_user_client(token)` — RLS-respecting client (uses user's JWT)
- `get_admin_client()` — Service role client (bypasses RLS, for admin operations)
- Pydantic schemas in `schemas/` for request/response validation
- Raw SQL migrations in `migrations/` per backend

**Supabase** (managed PostgreSQL)

- Connection via `SUPABASE_URL` + `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`
- Supabase Auth for user management, JWT token issuance
- Row Level Security enforced on all tenant-scoped tables via `org_id`
- PostgREST-style query builder (`.select()`, `.eq()`, `.range()`, etc.)

---

## Messaging Layer: WAHA

**WAHA (WhatsApp HTTP API)** at `waha.noctusai.com`

- HTTP-based API for sending/receiving WhatsApp messages
- Webhook-based message delivery to n8n
- Session management for multi-device support
- JID formatting: `{phone}@s.whatsapp.net` for individuals

---

## Project Structure

```
project-root/
├── core/                        # NoctusAI Platform (auth, orgs, billing, SSO)
│   ├── backend/app/             # FastAPI :8000
│   │   ├── routers/             # 20 routers (auth, orgs, billing, sso, etc.)
│   │   ├── services/            # 8 services (billing, email, permissions, etc.)
│   │   ├── dependencies.py      # Auth helpers (get_current_user, get_current_admin)
│   │   ├── database.py          # Supabase client (admin + user)
│   │   └── config.py            # Pydantic Settings from root .env
│   ├── backend/tests/           # 23 test files
│   └── frontend/src/            # React :5173 (admin panel, billing, team)
│
├── products/
│   └── erp-imobiliario/         # Real Estate CRM product
│       ├── backend/app/         # FastAPI :8001
│       │   ├── routers/         # 39 routers (ativos, clientes, matching, AI, etc.)
│       │   ├── services/        # 30 services (matching, embedding, AI, etc.)
│       │   └── schemas/         # Pydantic request/response models
│       ├── backend/tests/       # 56 test files
│       └── frontend/src/        # React :8080 (45 pages, 55 hooks, shadcn/ui)
│
├── AGENTIC-WORKFLOW/            # CDD+TDD methodology & agentic artifacts
│   ├── INSTRUCTIONS/            # Methodology documentation (00-07)
│   │   ├── 00-MASTER.md         # Core principles and architecture
│   │   ├── 01-SKILLS.md         # Composable units of agent expertise
│   │   ├── 02-MCP.md            # MCP integration patterns
│   │   ├── 03-AGENTIC-WORKFLOWS.md  # Orchestration & design patterns
│   │   ├── 04-DESIGN-PHASES.md  # 7-phase design process
│   │   ├── 05-TESTING-EVALS.md  # Agentic testing strategy
│   │   ├── 06-TECH-STACK.md     # Tech stack & conventions (this file)
│   │   └── 07-TEMPLATES.md      # Reusable starting point templates
│   ├── CONTEXT/                 # System landscape docs for agent context loading
│   │   ├── 00-LANDSCAPE.md      # Platform overview, products, architecture
│   │   ├── 01-CORE-BACKEND.md   # Core backend: 20 routers, 8 services
│   │   ├── 02-ERP-BACKEND.md    # ERP backend: 39 routers, 30 services
│   │   ├── 03-ERP-FRONTEND.md   # ERP frontend: 45 pages, 55 hooks
│   │   ├── 04-CORE-FRONTEND.md  # Core frontend: admin, billing, auth
│   │   ├── 05-DATABASE.md       # Supabase tables, RLS, key relationships
│   │   ├── 06-INFRASTRUCTURE.md # Ports, Docker, n8n, WAHA, deployment
│   │   └── 07-AI-FEATURES.md    # AI service, embeddings, matching algorithm
│   ├── SKILLS/                  # Agent skill definitions (reference 01-SKILLS.md)
│   │   ├── property-description/SKILL.md
│   │   ├── lead-scoring/SKILL.md
│   │   ├── price-suggestion/SKILL.md
│   │   ├── ativo-matching/SKILL.md
│   │   ├── ativo-embedding/SKILL.md
│   │   └── whatsapp-messaging/SKILL.md
│   ├── EVALS/                   # Agent evaluation tests (reference 05-TESTING-EVALS.md)
│   │   ├── cases/               # Test case definitions (YAML)
│   │   ├── runners/             # Eval execution scripts
│   │   ├── reports/             # Results and regression tracking
│   │   └── config.yaml          # Runner configuration
│   ├── MCP-SERVERS/             # MCP Server definitions (reference 02-MCP.md)
│   └── WORKFLOWS/               # n8n workflow exports (reference 03-AGENTIC-WORKFLOWS.md)
│
├── docker-compose.yml           # Local dev: 4 services
├── start.sh                     # Local dev startup script
├── requirements.txt             # Root Python deps (merged superset)
├── venv/                        # Shared Python virtual environment
├── .env                         # Root environment variables
└── CLAUDE.md                    # AI coding assistant instructions
```

---

## Environment Variables

All sensitive data via environment variables. Never hardcode. Single root `.env` file shared by all backends.

```bash
# Supabase
SUPABASE_URL=https://project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
JWT_SECRET=your-jwt-secret

# App
CORS_ORIGINS=http://localhost:5173,http://localhost:8080
DEBUG=true
CORE_API_URL=http://localhost:8001

# Billing (Stripe)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# LLM (optional — ERP AI features)
OPENAI_API_KEY=sk-...

# Email (optional)
RESEND_API_KEY=...

# Observability (optional)
SENTRY_DSN=...
REDIS_URL=...
```

Frontend uses `VITE_`-prefixed vars in per-frontend `.env` files (security boundary — these end up in browser bundles):
- Core: `VITE_CORE_API_URL=http://localhost:8000`
- ERP: `VITE_BACKEND_API_URL=http://localhost:8001`

---

## Deployment

### Local Development
- `bash start.sh` — Creates venv, installs deps, starts all 4 services
- `docker-compose up` — Containerized local dev (4 services)
- Core Backend: `uvicorn app.main:app --reload --port 8000 --app-dir core/backend`
- ERP Backend: `uvicorn app.main:app --reload --port 8001 --app-dir products/erp-imobiliario/backend`

### VPS — Hostinger (n8n + WAHA)
- Server: `72.61.28.36`
- n8n: `n8n.noctusai.com` (Docker)
- WAHA: `waha.noctusai.com` (Docker)
- SSL: Let's Encrypt via reverse proxy

---

## Package Managers

- **Python:** pip with `requirements.txt`
- **Frontend:** npm (not yarn or pnpm)
- **n8n community nodes:** npm (installed within n8n container)
