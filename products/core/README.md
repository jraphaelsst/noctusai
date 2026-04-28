# Core Platform

Central platform for authentication, organization management, billing, licensing, and SSO. Serves as the admin dashboard and gateway to all NoctusAI products.

## Stack

- **Backend**: FastAPI (port 8000)
- **Frontend**: React + TypeScript + Vite (port 5173)
- **Database**: Supabase (schema: `public`)
- **Tenant key**: `org_id`
- **Auth**: Custom REST API

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8000 --app-dir products/core/backend

# Frontend
cd products/core/frontend && npm run dev
```

## Key Features

- Organization creation and management
- User authentication and session handling
- SSO token exchange for product access
- Stripe billing and subscription management
- Product licensing and provisioning
- Admin dashboard with platform-wide controls
- 7-role hierarchy (owner, admin, manager, member, viewer, dev, test)
- Team invitations and role assignment
- Notification system (platform-wide)
