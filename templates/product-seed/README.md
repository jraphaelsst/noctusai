# {{PRODUCT_NAME}}

Minimal viable product that serves as a reference implementation for the entire NoctusAI shared stack. Used as the source for the product template (`templates/product-seed/`).

## Stack

- **Backend**: FastAPI (port {{BACKEND_PORT}})
- **Frontend**: React + TypeScript + Vite (port {{FRONTEND_PORT}})
- **Database**: Supabase (schema: `seed`)
- **Tenant key**: `org_id`
- **Auth**: SSO + direct login

## Running

```bash
# Backend
uvicorn app.main:app --reload --port {{BACKEND_PORT}} --app-dir products/seed/backend

# Frontend
cd products/seed/frontend && npm run dev
```

## Key Features

- Proves shared backend library (`noctusai_shared`) integration
- Proves shared frontend library (`@noctusai/shared`) integration
- SSO authentication flow
- Role-based layout with AppShell, Sidebar, and Header
- Page status filtering
- Notification proxying
- Auto-synced to `templates/product-seed/` via post-commit hook
