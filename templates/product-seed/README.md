# NoctusAI Product Seed Template

Minimum viable product template with all shared configurations pre-wired.
Copy this directory to `products/<your-product>/` and customize.

## Quick Start

```bash
# 1. Copy the seed
cp -r templates/product-seed products/my-product

# 2. Find-and-replace placeholders
#    {{PRODUCT_NAME}}     → "My Product"
#    {{PRODUCT_SLUG}}     → "my-product"
#    {{SCHEMA_NAME}}      → "my_product"
#    {{BACKEND_PORT}}     → 8004
#    {{FRONTEND_PORT}}    → 8100
#    {{PRODUCT_ICON}}     → lucide icon component name

# 3. Backend setup
source venv/bin/activate
pip install -r products/my-product/backend/requirements.txt

# 4. Frontend setup
cd products/my-product/frontend
npm install

# 5. Create the database schema
# Run migrations/001_<schema>.sql in Supabase SQL Editor

# 6. Register the product in Core
# Add a row to the products table via admin panel or SQL

# 7. Add to start.sh
# Add uvicorn + npm run dev commands for the new product
```

## What's Included

### Backend (`backend/`)
- `app/main.py` — FastAPI entry point with shared app factory
- `app/config.py` — Pydantic Settings with root .env resolution
- `app/database.py` — Supabase client with schema targeting
- `app/dependencies.py` — Auth helpers (get_current_user, require role)
- `app/rate_limit.py` — Shared slowapi limiter
- `app/routers/health.py` — Health check endpoint
- `app/routers/notificacoes.py` — Notifications (proxies to core public.notifications)
- `tests/conftest.py` — MockSupabaseClient + AuthClient fixtures
- `requirements.txt` — Minimal deps for this product

### Frontend (`frontend/`)
- Vite + React + TypeScript + Tailwind (shared design system)
- Shared AppShell + Sidebar + Header from `@noctusai/shared/design-system`
- Shared useTheme hook for dark/light toggle
- Auth store from shared factory
- API client from shared factory
- NotificationBell from shared hooks
- Supabase client for auth only

### Shared Infrastructure (consumed, not duplicated)
- `shared/backend/noctusai_shared/` — exceptions, responses, middleware, logging, app factory
- `shared/frontend/src/` — API client, auth, stores, hooks, design system, components
- `tokens.css` — global design tokens
- `tailwind.config.base.ts` — global Tailwind theme
