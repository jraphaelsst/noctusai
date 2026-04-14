# ERP Imobiliario

Real estate CRM for managing clients, properties, sales funnels, and financials. Includes WhatsApp integration, digital signatures, and AI-powered property descriptions.

## Stack

- **Backend**: FastAPI (port 8001)
- **Frontend**: React + TypeScript + Vite (port 8080)
- **Database**: Supabase (schema: `erp`)
- **Tenant key**: `org_id`
- **Auth**: SSO + direct login

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8001 --app-dir products/erp-imobiliario/backend

# Frontend
cd products/erp-imobiliario/frontend && npm run dev
```

## Key Features

- Client management and segmentation
- Property listings with AI-generated descriptions
- Client-property matching engine
- Sales funnel tracking
- Financial management (commissions, invoices)
- WhatsApp messaging via WAHA
- Digital signature workflows
- Document management
- Team and role-based access control
