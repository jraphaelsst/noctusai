# YouTube Crawler

YouTube Data API v3 + Drive + WAHA + SMTP — quota-aware uploads with Fernet-encrypted refresh tokens. Scaffolded 2026-05-05 against the seed framework; domain implementation tracked in `projects/youtube-crawler-domain-implementation/` (see `MASTER-PROMPT.md`).

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8008)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8150)
- **Build**: `createViteConfig()` from seed framework (3-line vite.config.ts)
- **Database**: Supabase (schema: `youtube_crawler`)
- **Auth**: SSO + direct login

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8008 --app-dir products/youtube-crawler/backend

# Frontend
cd products/youtube-crawler/frontend && npm run dev

# Or, full stack (recommended): from repo root
./start.sh  # picks up youtube-crawler from the start.sh PRODUCTS registry
```

## Current state

Scaffolded against the seed framework. Backend has `0` routers / `0` services — only seed wiring (`create_product_app` + `create_database_module` + `create_dependencies` + `create_product_limiter`). Frontend ships seed pages (Dashboard, Equipe, Landing, Login, AcceptInvite, ForgotPassword, NotFound) with no domain UI yet. Migration `001_youtube_crawler.sql` provisions schema + `status_pagina` + `invitations` only.

Domain implementation (YouTube Data API integration, Drive uploads, WAHA notifications, SMTP digests, Fernet-encrypted refresh-token vault, quota-aware upload pipeline) is the next deliverable.

## Tests

```bash
cd products/youtube-crawler/backend && pytest  # 31 framework-suite tests inherited
cd products/youtube-crawler/frontend && npx vite build  # must build clean
```

Framework-test suites inherit from `noctusai_lib.testing` (`FrameworkEndpointsSuite` / `TeamFlowSuite` / `NotificationFlowSuite` / `AuthBoundarySuite` / `TeamRouter*Suite`). Domain tests will be added as routers/services land.
