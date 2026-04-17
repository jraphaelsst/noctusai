# AdConnect — Product Description & Implementation Checklist

## What AdConnect Is

AdConnect is a **B2B marketplace platform** that connects brands/manufacturers with their distributor network. It is NOT a consumer-facing product — it serves business-to-business commercial relationships.

The platform enables brands to manage their distributor channels: product catalog distribution, order management (integrated with Omie ERP), a loyalty/rewards program (cashback + marketing budget incentives), sellout compliance tracking, and financial operations (invoices, credit limits).

## User Roles

### Customer (Distributor)
A company that buys products in bulk from the brand. Distributors:
- Browse the B2B product catalog and place bulk orders (enforcing pack multiples and minimum quantities)
- Earn cashback and marketing budget on purchases based on their tier level
- Upload monthly sellout reports to prove they actually sold the products (compliance requirement)
- Track invoices (NF-e), credit limits, and overdue balances
- Manage their economic group (multiple CNPJs per distributor company)
- Progress through loyalty tiers (Starter → Insider → Master → Smarter) based on annual purchase volume

### Admin (Brand/Platform Operator)
Manages the platform on behalf of the brand:
- Configures reward rules (cashback percentages per product category per tier)
- Creates promotional campaigns (date-ranged bonus multipliers)
- Monitors distributor sellout compliance across the network
- Views platform-wide metrics (GMV, active distributors, compliance rates)
- Manages distributor registrations and economic groups

## Core Domain Logic

### Cart & Quote System
B2B-specific ordering, not consumer e-commerce:
- Products have **pack multiples** (e.g., ships in boxes of 12 — can't order 5)
- Products have **minimum order quantities** (e.g., minimum 2 boxes)
- Quote calculation applies: base price × quantity + cashback earned + marketing budget applied
- Distributors can choose to apply accumulated cashback or marketing budget to discount the order

### Rewards & Tier Program
Loyalty program with 4 tiers based on annual purchase volume:
- **Starter** (R$0 – R$500k) → base cashback rates
- **Insider** (R$500k – R$1M) → improved rates
- **Master** (R$1M – R$2M) → premium rates
- **Smarter** (R$2M+) → best rates
- Each purchase earns cashback (percentage varies by product category AND distributor tier)
- Distributors also earn **marketing budget** (verba MKT) — a separate balance for co-marketing
- Both balances can be redeemed on future orders as discounts

### Sellout Compliance
Brands need to verify that distributors actually sell-through the products (not just hoard inventory):
- Distributors upload monthly sellout reports (CSV/Excel)
- System tracks compliance status per distributor per period
- Non-compliant distributors may lose tier benefits or promotions

### Financial Operations
Brazilian B2B financial tracking:
- NF-e (Nota Fiscal Eletrônica) — invoice records per distributor
- Credit limit management — each distributor has a purchase limit
- Overdue balance tracking — alerts for unpaid invoices

### Omie ERP Integration
Orders sync to Omie (popular Brazilian ERP):
- Currently **stubbed** — `omie.ts` generates mock IDs (`OMI-MOCK-*`)
- When `OMIE_APP_KEY` + `OMIE_APP_SECRET` are set in `.env`, the real HTTP integration activates
- The service layer is designed for this swap (same function signatures)

## Current State (pre-migration)

The adconnect code lives at `adconnect/` as a standalone FastAPI + React app:
- **Backend**: FastAPI with 9 routers, 2 services, in-memory data store (JSON seed files). Custom JWT auth (NOT Supabase).
- **Frontend**: React + Vite + shadcn/ui. Most pages use hardcoded mock data. `api.ts` and `api-endpoints.ts` exist but pages haven't been migrated to use them with TanStack Query yet.
- **Database**: None — everything is in-memory. The data model is ready for Supabase migration (store.ts designed for swap).
- **Auth**: Custom JWT — AdConnect has its own user base (distributors + admins), NOT NoctusAI platform users. This is different from other products which use Supabase SSO.

## Migration Notes for Future Agents

### Auth Architecture Decision
AdConnect has its **own auth system** — distributors log in with email/password and get a JWT. This is fundamentally different from other NoctusAI products (ERP, PF, Therapy) which use Supabase Auth + SSO from Core.

**Options (to be decided by the user):**
1. **Keep AdConnect's own auth** — AdConnect users are separate from NoctusAI users. The seed framework's standard team/notification routers won't apply to AdConnect's domain users. The framework still provides health check, CORS, middleware, rate limiting.
2. **Migrate to Supabase Auth** — AdConnect users become Supabase auth users. Enables SSO from Core. But requires rethinking the distributor registration flow.

Until decided, the migration should preserve the existing auth and keep it working. The framework's `create_product_app()` provides standard routers (health, team, notificacoes) which use Supabase auth — these coexist alongside AdConnect's custom auth routers without conflict.

### In-Memory to Supabase Migration
The backend currently uses `store.py` (in-memory dict-based storage loaded from JSON). The migration to Supabase involves:
1. Create the `adconnect` schema with proper tables (see section 3)
2. Replace `store.products`, `store.users`, etc. with Supabase queries
3. The service layer signatures stay the same — only the data access changes

This can be done incrementally: start with the in-memory store working inside the seed framework, then swap to Supabase table by table.

### Frontend Approach
The existing frontend has its own component library (shadcn/ui) and layouts (CustomerLayout, AdminLayout). Two approaches:
1. **Use seed framework layouts** — `createProductApp()` with `roleRoutes` (customer vs admin), `createProductLayout()` for sidebar/header. Rewrite pages to use seed design system.
2. **Keep existing layouts** — The existing CustomerLayout/AdminLayout work. Wrap them in the seed framework's App structure for auth/routing but keep the domain-specific layouts. This is faster but means AdConnect's UI doesn't look like other NoctusAI products.

Recommendation: **Option 2 for speed** — keep the existing layouts, wire them into `createProductApp()` with `roleRoutes`. The UI can be unified later.

### Suggested Improvements (for implementation)
1. **Extract cart service logic to proper service files** — current cart.py mixes HTTP and business logic
2. **Add proper error handling** — current routers return raw HTTPException without consistent response shapes
3. **Add pagination** — product catalog and order lists don't paginate
4. **Add order status workflow** — currently orders are just created, no status transitions
5. **Add sellout report validation** — current upload endpoint accepts any file, no validation
6. **Add credit limit enforcement** — financial.py exposes balance but cart doesn't check credit limit before allowing orders

---

## Product Registration

| Field | Value |
|-------|-------|
| Name | AdConnect |
| Slug | `adconnect` |
| Schema | `adconnect` |
| Backend port | 8007 |
| Frontend port | 8130 |
| Icon | `ShoppingCart` (lucide) |
| Color | `#f97316` (orange) |
| Auth | Custom JWT (own user base, NOT Supabase SSO) |

---

## Implementation Checklist

### 1. Scaffold & Registration

- [x] Scaffold from seed template (`products/adconnect/`)
- [ ] Update `products/adconnect/README.md` — describe what AdConnect does
- [ ] Update `products/adconnect/MASTER-PROMPT.md` — authoritative dev guide
- [ ] Add to `start.sh` (backend 8007, frontend 8130)
- [ ] Add to `CLAUDE.md` product table
- [ ] Add to `PRODUCT_MAP` in `seed/frontend/framework/vite.config.factory.ts`
- [ ] Insert into `public.products` table (Supabase)

### 2. Backend — Migrate Domain Code

#### Config & Infrastructure
- [ ] `app/config.py` — extend ProductSettings with AdConnect-specific fields (jwt_secret for AdConnect auth, jwt_expires_minutes, omie_app_key, omie_app_secret, omie_base_url)
- [ ] `app/main.py` — wire all 9 domain routers into create_product_app()
- [ ] `app/security.py` — copy AdConnect JWT auth functions (create_token, verify_password, hash_password)
- [ ] `app/data/` — copy in-memory data store + all seed JSON files

#### Domain Routers (9)
- [ ] `routers/auth.py` — login, register, GET /auth/me
- [ ] `routers/products.py` — GET /products, /products/:id, /products/categories
- [ ] `routers/cart.py` — POST /cart/quote
- [ ] `routers/orders.py` — POST /orders, GET /orders, GET /orders/:id
- [ ] `routers/rewards.py` — GET /rewards/balance, /history, /tier, POST /rewards/redeem
- [ ] `routers/sellout.py` — POST /sellout/upload, GET /sellout/reports, /summary
- [ ] `routers/financial.py` — GET /financial/invoices, /balance
- [ ] `routers/distributors.py` — GET /distributors/me, /:id/cnpjs, CRUD CNPJs
- [ ] `routers/admin.py` — /admin/reward-rules, /promos, /sellout/reports, /dashboard

#### Domain Services
- [ ] `services/cart.py` — find_product, calc_quote (cashback, marketing budget, min/multiples validation)
- [ ] `services/rewards.py` — resolve_tier, calc_balance, process_redemption

#### Schemas (Pydantic)
- [ ] `schemas/auth.py` — LoginInput, RegisterInput, UserResponse
- [ ] `schemas/cart.py` — CartItem, QuoteRequest, QuoteResponse
- [ ] `schemas/orders.py` — OrderCreate, OrderResponse, OrderItem
- [ ] `schemas/products.py` — Product, Category
- [ ] `schemas/rewards.py` — RewardBalance, TierInfo, RedemptionRequest

### 3. Database Migration (`001_adconnect.sql`)

- [ ] Create `adconnect` schema with grants and RLS
- [ ] `adconnect.status_pagina` + `adconnect.invitations` (standard platform tables)
- [ ] `adconnect.users` — id, email, password_hash, name, role (admin/customer), distributor_id, created_at
- [ ] `adconnect.distributors` — id, nome, cnpj_principal, tier, annual_revenue, created_at
- [ ] `adconnect.distributor_cnpjs` — id, distributor_id, cnpj, razao_social, ativo
- [ ] `adconnect.products` — id, nome, sku, descricao, preco, categoria_id, multiplo, minimo, ativo
- [ ] `adconnect.categories` — id, nome, slug, icone
- [ ] `adconnect.orders` — id, distributor_id, status, total, cashback_applied, verba_applied, omie_id, created_at
- [ ] `adconnect.order_items` — id, order_id, product_id, quantidade, preco_unitario, cashback_earned
- [ ] `adconnect.rewards_balance` — id, distributor_id, tipo (cashback/verba_mkt), saldo, updated_at
- [ ] `adconnect.rewards_history` — id, distributor_id, tipo, valor, operacao (earned/redeemed/expired), order_id, created_at
- [ ] `adconnect.reward_rules` — id, categoria_id, tier, percentual_cashback, percentual_verba, ativo
- [ ] `adconnect.promos` — id, nome, descricao, multiplicador, data_inicio, data_fim, ativo
- [ ] `adconnect.sellout_reports` — id, distributor_id, periodo, arquivo_url, status (pendente/aprovado/rejeitado), created_at
- [ ] `adconnect.invoices` — id, distributor_id, numero_nfe, valor, data_emissao, data_vencimento, status (aberta/paga/vencida)
- [ ] Seed data: categories, sample products, reward rules, tier config, demo users

### 4. Frontend — Infrastructure

- [ ] `src/App.tsx` — createProductApp() with roleRoutes (customer paths + admin paths)
- [ ] `vite.config.ts` — createViteConfig({ port: 8130 })
- [ ] `tailwind.config.ts` — extend seed base with AdConnect brand colors
- [ ] `tsconfig.json` — seed path aliases
- [ ] `contexts/CartContext.tsx` — keep (domain-specific cart state)

### 5. Frontend — Pages (17 pages, 2 roles)

#### Public (3)
- [ ] `pages/Landing.tsx` — B2B landing page
- [ ] `pages/Login.tsx` — AdConnect login (custom auth, NOT Supabase)
- [ ] `pages/Register.tsx` — distributor registration

#### Customer / Distributor (8)
- [ ] `pages/customer/Dashboard.tsx` — overview: recent orders, rewards summary, sellout status
- [ ] `pages/customer/Catalog.tsx` — product catalog with search, category filters, add to cart
- [ ] `pages/customer/Checkout.tsx` — cart review, apply cashback/marketing budget, place order
- [ ] `pages/customer/Orders.tsx` — order history with status tracking
- [ ] `pages/customer/Rewards.tsx` — cashback balance, tier progress bar, redemption history
- [ ] `pages/customer/Sellout.tsx` — upload monthly sellout, compliance status per period
- [ ] `pages/customer/Financial.tsx` — invoices, credit limit bar, overdue alerts
- [ ] `pages/customer/Settings.tsx` — profile, CNPJ management

#### Admin (4)
- [ ] `pages/admin/Dashboard.tsx` — GMV, active distributors, compliance rates, top distributors
- [ ] `pages/admin/Distributors.tsx` — distributor list, detail, CNPJ management
- [ ] `pages/admin/Rewards.tsx` — reward rules CRUD, promo campaigns, tier configuration
- [ ] `pages/admin/Settings.tsx` — platform settings

#### Shared (2)
- [ ] `pages/NotFound.tsx`
- [ ] `pages/Equipe.tsx` — team management (from seed framework)

### 6. Frontend — Hooks (dedicated files)

- [ ] `hooks/useAdConnectAuth.ts` — login, register, me, logout (custom JWT)
- [ ] `hooks/useProducts.ts` — catalog list, detail, categories, search
- [ ] `hooks/useCart.ts` — quote calculation, cart state management
- [ ] `hooks/useOrders.ts` — create, list, detail, status tracking
- [ ] `hooks/useRewards.ts` — balance, history, tier info, redeem
- [ ] `hooks/useSellout.ts` — upload report, list reports, summary, compliance status
- [ ] `hooks/useFinancial.ts` — invoices, credit limit, overdue balance
- [ ] `hooks/useDistributors.ts` — profile, CNPJs, economic group (admin)
- [ ] `hooks/useAdminDashboard.ts` — platform metrics, top distributors

### 7. Frontend — Components

- [ ] `components/CartDrawer.tsx` — slide-out cart with live quote calculation
- [ ] `components/ProductCard.tsx` — product card for catalog grid
- [ ] `components/OrderStatusBadge.tsx` — color-coded order status
- [ ] `components/TierProgress.tsx` — visual tier progress bar with milestones
- [ ] `components/SelloutUpload.tsx` — file upload with validation
- [ ] `components/CreditLimitBar.tsx` — visual credit usage bar

### 8. Tests

#### Backend
- [ ] `tests/conftest.py` — fixtures
- [ ] `tests/routers/test_auth.py` — login, register, me, invalid credentials
- [ ] `tests/routers/test_products.py` — catalog list, detail, categories, not found
- [ ] `tests/routers/test_cart.py` — valid quote, multiple validation, minimum validation, cashback calc
- [ ] `tests/routers/test_orders.py` — create, list, detail
- [ ] `tests/routers/test_rewards.py` — balance, tier, redeem, insufficient balance
- [ ] `tests/routers/test_admin.py` — reward rules CRUD, promos CRUD
- [ ] `tests/services/test_cart_service.py` — calc_quote edge cases (multiples, minimums, cashback math)
- [ ] `tests/services/test_rewards_service.py` — tier resolution boundaries, balance calculations
- [ ] `tests/integration/test_e2e_flows.py` — browse → add to cart → quote → place order → earn cashback
- [ ] `tests/integration/test_auth_boundary.py` — all protected endpoints return 401

#### Frontend
- [ ] All frontends build: `npx vite build`

### 9. Verification

- [ ] Backend starts: `uvicorn app.main:app --reload --port 8007`
- [ ] Frontend builds clean
- [ ] Frontend starts: `npm run dev` on port 8130
- [ ] All backend tests pass
- [ ] MCP validate: `python mcp/noctusai/cli.py --validate`
- [ ] MCP heal: `python mcp/noctusai/cli.py --heal --product adconnect`
- [ ] Both backend AND frontend at same maturity (no incomplete commits)
