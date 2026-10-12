# Commerce seed — digital-product seed + products inside products (2026-10-12)

> Companion to [`commerce-seed-2026-10.md`](commerce-seed-2026-10.md) (decision D21). Research done 2026-10-12; sources inline. No public benchmarks exist from Hotmart / Kiwify / Eduzz for conversion, refund or order-bump rates — most Brazilian figures are vendor-blog approximations, so the seed **measures its own numbers from day one** instead of relying on outside ones.

## 1 · Two levels of "product"

- **noc product** — a deployed app (e.g. *Gilson's Store*, the photo store). Created with skill `noc-new-product`.
- **Catalog product** — a sellable item *inside* a store (e.g. Gilson's purchase-and-sale contract template, one photo, one course). Created with the **products-inside-products tools** (§5). The photographer's photos and Gilson's contracts are both digital catalog products; the photo store specializes the same model.

## 2 · Digital-product model (L1 commerce organ, `product_type=digital`)

**Entities:** store (= org's store profile) · product · offer/price (one product, several offers) · deliverable · deliverable_version · entitlement (grant: license terms, `access_until` lifetime or N days) · coupon · bundle · order bump · upsell · affiliate · commission rule (first/last/split click, cookie TTL, applies-to-bumps).

**Deliverable types — a named seam (`deliverable_type`):**
`file` (download) · `generated_document` (questionnaire → document filled per buyer) · `course` (modules → lessons, progress, certificate) · `ebook` · `license` (photo/video/music: preview + original + certificate) · `bundle`.

**Product lifecycle:** `draft → in_review → published → (updated: new deliverable_version, old versions kept) → unlisted/deprecated (buyers keep access) → retired`.

**Order lifecycle (digital):** `created → pending_payment (Pix/boleto with expires_at) → paid | expired | failed → refunded (partial/full) | chargeback`. `expired` is its own state because unpaid Pix/boleto is a recovery funnel, not a dead end (Pix ≈75% paid vs boleto ≈50% in Mercado Pago data — https://www.infomoney.com.br/minhas-financas/pix-atropela-boleto-e-ja-domina-compras-a-vista-no-mercado-pago/).

**Versioning gap we fill:** Gumroad replaces the file and emails buyers, with no changelog or version dashboard (https://gumroad.com/help/article/126-setting-up-versions-on-a-digital-product). The seed keeps `deliverable_version` rows + buyer notification + version-adoption metric.

**Analytics events (emitted by the organ, not the product):** `product_viewed · added_to_cart · checkout_started · order_paid · order_expired · payment_recovered · deliverable_accessed · version_published · version_notified · version_downloaded · refund_requested · refund_completed · chargeback_opened · questionnaire_started · document_generated`.

## 3 · KPIs the seed ships (dashboard per store and per catalog product)

| Metric | Formula | Why | Layer |
|---|---|---|---|
| Store conversion | paid orders / sessions | overall health (global e-com ≈1.7–2.7%; low-ticket info-products ≈2–5%, approx.) | core |
| Funnel step rates | step n+1 / step n | where the leak is | core |
| Payment completion by method | paid / created per Pix · boleto · card | expiry losses (Pix 42% of BR online value in 2025 — https://www.poder360.com.br/poder-economia/pix-chega-a-42-dos-pagamentos-on-line-no-brasil/) | core |
| Recovery rate | recovered / expired+abandoned | value of reminders (Hotmart cites ≈+8% revenue from recovery, vendor claim) | core |
| AOV | revenue / paid orders | pricing, bumps | core |
| Bump / upsell take | orders with bump / paid orders | ticket lift (no public benchmark) | core |
| Refund rate | refunds / paid orders | fit, abuse — CDC art. 49 gives 7 days even for digital goods per Brazilian consumer bodies | core |
| **Refund-after-access** | refunds with access / refunds | download-then-refund abuse — **critical for contracts** | core |
| Chargeback rate | chargebacks / settled card transactions | card-network thresholds ≈1.5–2.2% (dates/regions vary) | core |
| Access rate | buyers who accessed / paid | delivery problems, value | core |
| Time-to-first-value | median(first access − paid) | onboarding | core |
| LTV · CAC · repeat rate | Σnet/buyers · spend/new buyers · repeat buyers/buyers | unit economics | core |
| Affiliate share | affiliate revenue / revenue | channel dependence | core |
| NPS / rating | %promoters − %detractors · avg stars | trust | core |
| Per-product conversion · net revenue · tickets/100 sales | per catalog product | catalog pruning | core |
| Version adoption | re-downloads of vN / notified buyers | value of updates | core |
| Questionnaire completion | documents generated / started | generator friction | contracts |
| E-sign attach / completion | add-on / orders · signed / sent | upsell, real use | contracts |
| Lesson completion · certificates | lessons done / total · certs / enrolled | engagement, refund predictor | courses |

## 4 · Gilson's contract product (the first canonical digital catalog product)

- **Deliverable:** `generated_document` — buyer answers a questionnaire, sees a full preview, pays, gets the filled contract (DOCX + PDF), with free edits for N days. Source templates exist: `projects/store/contrato/` (purchase-and-sale: cash / financed / installments, plus `gerar_modelo.py`). Brazilian reference: GeraContratos (pay-per-contract, preview before paying, 7-day refund) — https://geracontratos.com.br/contrato-compra-venda-imovel.
- **Pricing:** per document first (D7-style simplicity); subscription later only with clear renewal consent (US sellers draw complaints about auto-renew).
- **LGPD:** questionnaire answers include third parties' CPFs and addresses → personal data with a contract legal basis, retention policy, access only by the buyer and the store org.
- **Disclaimers (shown before payment and in the document):** not legal advice / consult a lawyer; a private purchase-and-sale contract does not transfer property (public deed + ITBI + registry required — CC arts. 108/219).
- **E-signature add-on (later):** simple/advanced e-signatures are valid for private contracts (MP 2.200-2 art. 10 §2, Lei 14.063) with an audit trail.
- **⚠️ Open — OAB:** if Gilson is a lawyer, his marketing must follow OAB Provimento 205/2021; per-buyer *tailored review* could edge into work reserved to lawyers. Selling template kits was held lawful (2016), but OAB-RJ contests cheap AI-generated petitions. Needs the owner's / counsel's answer before P13. (Sources: https://oab.estrategia.com/portal/publicidade-advocacia-provimento-205-2021/ · https://www.conjur.com.br/2016-mar-12/site-oferecer-peticoes-gratis-vender-kits-modelos-prontos//?print=1)

## 5 · Products-inside-products tools (design — built with the catalog organ in P3/P5)

One service layer in the commerce organ (`noctusai_lib/domain/commerce/catalog`), three faces over the SAME code:

1. **MCP tools now** (agent-facing, for building and learning): `noctus.commerce.catalog_product` with actions
   `draft` (store org, title, deliverable_type, spec) · `spec` (fill/validate the type's required fields — returns what's missing) · `attach_deliverable` (file / template + questionnaire schema / course outline) · `version` (new deliverable_version + changelog) · `price` (offers, coupons, bumps) · `publish` / `unlist` / `retire` (lifecycle with guards) · `preview` (render the buyer view / generated sample) · `metrics` (§3 per product).
2. **Admin UI later** (operator-facing, in each store's back-office): a "New product" wizard calling the same service endpoints.
3. **Product-type templates** (the "seed" for catalog products): one spec template per `deliverable_type` (required fields, validations, default KPIs) — the contract template is the first `generated_document` template; photos the first `license` template.

Rules: the MCP tools never write tables directly — they call the organ's service (same validation as the UI); every action is org-scoped and audited; the tools open `noc-learn-refine` trials on their own precision (e.g. `spec` missing-field detection vs what the owner later had to add).

## 6 · Open questions

- Is Gilson a lawyer? (OAB constraints, §4.)
- Which contract templates beyond purchase-and-sale ship first?
- Course hosting: own player + storage vs external (e.g. video host) — P13.
- Affiliates in v1 or later?
