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

## Hold — host product commit (owner decision pending, 2026-10-13)

Slice B's scaffold of `products/commerce` is complete and staged but NOT committed: the pre-commit keeper `check_secdef_migration_revokes_execute` flags the 5 SECURITY DEFINER RLS helpers the template copies (`current_org_id`, `current_org_role`, `current_user_org_id`, `is_customer`, `current_customer_org_id` — all verified as referenced by policies). The engineer's marker edit (`-- secdef-execute-ok: rls-helper`) was refused by the auto-mode safety classifier. Owner chose to hold and decide; options presented: scaffold emits verified markers / REVOKEs by construction (recommended), mark the commerce copies only, or baseline entries. Slice D (pages) waits on this.
