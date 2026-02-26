# NoctusAI Platform — MVP Production Checklist

Status: All items implemented. Only manual configuration (Stripe keys, Resend API key) remains.

---

## CRITICAL — DONE

### 1. ~~Fix Supabase project mismatch~~ DONE

ERP frontend `.env` updated to use the same Supabase project as the backends (`nyplttplcoyiiqjrvtiw.supabase.co`).

**Files changed:** `products/erp-imobiliario/frontend/.env`

### 2. ~~Rotate JWT_SECRET~~ DONE

JWT_SECRET rotated to a secure 64-byte random value in root `.env`.

**Files changed:** `.env`

---

## HIGH PRIORITY — DONE

### 3. Configure Stripe keys — MANUAL STEP REQUIRED

The `.env` has empty Stripe fields. Code is ready, but you need to fill in real keys.

**What to do:**
- Create a Stripe account and get test keys from the Stripe Dashboard.
- Fill in the root `.env`:
  ```
  STRIPE_SECRET_KEY=sk_test_...
  STRIPE_PUBLISHABLE_KEY=pk_test_...
  STRIPE_WEBHOOK_SECRET=whsec_...
  ```
- Create Stripe Products + Prices matching the three plans (Free, Pro R$99/mo, Enterprise R$299/mo).
- Update the `plans` table seed data in `core/backend/migrations/001_noctusai_core.sql` with the real `stripe_price_id_monthly` and `stripe_price_id_yearly` values.
- Set up a Stripe webhook endpoint pointing to `https://<your-domain>/api/billing/webhook` for events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`.
- **Test:** Go to Pricing page, select a plan, complete checkout with Stripe test card `4242 4242 4242 4242`, verify subscription is created in the `subscriptions` table.

### 4. ~~Add Docker / deployment configuration~~ DONE

Created Dockerfiles for all 4 services, nginx configs for frontends, docker-compose.yml, and .dockerignore.

**Files created:**
- `core/backend/Dockerfile`
- `products/erp-imobiliario/backend/Dockerfile`
- `core/frontend/Dockerfile` + `core/frontend/nginx.conf`
- `products/erp-imobiliario/frontend/Dockerfile` + `products/erp-imobiliario/frontend/nginx.conf`
- `docker-compose.yml`
- `.dockerignore`

**Usage:** `docker-compose up --build`

---

## MEDIUM PRIORITY — DONE

### 5. ~~Implement email notifications~~ DONE

Email service created using Resend as provider. Gracefully degrades (logs only) if `RESEND_API_KEY` is not set.

**Files created:**
- `core/backend/app/services/email_service.py` — `send_invitation_email()`, `send_welcome_email()`, `send_billing_alert()`

**Files modified:**
- `core/backend/app/config.py` — Added `resend_api_key` setting
- `core/backend/app/routers/team.py` — Wired invitation emails into `POST /api/team/invite`
- `core/backend/app/routers/billing.py` — Wired billing alerts on `invoice.payment_failed`
- `.env` — Added `RESEND_API_KEY=` placeholder
- `requirements.txt` — Added `resend>=2.0.0`

**To activate:** Get an API key from [resend.com](https://resend.com) and set `RESEND_API_KEY` in `.env`.

### 6. ~~Backport ERP exception handling to Core backend~~ DONE

Copied the exception hierarchy and registered handlers in Core's main.py.

**Files created:**
- `core/backend/app/exceptions.py` — `AppException`, `NotFoundError`, `ValidationError_`, `UnauthorizedError`, `ForbiddenError`, `ConflictError`, `InternalError`

**Files modified:**
- `core/backend/app/main.py` — Registered all 4 exception handlers

---

## LOW PRIORITY — DONE

### 7. ~~Add user account settings page~~ DONE

Backend endpoint and frontend page created.

**Files created:**
- `core/frontend/src/pages/AccountSettings.tsx` — Profile editing (name, avatar URL)

**Files modified:**
- `core/backend/app/routers/auth.py` — Added `PATCH /api/auth/profile` endpoint
- `core/frontend/src/main.tsx` — Added `/settings` route

### 8. ~~Add rate limiting middleware~~ DONE

Added slowapi rate limiting to both backends.

**Files modified:**
- `core/backend/app/main.py` — Global 100 req/min limiter + 429 handler
- `core/backend/app/routers/auth.py` — Login/signup: 10 req/min per IP
- `products/erp-imobiliario/backend/app/main.py` — Global 100 req/min limiter + 429 handler
- `requirements.txt` — Added `slowapi>=0.1.9`

### 9. ~~Add CI/CD pipeline~~ DONE

GitHub Actions workflow created.

**Files created:**
- `.github/workflows/test.yml` — 3 jobs: ERP backend tests (pytest), ERP frontend build+lint, Core frontend build

Runs on push/PR to `main`.
