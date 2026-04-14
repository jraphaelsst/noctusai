# Therapy Platform

Online therapy platform for clinics. Supports video sessions, scheduling, clinical AI assistance, patient management, and secure messaging.

## Stack

- **Backend**: FastAPI (port 8003)
- **Frontend**: React + TypeScript + Vite (port 8095)
- **Database**: Supabase (schema: `therapy`)
- **Tenant key**: `clinic_id`
- **Auth**: Direct Supabase Auth

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8003 --app-dir products/therapy-platform/backend

# Frontend
cd products/therapy-platform/frontend && npm run dev
```

## Key Features

- Video sessions via LiveKit
- Appointment scheduling and calendar management
- Patient management and clinical records
- Clinical AI assistance
- Wallet and payment handling
- Secure messaging between therapists and patients
- Team invitations with invite types and binding
- Role-based access for clinic staff
