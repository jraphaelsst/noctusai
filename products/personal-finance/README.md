# Personal Finance

Finance tracker for managing accounts, transactions, budgets, investment portfolios, and generating financial reports.

## Stack

- **Backend**: FastAPI (port 8002)
- **Frontend**: React + TypeScript + Vite (port 8090)
- **Database**: Supabase (schema: `personal-finance`)
- **Tenant key**: `org_id`
- **Auth**: SSO + direct login

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8002 --app-dir products/personal-finance/backend

# Frontend
cd products/personal-finance/frontend && npm run dev
```

## Key Features

- Bank account and credit card management
- Transaction tracking and categorization
- Budget creation and monitoring
- Investment portfolio tracking
- Asset watchlists
- Financial reports and analytics
