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

## Hold — host product commit (owner decision pending, 2026-10-13)

Slice B's scaffold of `products/commerce` is complete and staged but NOT committed: the pre-commit keeper `check_secdef_migration_revokes_execute` flags the 5 SECURITY DEFINER RLS helpers the template copies (`current_org_id`, `current_org_role`, `current_user_org_id`, `is_customer`, `current_customer_org_id` — all verified as referenced by policies). The engineer's marker edit (`-- secdef-execute-ok: rls-helper`) was refused by the auto-mode safety classifier. Owner chose to hold and decide; options presented: scaffold emits verified markers / REVOKEs by construction (recommended), mark the commerce copies only, or baseline entries. Slice D (pages) waits on this.
