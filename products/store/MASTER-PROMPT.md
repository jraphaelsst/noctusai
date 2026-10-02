# Store — MASTER-PROMPT

> Authoritative development guide for the store product.

## Purpose

Sell digital products from a public sales page. v1 sells one kit, the
"Contrato Blindado de Compra e Venda" (3 contract templates, Word + PDF).
Buyers never log in; one owner administers the page at `/login` → `/admin`.

## Architecture

Seed single container. Backend `create_product_app("Store", "store", settings)`;
frontend `createProductApp()` with `publicRoutes` for `/` and `/obrigado`.

```
products/store/backend/app/
  routers/   public (settings, checkout, pedidos, download, autor/foto),
             admin (settings, upload, pedidos), webhooks (asaas)
  services/  settings (versioned ledger), checkout (seed hosted checkout),
             fulfillment (email + signed download), webhooks (seed inbox)
products/store/frontend/src/
  pages/     Landing (public), Obrigado (public), Login, AdminPagina, AdminVendas
```

### Database (schema `store`)

`landing_settings` (append-only versions), `pedidos`, `webhook_eventos`
(seed event inbox), `status_pagina`. RLS on everywhere, service-role access
from the backend only; no anon grants. Private bucket `store-produtos`.

## Domains

- **Settings** — defaults live only in the backend service; the anchor total
  is derived, never stored.
- **Checkout** — price is read server-side; the charge goes through
  `noctusai_lib.integrations.payments` (never a store-local Asaas client).
- **Fulfillment** — webhook-driven and idempotent (inbox claim + `email_enviado_em`).
- **Admin** — `require_store_admin` (`STORE_ADMIN_EMAILS`); public pages carry no login link.

## Rules

- Seed first: new IO goes into the seed organ with Fake + Real + factory.
- The contract (`projects/store-v1-CONTRACT.md`) is the FE ↔ BE source of truth;
  change it first, then both sides.
- Visual identity: `projects/landing-reference/` and the Store Visual Identity
  design system. Cream paper, navy ink, gold foil; Playfair Display + Montserrat.

## Testing

Backend: status-pinned router tests (auth `== 401`, admin 403), service tests
with the seed Fakes via DI. Frontend: vitest for public `/` (signed in and out),
checkout dialog states, admin 403 state. `predeploy_check product='store'`
must be `ready` before any deploy.
