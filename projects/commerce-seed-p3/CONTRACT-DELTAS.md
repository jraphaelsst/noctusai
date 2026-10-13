# P3 contract deltas (agreed during the build — authoritative over CONTRACT.md where they differ)

Logged by the tech-lead from the slice returns, 2026-10-13. Fold into `CONTRACT.md` at phase close.

| # | Delta | Source | Backend action |
|---|---|---|---|
| 1 | Storefront product page component is `StorefrontProductPage` (alias `ProductPage` kept) — core's marketing site already declares `ProductPage` and the canonical-organ keeper keys on names | slice C | none |
| 2 | `createCommerceHooks(apiOrBase: string \| ApiClient)` — seed `ApiClient` for staff (auth), plain string for the public storefront; hooks unwrap `{data}` | slice C | none |
| 3 | `PUT /api/commerce/profile` with `expected_version: 0` = create when no profile exists | slice C | accept 0 as create (409 otherwise) |
| 4 | Lists read as `{data, pagination: {page, page_size, total, total_pages?}}` | slice C | emit `paginated_response` exactly; confirm field names |
| 5 | `QuoteLine = {offer_id, product_id, title, product_type, fulfillment_type, unit_price_cents, qty, total_cents}`; `CatalogItem = {id, slug, title, offers[], media_url}`; `PublicOrder` has no internal ids; `pix_qr = {payload?, encoded_image?, expires_at?}` | slice C | match shapes |
| 6 | Checkout shows address fields only when a quote line's `fulfillment_type` is `shipping` or `local_delivery` | slice C | `fulfillment_type` required on quote lines |
| 7 | `GET /api/commerce/customers/{id}/export` returns JSON `{data}` (offered as a download in the UI) | slice C | match |
| 8 | Media upload = multipart fields `file` + `alt` | slice C | match |
| 9 | No regenerate-payment endpoint in P3; the expired-order button is a `NOC-REMEDIATE[commerce-regenerate-payment]` placeholder → P4 (recovery funnel) | slice C | none in P3 |

## Slice A deltas (backend organ, on dev e0d18d4bd)

| # | Delta | Frontend / host action |
|---|---|---|
| A1 | Extra storefront routes for e-mailed links: `GET /api/storefront/my-orders?token=` → public orders list; `POST /api/storefront/privacy-requests/verify` `{token}` → `{status, kind}`. Links are HMAC-signed, bound to org + purpose (`get_link_secret`) | slice D pages call them (`/minhas-compras`, `/privacidade/verificar`) |
| A2 | Status codes: checkout + creates 201, deletes 204, access-link + privacy-requests 202 `{"data":{"accepted":true}}`; storefront 503 `pagamento_indisponivel`, 502 `pagamento_falhou`, 409 `loja_nao_configurada` | handle in hooks/pages |
| A3 | Error codes: `documento_invalido` · `oferta_indisponivel` · `cupom_invalido` (`details.reason`) · `total_zero` · `sem_oferta_ativa` · `slug_em_uso` · `transicao_invalida` · `link_invalido` · `midia_invalida` · `assinatura_invalida` (webhook 401); body `{"error":{"code","message","details"}}` | map in i18n messages |
| A4 | Unpaginated lists (`{data:[...]}`): categories, offers, coupons, hosts. Paginated: products, customers, orders, catalog — `pagination = {page, page_size, total, total_pages}` | confirm hooks |
| A5 | `CatalogItem` adds `description, product_type, fulfillment_type, category_id`; offers are `{id, name, price_cents, currency}`; `StorefrontProduct` = same + `media[{id,kind,alt,position,url}]` | superset of C's shape — compatible |
| A6 | Event inbox `payment_gateway_events` keyed `(gateway, event_id)`, no `org_id`, deny-all to `authenticated` (matches `RealSupabaseEventInbox`); `commerce_privacy_requests.details`, `commerce_storefront_hosts.created_at` added | none |
| A7 | Webhook: a confirmed payment on `created`/`failed` chains legally to `paid` (money never dropped); payment on cancelled/refunded/chargeback → ignored + error log (manual refund); `PAYMENT_CHARGEBACK_REQUESTED` → `chargeback`; `PAYMENT_OVERDUE` → `expired`; fulfillment handlers must be idempotent per order | P4 adds refund/void flows |
| A8 | Coupon zeroing the total refused (`total_zero`, `NOC-REMEDIATE[commerce-free-orders]`); cancelling a pending order does not void the gateway charge (`NOC-REMEDIATE[commerce-gateway-cancel]`) | P4 |
| A9 | `CommerceConfig` + router factory signatures — see `noctusai_lib/domain/commerce/__init__.py` and `KB § 04-SHARED-LIBRARY.md` organ entry; host adds `{MEDIA_UPLOAD_PATH_PATTERN: MEDIA_UPLOAD_MAX_BYTES}` to `max_body_path_overrides` | slice B PART 2 |
| A10 | `commerce_orders` gains nullable `buyer_doc TEXT`, `buyer_name TEXT`, `fiscal_retain_until DATE` (D30 tax-record snapshot set when the order reaches `paid`; nulled by `purge_expired_fiscal_retention`). Order payloads / `export_customer` now carry them. FE: staff order detail may show `buyer_doc` masked | fiscal retention |

**Decided (D30, 2026-10-13):** on anonymize, PAID orders (incl. later refunded/chargeback) keep the buyer's CPF/CNPJ + name as a tax record until `fiscal_retain_until` (LGPD art. 16 II + CTN art. 173: 1 Jan of paid year + 6); everything else is scrubbed; `purge_expired_fiscal_retention` erases them after the window.

## Hold — host product commit (RESOLVED by D31, 2026-10-13)

Slice B's scaffold was held because `check_secdef_migration_revokes_execute` flagged the 5 SECURITY DEFINER RLS helpers the template copies. Resolved by D31: the scaffold now emits a product that passes the keeper by construction (`fa4e46d85`), and the host product landed on dev (`2737bbb33` scaffold, `f013e0f0c` organ wiring). Slice D proceeded on that base.

## Organ hardening deltas (feat/commerce-organ-hardening, off dev 8fad3c98e)

| # | Delta | Frontend / host action |
|---|---|---|
| H1 | `CommerceConfig.org_id_expr` is now `Optional[str] = None` ⇒ derived `public.current_org_id_for('<schema>')` (was the home-only `public.current_org_id()`). Every own-org policy AND the `credentials` SELECT policy use it. The media bucket's object RLS stays HOME-ONLY (`current_org_id()`): storage never acts per `projects/org-picker/CONTRACT.md` | host override removed (`app/commerce.py`); `012_commerce.sql` output byte-identical (host already passed the same expression) |
| H2 | New per-org key `asaas_environment` (`CommerceConfig.asaas_environment_name`), choice `sandbox` / `production`, default `sandbox` (`CommerceConfig.asaas_default_environment`). The gateway charges, reads customers and probes in the org's environment; an unknown value ⇒ `GatewayNotConfigured` (checkout 503) | host `API_KEY_SPECS` gains the CHOICE spec; seed `ApiKeysPanel` renders it as a switch (no FE change expected — options/default come from `GET /api/settings/api-keys`) |
| H3 | `CheckoutGateway` Protocol gains `checkout_for_key(org_id, api_key) -> HostedCheckout` (Fake returns its checkout) | a custom gateway implementation must add it |
| H4 | Readiness probe lifted: `noctusai_lib.domain.commerce.probe_api_key_readiness` + payments `readiness_verdict` / `ReadinessVerdict` / `READINESS_READY_MESSAGE`. Seed `create_api_keys_router` gains `org_testers={name: async (value, org_id)}` (additive) | `POST /api/settings/api-keys/asaas_api_key/test` unchanged on the wire (`{key, success, message}`); `products/store` keeps its copy (inactive, to migrate or retire) |

## Slice D deltas (host pages, `products/commerce/frontend/src/**`, branch `feat/commerce-p3-pages`)

| # | Delta | Owner / follow-up |
|---|---|---|
| D1 | CONTRACT §5 has no staff **product list** component. `/admin/produtos` carries a page-local list (search, status filter, pagination) over `useProducts`; marked `NOC-REMEDIATE[commerce-products-table-organ]` | organ (slice C follow-up): add `ProductsTable`, then the page consumes it |
| D2 | Organ hooks don't wrap `GET/POST/DELETE /api/commerce/hosts`, A1 `GET /api/storefront/my-orders`, A1 `POST /api/storefront/privacy-requests/verify`; organ has `usePrivacyRequest` but no form component. Host covers them in `src/hooks/{useStorefrontHosts,useMyOrders,usePrivacyVerify}.ts` + `pages/storefront/PrivacyRequest.tsx` (`/privacidade`); marked `NOC-REMEDIATE[commerce-organ-hook-gap]` / `[commerce-privacy-request-form-organ]` | organ: lift hooks into `createCommerceHooks` + add `PrivacyRequestForm` |
| D3 | Organ components render the server `message`, not the A3 `code` (only `aceite_obrigatorio`/`versao_conflitante` are mapped). The full A2/A3 code → pt-BR/en map lives in `src/lib/i18n.ts` (`describeError`) and is used by host-owned pages; marked `NOC-REMEDIATE[commerce-error-i18n-organ]` | organ: move `error.*` into `messages.ts`, map codes in components |
| D4 | No org-wide **privacy-request queue**: no `GET /api/commerce/privacy-requests` / resolve endpoint, and the organ's customer detail does not render the `privacy_requests` it receives. P3 handles requests per customer (export/anonymize in `/admin/clientes`, with an explanatory note); no standalone page (it would show no real data). `NOC-REMEDIATE[commerce-privacy-queue]` | backend + organ (P4 or a P3 follow-up) |
| D5 | A10 fields (`buyer_name`, `buyer_doc`, `fiscal_retain_until`) are not in the organ `Order` type nor shown by `OrderDetail`. `/admin/pedidos/:id` adds a page-level buyer block (doc masked via `maskCpfOrCnpj`) reading the same `useOrder` query | organ: add the fields to `Order` + show them in `OrderDetail` |
| D6 | Back-office nav `route` keys need `commerce.status_pagina` rows or the items are hidden: `pedidos`, `clientes`, `cupons`, `produtos`, `categorias`, `loja`, `enderecos`, `integracoes` (`equipe` exists). Pages work by URL meanwhile | host backend (slice B): one migration inserting the rows |
| D7 | Routing: `/` is the storefront (`publicRoutes`), so the scaffold Landing/Dashboard/Example pages are retired from the FE; `unauthRedirect: "/login"`; Login lands on `/admin`. On the back-office host the storefront 404 → organ "no store" state; a signed-in user is sent to `/admin` (covers the seed SSO callback, which lands on `/`). Storefront paths = organ link templates (`/pedido/{token}`, `/minhas-compras?token=`, `/privacidade/verificar?token=`) + `/p/:slug`, `/carrinho`, `/checkout`, `/privacidade` | none; note: the seed's remembered-deep-link restore only runs when `/` is an auth route, so `/admin/*` deep links are not restored after login here (seed gap) |
| D8 | No FE platform-staff helper exists. `StoreProfileForm`'s `isPlatformAdmin` (fee field) is derived from the server answering the platform-admin-only `GET /api/commerce/hosts` with 200 (403 ⇒ false) | seed: a `useIsPlatformStaff()` or capability flag on the profile response |
