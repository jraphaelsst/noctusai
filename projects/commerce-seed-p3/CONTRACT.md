# Commerce seed P3 — contract (organ ↔ host product ↔ frontend)

> **Authoritative for slices A–D.** Change it only through the tech-lead; every slice builds to these exact names. Roadmap: `project-history/roadmaps/commerce-seed-2026-10.md` (D1–D29). Design source: P3 Phase-0 audit (summarized in `PROJECT.md §5`).
> Money is **integer cents** everywhere (`*_cents`). Timestamps are ISO-8601 UTC. Ids are UUID strings. All tables carry `org_id uuid not null` + RLS (`rls_subquery_policy` + `service_role_bypass`, card_hub convention).

## 1 · Enums (owned by the backend organ `noctusai_lib.domain.commerce.types`; mirrored in `@noctusai/lib` `commerce/types.ts`; a parity test pins them)

| Enum | Values |
|---|---|
| `ProductType` | `digital` · `physical` · `service` · `print_on_demand` |
| `FulfillmentType` | `digital_delivery` · `shipping` · `pickup` · `local_delivery` · `none` |
| `ProductStatus` | `draft` · `in_review` · `published` · `unlisted` · `retired` |
| `OrderStatus` | `created` · `pending_payment` · `paid` · `expired` · `failed` · `cancelled` · `refunded` · `chargeback` |
| `TaxRegime` | `mei` · `simples` · `lucro_presumido` · `lucro_real` · `outro` |
| `TaxTreatment` | `service_nfse` · `rights_receipt` · `goods_nfe` · `none` |
| `CouponKind` | `percent` · `fixed` |
| `ConsentKind` | `terms` · `privacy` · `marketing` · `immediate_delivery_waiver` |
| `PrivacyRequestKind` | `access` · `correction` · `deletion` · `portability` · `revoke_consent` |
| `FieldSource` | `form` · `payment` · `staff` |
| `PaymentMethod` | `pix` · `boleto` · `credit_card` |

**Order transitions** (pure function `order_state.transition(current, event) -> new | raises InvalidTransition`; every applied transition appends a `commerce_order_events` row):
`created → pending_payment | failed | cancelled` · `pending_payment → paid | expired | failed | cancelled` · `expired → paid` (late payment = recovery) `| cancelled` · `failed → pending_payment` (retry) · `paid → refunded | chargeback`. Terminal: `cancelled`, `refunded`, `chargeback`.

**Fulfillment seam:** `FulfillmentHandler` Protocol `on_paid(order, items) -> None`; registry keyed by `FulfillmentType`; default `noop` for every type in P3 (P5 fills `digital_delivery`, P9 the physical ones).

## 2 · Tables (`commerce_migration(cfg, schema) -> str`, rendered verbatim into the product's own migration + parity test)

| Table | Key columns |
|---|---|
| `commerce_store_profiles` | `org_id` PK · `version` int · `legal_name` · `trade_name` · `cnpj` NOT NULL (validated: `primitives.identificador.cnpj_dv_valido`) · `tax_regime` · `tax_treatment` jsonb `{ProductType: TaxTreatment}` · `locale` (default `pt-BR`) · `currency` (default `BRL`) · `brand_tokens` jsonb · `address` jsonb · `contact_email` · `contact_phone` · `platform_fee_bps` int default 0 (**platform-admin only**; basis points) · `updated_at` · `updated_by` |
| `commerce_store_profile_versions` | `org_id`, `version` (PK pair) · `snapshot` jsonb · `changed_by` · `changed_at` — INSERT v+1, PK conflict → 409 (store `settings_service` pattern) |
| `commerce_storefront_hosts` | `hostname` PK · `org_id` · `is_primary` |
| `commerce_categories` | `id` · `slug` (unique per org) · `name` · `parent_id` · `position` |
| `commerce_products` | `id` · `slug` (unique per org) · `title` · `description` · `product_type` · `fulfillment_type` · `status` · `category_id` · `attributes` jsonb · `tax_treatment_override` nullable · timestamps |
| `commerce_offers` | `id` · `product_id` · `name` · `price_cents` (>0) · `currency` · `active` · `position` |
| `commerce_media` | `id` · `product_id` · `storage_path` (private bucket, org-prefixed) · `kind` (`image`·`video`) · `alt` · `position` |
| `commerce_coupons` | `id` · `code` (unique per org, case-insensitive) · `kind` · `value` (percent 1–100 or cents) · `starts_at` · `ends_at` · `max_uses` · `uses_count` · `active` |
| `commerce_customers` | `id` · `email` (unique per org, lowercased) · `name` · `doc` (CPF/CNPJ digits) · `phone` · `address` jsonb · `field_sources` jsonb `{field: {source: FieldSource, at, verified: bool}}` · `anonymized_at` · timestamps |
| `commerce_consents` | append-only · `customer_id` · `order_id` nullable · `kind` · `version` · `granted` · `ip` · `user_agent` · `at` |
| `commerce_privacy_requests` | `id` · `customer_id` · `kind` · `status` (`open`·`verified`·`done`·`rejected`) · `verified_at` · `created_at` · `resolved_at` |
| `commerce_orders` | `id` · `token` (opaque, unique) · `customer_id` · `status` · `subtotal_cents` · `discount_cents` · `total_cents` · `currency` · `coupon_id` · `payment_method` · `gateway` · `gateway_charge_id` · `checkout_url` · `pix_qr` jsonb · `expires_at` · `paid_at` · `platform_fee_cents` · timestamps |
| `commerce_order_items` | `id` · `order_id` · `product_id` · `offer_id` · `title_snapshot` · `product_type` · `fulfillment_type` · `unit_price_cents` · `qty` · `total_cents` |
| `commerce_order_events` | append-only · `order_id` · `from_status` · `to_status` · `reason` · `source` (`checkout`·`webhook`·`staff`·`system`) · `at` |
| event inbox | `event_inbox_table_sql(schema)` — NEW generator in `domain/payments/` (matches `RealSupabaseEventInbox`) |
| credentials | existing `credentials_table_ddl(schema)` (per-org Asaas keys, Fernet) |

**Customer enrichment rule (D26):** checkout writes fields with `source=form`; a confirmed payment webhook overwrites name/doc/email/phone/address with the gateway's customer data, `source=payment, verified=true` — **payment is the source of truth**; staff edits are `source=staff`. Never downgrade a `payment` field with a later `form` value.

**Platform fee (D27):** at charge creation, if `platform_fee_bps > 0` and a platform wallet id is configured (`resolve_credential("asaas_platform_wallet_id")` platform tier), the Asaas charge carries a split `{walletId, percentualValue: bps/100}`; `platform_fee_cents` is recorded as **expected**; it is treated as earned only when the order is `paid` and not later `refunded`/`chargeback`. No wallet configured ⇒ no split (logged once, not an error).

## 3 · Staff API (license-gated; `auth_dependency` = product's `get_current_user_org`; envelope `success_response` → `{"data": …}`; lists `paginated_response` → `{"data": [...], "pagination": {...}}`)

| Method + path | Body / query | Returns `data` |
|---|---|---|
| `GET /api/commerce/profile` | — | profile or `null` |
| `PUT /api/commerce/profile` | profile fields + `expected_version` | profile (422 `cnpj_invalido`, 409 `versao_conflitante`); `platform_fee_bps` ignored unless caller is platform admin |
| `POST /api/commerce/profile/cnpj-lookup` | `{cnpj}` | prefill from `integrations/cnpj_registry` |
| `GET/POST /api/commerce/categories` · `PATCH/DELETE …/{id}` | | category |
| `GET /api/commerce/products?status=&q=&page=` · `POST` · `GET/PATCH/DELETE …/{id}` | product fields | product (+ `offers`, `media` on GET by id) |
| `POST /api/commerce/products/{id}/status` | `{status}` | product (guards: publish needs ≥1 active offer) |
| `GET/POST /api/commerce/products/{id}/offers` · `PATCH/DELETE …/offers/{offer_id}` | | offer + `fee_estimate` `{pix_cents, boleto_cents, card_cents}` (Asaas list prices, labelled estimate) |
| `POST /api/commerce/products/{id}/media` (multipart) · `DELETE …/media/{media_id}` | | media with signed `url` |
| `GET/POST /api/commerce/coupons` · `PATCH/DELETE …/{id}` | | coupon |
| `GET /api/commerce/customers?q=&page=` · `GET …/{id}` · `GET …/{id}/export` · `POST …/{id}/anonymize` | | customer (+ orders, consents) |
| `GET /api/commerce/orders?status=&page=` · `GET …/{id}` · `POST …/{id}/cancel` | | order (+ items, events) |
| `GET/POST /api/commerce/hosts` · `DELETE …/{hostname}` | platform admin only | host rows |

## 4 · Public storefront API (no login; org resolved from the `Host` header via `commerce_storefront_hosts` — unknown host ⇒ 404; org without an active `commerce` license ⇒ 404; rate-limited)

| Method + path | Body | Returns `data` |
|---|---|---|
| `GET /api/storefront` | — | `{trade_name, legal_name, cnpj, address, contact, brand_tokens, locale, currency, legal: {terms_version, privacy_version, withdrawal_text}}` (Decreto 7.962 art. 2 disclosures) |
| `GET /api/storefront/catalog?category=&q=&page=` | — | published products with active offers + first media url |
| `GET /api/storefront/products/{slug}` | — | product + offers + media |
| `POST /api/storefront/checkout/quote` | `{items: [{offer_id, qty}], coupon?}` | `{lines, subtotal_cents, discount_cents, total_cents, currency, coupon_error?, requires_immediate_delivery_waiver: bool}` |
| `POST /api/storefront/checkout` | quote body + `buyer {name, email, doc, phone}` + `address?` + `payment_method` + `consents {terms_version, privacy_version, marketing: bool, immediate_delivery_waiver: bool}` | `{order_token, status, checkout_url?, pix_qr?, expires_at}` — 422 `aceite_obrigatorio` when terms/privacy missing or a digital item lacks the waiver; price always recomputed server-side |
| `GET /api/storefront/orders/{token}` | — | public order view (status, items, totals, no internal ids) |
| `POST /api/storefront/orders/access-link` | `{email}` | always 202 (magic link to "my orders" emailed if the customer exists; no enumeration) |
| `POST /api/storefront/privacy-requests` | `{email, kind, details?}` | 202; verified by email link |

**Webhook:** `POST /api/webhooks/payments/{gateway}/{org_id}` — 5-pin verification (per-org token from credentials), inbox claim → order transition → release on failure (store `webhook_service` pattern). Unknown events are recorded and ignored, never 5xx-looped.

## 5 · Frontend organ (`seed/lib/frontend/src/commerce/**`, exported from the `@noctusai/lib` barrel)

`types.ts` (this contract's enums + DTOs, first commit) · `createCommerceHooks(apiBase)` (TanStack Query; two-signal loading: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`) · staff: `StoreProfileForm` (CNPJ mask + check-digit validation via `identificador.ts`, lookup prefill, tax regime, tax treatment per product type, locale/currency, brand tokens) · `ProductEditor` (slots per `ProductType`) · `OffersEditor` (shows `fee_estimate`) · `CategoryManager` · `CouponsEditor` · `OrdersTable` · `OrderDetail` (event timeline) · `CustomersTable` · `PrivacyActions` · storefront: `StorefrontShell` (brand tokens → CSS vars) · `ProductGrid` · `ProductCard` · `ProductPage` · `Cart` (local state) · `CheckoutForm` (disclosures + required consents + immediate-delivery waiver when any digital line) · `OrderStatusPage` · `MyOrdersRequest`. Copy is pt-BR by default with an i18n map keyed by `locale`.

## 6 · Host product `products/commerce` (slug `commerce`, back office `commerce.noctusai.com`, `deploy_scope=dev` until T2)

Scaffolded from the seed; consumes the organ: `app/commerce.py` (CommerceConfig) · `migrations/0NN_commerce.sql` (generator output) + parity test · router mounts (staff + storefront + webhook) · api-key specs for Asaas (+ readiness tester lifted from store `key_testers.py`) · pages `/admin/*` (staff organ components) and `/` storefront (host-resolved; on `commerce.noctusai.com` itself the storefront shows a "no store on this address" state).
