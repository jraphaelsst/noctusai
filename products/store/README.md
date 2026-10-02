# Store

Public sales pages for digital products. The first product is the
"Contrato Blindado de Compra e Venda" kit: three generic contract templates
(à vista, financiado, parcelado com confissão de dívida) in Word + PDF,
generated from social-wiring's contract generator with no client data
(`projects/store/contrato/`).

## How it works

1. A visitor opens `/` (public, no login link) and clicks a CTA.
2. A short form (nome, e-mail, CPF) creates an order and an Asaas one-off
   charge through the seed payments organ; the buyer pays on Asaas' page.
3. Asaas calls `POST /api/webhooks/asaas`; the order becomes `pago` and the
   buyer gets an email with a private download link (30 days, 20 downloads).
4. Asaas redirects to `/obrigado?pedido=<token>`, which shows the same link
   once the payment is confirmed.
5. The owner signs in at `/login` (no button anywhere; type the URL) and edits
   the page's values at `/admin` and sees sales at `/admin/vendas`.

## Stack and ports

Seed single container: FastAPI (`create_product_app`) + React SPA
(`createProductApp`). Backend 8018, frontend dev 8220, schema `store`.

## Configuration

Keys are **stored in the DB, not env**. The owner writes the Asaas API key, the
webhook token and the environment (sandbox | production, default sandbox) in the
admin UI (`/api/settings/api-keys`, seed router); they are Fernet-encrypted in
`store.credentials` and read via `resolve_api_key` (local store -> platform chain
-> env fallback). Values are never returned, only a masked hint + source. SMTP
for the delivery email comes from the platform chain (`smtp_*`, `email_from`).

Env that remains (see `backend/.env.example`): `ENCRYPTION_KEY` (unset => key
writes 503), `STORE_ORG_ID` (the owner's org), `STORE_PUBLIC_URL`,
`STORE_ADMIN_EMAILS`, `PAYMENTS_ALLOW_FAKE` (dev only). Without an Asaas key the
checkout answers 503.

## Docs

- Contract: `projects/store-v1-CONTRACT.md`
- Approved landing design: `projects/landing-reference/`
- Roadmap: `project-history/roadmaps/store-launch-2026-10.md`
