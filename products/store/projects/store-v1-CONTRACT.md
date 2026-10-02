# store v1 — contract (FE ↔ BE ↔ seed)

Owner decisions (2026-10-02): domain `store.noctusai.com` (own domain later) ·
delivery = email + thank-you page · admin = only the owner · price R$ 47 for now.

Product: one digital kit, "Contrato Blindado de Compra e Venda" (3 contracts,
Word + PDF — source files in `projects/store/contrato/`). Landing design: the
published artifact (scratch `lp/index.html`), ported 1:1 into React.

## 0. Seed addition (separate slice, `integrations.payments`)

The seed only does subscriptions. v1 needs a **one-off** charge, and p-studio
already carries a product-local one (`products/p-studio/backend/app/providers/asaas.py`
`criar_cobranca`) — N=2, so it is lifted into the seed, Fake + Real + factory:

- `CheckoutRequest` gains one-off support: `billing_cycle=None` ⇒ a single
  charge (no subscription). `billing_method` gains `"undefined"` (Asaas
  `billingType=UNDEFINED`: buyer picks PIX / boleto / card on Asaas' page).
- `AsaasHostedCheckout` one-off path: ensure_customer (with `cpfCnpj`) →
  `POST /payments` {customer, billingType, value, dueDate=today+N,
  description, externalReference, callback:{successUrl, autoRedirect:true}}
  → `CheckoutSession(checkout_url=invoiceUrl, gateway_charge_id=<payment id>)`.
- `StripeHostedCheckout` one-off path: Checkout Session `mode="payment"`.
- `FakeHostedCheckout`: deterministic fake URL + id.
- Webhook parsing is unchanged: `PAYMENT_RECEIVED` / `PAYMENT_CONFIRMED` →
  `charge_paid`, `externalReference` → `GatewayEvent.external_reference`.

store consumes ONLY `make_hosted_checkout(...)`, `parse_webhook_event(...)`,
`make_event_inbox(...)` — never calls Asaas directly.

## 1. Data (schema `store`, RLS on, `service_role_bypass` only, no anon grant)

- `store.landing_settings` — append-only versioned ledger (shape of core
  `052_website.sql` `website_settings`): `version int PK`, `data jsonb`,
  `created_by uuid`, `created_at`. Current = max(version).
- `store.pedidos` — `id uuid PK`, `token text unique` (32-byte urlsafe; the
  buyer's only handle), `nome`, `email`, `cpf` (digits), `valor_cents int`,
  `produto text`, `status text check in ('pendente','pago','reembolsado','falhou')`,
  `gateway text`, `gateway_charge_id text`, `checkout_url text`, `pago_em`,
  `email_enviado_em`, `downloads int default 0`, `created_at`, `updated_at`.
- `store.webhook_eventos` — the seed event-inbox table
  (`gateway text, event_id text, claimed_at timestamptz default now(), PK(gateway,event_id)`).
- `status_pagina` rows (`producao`) for `/admin` and `/admin/vendas`.
- Private storage bucket `store-produtos`: `contrato-blindado/kit.zip`,
  `autor/foto.<ext>`. Never public — served through the backend.

## 2. Settings shape (defaults = what the published page shows today)

```json
{
  "product_name": "Contrato Blindado de Compra e Venda",
  "price_cents": 4700,
  "items": [
    {"label": "Contrato À Vista (Word + PDF)", "anchor_cents": 9700},
    {"label": "Contrato Financiado (Word + PDF)", "anchor_cents": 9700},
    {"label": "Contrato Parcelado com confissão de dívida", "anchor_cents": 12700},
    {"label": "Lista de 14 certidões e documentos", "anchor_cents": 4700}
  ],
  "guarantee_days": 7,
  "author": {
    "name": "Gilson",
    "role": "corretor de imóveis",
    "bio": "O Gilson acompanha negociações de compra e venda do sinal à entrega das chaves. Este modelo nasceu dos contratos assinados nessas negociações, reunidos em um só texto e transformados em um modelo genérico que qualquer pessoa pode preencher.",
    "has_photo": false
  },
  "checkout_enabled": true
}
```

Anchor total is DERIVED (Σ anchor_cents), never stored. Defaults live in ONE
place: the backend service (`DEFAULT_SETTINGS`); version 1 is seeded by the
migration from the same values. Validation: price_cents 100..1_000_000,
1–8 items, guarantee_days 0..30, bio ≤ 600 chars.

## 3. API

Public (no auth dependency, rate-limited per IP, `client_ip_key`):

| Method | Path | Body / result |
|---|---|---|
| GET | `/api/public/settings` | settings above + `anchor_total_cents` + `author.photo_url` (`/api/public/autor/foto` or null) |
| GET | `/api/public/autor/foto` | 302 → short-lived signed URL, 404 if none |
| POST | `/api/public/checkout` | `{nome, email, cpf}` → 201 `{checkout_url, pedido_token}`. 503 when Asaas is not configured (unless `PAYMENTS_ALLOW_FAKE`). 409 when `checkout_enabled=false`. 422 invalid CPF/email. Price is read server-side, never from the client. `success_url = {STORE_PUBLIC_URL}/obrigado?pedido={token}` |
| GET | `/api/public/pedidos/{token}` | `{status, produto, email_mascarado, download_url|null}` — download_url only when `pago` |
| GET | `/api/public/download/{token}` | paid + within 30 days + downloads < 20 → increment, 302 to a 5-min signed URL of the kit; else 410/404 |
| POST | `/api/webhooks/asaas` | seed `parse_webhook_event` (`asaas-access-token` = `ASAAS_WEBHOOK_TOKEN`); bad token 401; inbox-dedup; `charge_paid` → pedido `pago` + send email once (idempotent on `email_enviado_em`); `charge_refunded` → `reembolsado` (download stops). Always 200 for ignored events |

Admin (auth + `require_store_admin`: signed-in user's email ∈ `STORE_ADMIN_EMAILS`; else 403):

| Method | Path | |
|---|---|---|
| GET/PUT | `/api/admin/settings` | PUT `{data, expected_version}` → new version; 409 on stale version |
| POST | `/api/admin/autor/foto` | multipart image ≤ 5 MB |
| POST | `/api/admin/produto/arquivo` | multipart zip ≤ 50 MB → replaces the kit |
| GET | `/api/admin/produto/arquivo` | `{exists, size, updated_at}` |
| GET | `/api/admin/pedidos` | list, newest first, filter `status` |
| POST | `/api/admin/pedidos/{id}/reenviar` | re-send the delivery email |

Email (seed `make_email_sender`): subject "Seu {product_name} chegou", body with
the download link `{STORE_PUBLIC_URL}/api/public/download/{token}` and the
30-day / 20-download terms. Plain + HTML.

Env: `ASAAS_API_KEY`, `ASAAS_BASE_URL` (sandbox default
`https://api-sandbox.asaas.com/v3`), `ASAAS_WEBHOOK_TOKEN`,
`PAYMENTS_ALLOW_FAKE`, `STORE_PUBLIC_URL`, `STORE_ADMIN_EMAILS`, SMTP vars of
the seed email sender. All in `.env.example` with placeholders.

## 4. Frontend

- `publicRoutes`: `/` Landing (no login link anywhere), `/obrigado`
  (polls `/api/public/pedidos/{token}` every 3 s up to 2 min: pendente →
  "Aguardando confirmação do pagamento", pago → download button + "enviamos
  para j***@gmail.com").
- Landing: port of the artifact, scoped CSS, images in `src/assets/landing/`,
  Google Fonts via `@import` in the scoped CSS, OG meta in `index.html`.
  Dynamic fields from `/api/public/settings`: product name, price, item list
  + anchors + total, guarantee days, author name/role/bio/photo. Every CTA
  opens a checkout dialog (nome, e-mail, CPF with mask) → POST checkout →
  `window.location.assign(checkout_url)`. Loading: two-signal rule
  (`showSkeleton = isPending && !data`) on the dynamic spans only.
- `/login` (seed-mounted, product `Login`) → `/admin`.
- `routes` (Layout, nav): `/admin` "Página de vendas" (form for every
  settings field, photo upload, kit upload status/upload, Salvar →
  PUT with expected_version, 409 → reload prompt) and `/admin/vendas`
  "Vendas" (orders table + reenviar). Non-admin signed-in user → seed
  forbidden/empty state, never the form.
