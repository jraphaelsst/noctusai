# Commerce seed P4 — contract (payments · commerce money states · finance · invoices)

> **Authoritative for slices A–F.** Change it only through the tech-lead; every slice builds to these exact names. Decisions: roadmap D32–D40. Extends `projects/commerce-seed-p3/CONTRACT.md` (conventions unchanged: money **integer cents** (`*_cents`), ISO-8601 UTC, UUID ids, every table `org_id uuid not null` + RLS via the organ config's `org_id_expr`, `success_response` / `paginated_response` envelopes, pt-BR error codes).
> **Reviewed 2026-10-13** by `architect` + `security` (read-only); their MUST-FIX items are folded in below.
> **Additive rule.** Existing consumers of the payments organ — `products/store` (Asaas), `products/community` (**Asaas AND Stripe**), the commerce webhook — keep working unchanged: nothing in §1 renames or remaps an existing `EventKind`, field or method.

## 0 · Cross-cutting rules (every slice)

- **Authorization.** RLS is the floor, never the only check. Org staff (`get_current_user_org`) may read. **Org admin** (`noctusai_lib.api.auth.platform.require_org_admin`) is required for: refunds, invoice issue/cancel, `PUT /fiscal`, certificate upload, NFS-e cutover (and its rollback), finance writes (entries, settlements, reversals, transfers, recurrences, accounts, categories, cost centers, statement import + match) and every export. A platform admin acting on another org goes through `require_platform_admin` only, and the action records the real `actor`. Request history comes from the seed audit middleware (`noctusai_lib.api.audit`); domain history lives in the domain rows themselves (order events, refund rows, settlement reversals — §3.3), so no new audit table.
- **Never trust a webhook body for money.** Any payment/refund/dispute/invoice webhook re-reads the gateway/provider (`get_charge` / `get`) and derives state from that read.
- **Secrets never leave the call.** Certificates, passwords, tokens: never in logs, exception messages, `raw` fields, error-tracker locals (Sentry `include_local_variables=False` or a scrubber). Provider error bodies are mapped to generic pt-BR codes before reaching the client.
- **Jobs.** Idempotent periodic sweeps use the seed scheduler (`noctusai_lib.api.scheduler.register`). Work that must retry with backoff (invoice issue/cancel) uses the durable jobs worker (`noctusai_lib.domain.jobs`, `dedupe_key` = the invoice `ref`).

---

## 1 · Payments organ (`noctusai_lib.integrations.payments`) — slice A

### 1.1 New Protocol `ChargeOperations` (`charges.py`; `FakeChargeOperations`, `AsaasChargeOperations`, `StripeChargeOperations`; factory `make_charge_operations(...)` mirrors `make_hosted_checkout`, fake-or-refuse)

| Method | Returns | Notes |
|---|---|---|
| `get_charge(charge_id_at_gateway)` | `GatewayCharge` | read-only |
| `refund_charge(charge_id_at_gateway, *, amount: Money \| None, description: str)` | `GatewayRefund` | `None` = full remaining. Asaas `POST /v3/payments/{id}/refund {value, description}`; Stripe `POST /v1/refunds`. Above refundable ⇒ `PaymentGatewayError(code="refund_exceeds_balance")` before calling out |
| `cancel_charge(charge_id_at_gateway)` | `GatewayCharge` | unpaid only (Asaas `DELETE /v3/payments/{id}`; Stripe expire session / cancel PaymentIntent). Paid ⇒ `PaymentGatewayError(code="charge_already_paid")` |
| `list_balance_transactions(*, since: date, cursor: str \| None)` | `BalanceTransactionPage{items, next_cursor}` | Asaas `GET /v3/financialTransactions`; Stripe `GET /v1/balance_transactions` |

Types (`types.py`):
- `ChargeStatus` = `pending` · `confirmed` (card approved, money not yet available) · `received` · `overdue` · `partially_refunded` · `refunded` · `disputed` · `chargeback` · `cancelled`. Unknown gateway status **raises** `PaymentGatewayError(code="unknown_charge_status")`.
- `GatewayCharge{id_at_gateway, status, method: PaymentMethod, amount: Money, net: Money | None, fee: Money | None, refunded: Money, refunds: list[GatewayRefund], installment_count: int, due_date, paid_at, credit_date (when funds become available), external_reference, raw}`
- `GatewayRefund{id_at_gateway | None, charge_id_at_gateway, amount: Money, status: "pending" | "done", created_at, raw}`
- `BalanceTransaction{id_at_gateway, occurred_at, kind: "charge" | "fee" | "refund" | "chargeback" | "transfer" | "adjustment" | "other", amount: Money (signed), charge_id_at_gateway | None, description, raw}`

### 1.2 `CheckoutRequest` additions (backward-compatible defaults)
- `installment_count: int = 1` — `>1` only with `billing_method="credit_card"` on a one-off; Asaas sends `installmentCount` + `totalValue`; Stripe refuses `>1` with `PaymentGatewayError(code="installments_unsupported")`.
- `customer_reference: str | None = None` — when set, `ensure_customer` is keyed on it (one gateway customer per buyer); `external_reference` stays the per-charge conciliation key. Fixes the P3 drift "one Asaas customer per order".

### 1.3 `GatewayEvent` refinement (additive)
New field `detail: EventDetail | None`, with `EventDetail = Literal["overdue", "partial", "chargeback_opened", "evidence_submitted", "won", "lost", "confirmed", "received"]`. New kinds `charge_partially_refunded`, `charge_dispute` and `charge_cancelled`. **Existing kind mappings are unchanged.**

| Gateway event | `kind` | `detail` |
|---|---|---|
| Asaas `PAYMENT_CONFIRMED` / `PAYMENT_RECEIVED` | `charge_paid` (unchanged) | `confirmed` / `received` |
| Asaas `PAYMENT_OVERDUE` | `charge_failed` (unchanged) | `overdue` |
| Asaas `PAYMENT_REFUNDED` | `charge_refunded` (unchanged) | — |
| Asaas `PAYMENT_PARTIALLY_REFUNDED` | `charge_partially_refunded` (new; was `ignored`) | `partial` |
| Asaas `PAYMENT_CHARGEBACK_REQUESTED` | `charge_refunded` (unchanged) | `chargeback_opened` |
| Asaas `PAYMENT_CHARGEBACK_DISPUTE` | `charge_dispute` (new) | `evidence_submitted` |
| Asaas `PAYMENT_AWAITING_CHARGEBACK_REVERSAL` | `charge_dispute` | `won` |
| Asaas `PAYMENT_DELETED` | `charge_cancelled` (new; was `ignored`) | — |
| Stripe `charge.refunded` | `charge_refunded` (unchanged) | `partial` when `amount_refunded < amount` |
| Stripe `charge.dispute.created` / `.closed` | `charge_dispute` (new) | `chargeback_opened` / `won` \| `lost` |

- **Partial refunds (Asaas):** the kind for `PAYMENT_PARTIALLY_REFUNDED` is the new **`charge_partially_refunded`** (was `ignored`) — NOT `charge_refunded`, which `store` reads as "stop downloads". Community, which does book Stripe partial refunds via `charge_refunded`, is untouched because the Stripe mapping above keeps `charge_refunded`.
- **Stripe disputes** move from `ignored` to `charge_dispute` — community's if/elif chain has no branch for it, so it stays a no-op there (no false refund booked).
- **Slice A verifies** every Asaas event name and the "dispute lost" signal against `docs.asaas.com` and cites the source in its delivery note. If Asaas has no "lost" event, the lost path is reached by `get_charge` returning `chargeback` (slice B's `commerce_dispute_poll`).

---

## 2 · Commerce organ money states (`noctusai_lib.domain.commerce`) — slice B

### 2.1 Enums (`types.py` + `commerce/types.ts`, parity test)
- `OrderStatus` **adds** `partially_refunded`, `disputed` (UI label "Contestado").
- New `RefundStatus` = `requested` · `done` · `failed`; `ChargeAttemptStatus` = `pending` · `paid` · `expired` · `cancelled` · `failed`; `ReminderKind` = `before_expiry` · `after_expiry`.
- `InvoiceKind`, `InvoiceStatus`, `NfseMode` are **owned by `integrations/invoices/types.py`** (slice E) and re-exported by commerce (integrations never import domain).

### 2.2 Transitions (`order_state.TRANSITIONS`, additions; one target per `(state, event)`)
| From | Event | To |
|---|---|---|
| `expired` | `RETRY` (buyer regenerates) | `pending_payment` |
| `paid` | `PARTIAL_REFUND` | `partially_refunded` |
| `partially_refunded` | `PARTIAL_REFUND` / `REFUND` | `partially_refunded` / `refunded` |
| `paid`, `partially_refunded` | `DISPUTE_OPENED` | `disputed` |
| `disputed` | `DISPUTE_WON` / `DISPUTE_WON_PARTIAL` | `paid` / `partially_refunded` (service picks by Σ done refunds) |
| `disputed` | `DISPUTE_LOST` | `chargeback` (terminal) |
| `partially_refunded` | `CHARGEBACK` | `chargeback` (counterpart of the P3 `paid → chargeback` edge, which stays) |

- **`webhook.py` rewrite:** branch on `kind` / `detail` only, never on `raw`. `charge_refunded` + `detail=chargeback_opened` ⇒ `DISPUTE_OPENED` (not `CHARGEBACK`). `charge_paid` + `confirmed` ⇒ `paid`; `received` ⇒ finance settlement (§2.4). Refund/partial/dispute events ⇒ re-read `get_charge` and reconcile (§2.4).
- **Fulfillment seam:** `FulfillmentHandler` gains `on_paused(order)` / `on_resumed(order)` (→/← `disputed`), `on_revoked(order)` (→ `refunded` | `chargeback`), `on_expired(order)` (→ `expired`). All default no-op. **Closed 2026-10-14 (ERP E6):** two more optional hooks, `on_created(order, items)` (runs BEFORE the order row exists; raising refuses the sale) and `on_cancelled(order, items)` (checkout failed after the hold, or staff cancelled), and the seed `StockFulfillment` (`domain/commerce/stock_fulfillment.py`) drives the inventory `StockPort` through them: created → `reserve`, paid → `commit`, `on_expired` / `on_cancelled` / `on_revoked` → `release` — D35's "stock released" is real for products linked to an item (`commerce_products.item_id`, the `commerce_erp` link delta).

### 2.3 Tables (added to `commerce_migration`; rendered into a NEW host migration, never editing `012`)
| Table | Key columns |
|---|---|
| `commerce_order_charges` | `id` · `order_id` · `attempt` int (unique per order) · `gateway` · `gateway_charge_id` (unique per gateway) · `payment_method` · `installment_count` · `amount_cents` (incl. buyer interest) · `status` · `checkout_url` · `pix_qr` jsonb · `due_at` · `created_at` · `closed_at`. `commerce_orders.gateway_charge_id` points at the **current** attempt; `commerce_orders.charge_attempts` int |
| `commerce_refunds` | `id` · `order_id` · `charge_id` → `commerce_order_charges` · `amount_cents` (>0) · `reason` · `status` · `gateway_refund_id` (unique when not null) · `idempotency_key` (unique per order when not null) · `requested_by` (null = made in the gateway panel) · `created_at` · `done_at` |
| `commerce_order_reminders` | PK (`order_id`, `kind`) · `sent_at` |
| `commerce_invoices` | `id` · `order_id` · `kind` · `ref` (unique; `"{org_short}-{order_id}-{kind}-{n}"`) · `status` · `number` · `series` · `access_key` · `verification_code` · `pdf_path` · `xml_path` (private bucket copies, kept for the D30 5-year fiscal retention) · `rejection` jsonb · `issued_at` · `cancelled_at` · `provider` |
| `commerce_store_profiles` **adds** | `installments_max` (1–12, default 12) · `installments_interest_free` (1..max, default 3) · `installment_interest_monthly_bps` (nullable — null follows the platform default, §7 / D41) · `inscricao_municipal` · `inscricao_estadual` · `municipio_ibge` · `nfse_mode` · `nfse_cutover` jsonb `{requested_at, approved_at, approved_by, previous_mode, validation_until}` · `invoice_company_ref` · `certificate_valid_until` · `certificate_cnpj` · `auto_issue_invoices` bool default false. Per-company provider tokens are NOT here — they live in the encrypted credentials table (§4) |

### 2.4 Rules
- **Installments (D33):** quote lists `installment_options` for card, counts `1..installments_max`; `≤ installments_interest_free` ⇒ buyer pays the order total; above ⇒ Price-table total at `installment_interest_monthly_bps`. Rounded to the cent; the last installment absorbs the remainder.
- **Refunds (D32):** `create_refund` runs in one transaction: `SELECT … FOR UPDATE` on the order (RPC), recompute refundable **server-side** = paid charge `amount_cents` − Σ non-failed refunds (cross-checked against `get_charge().refunded`), refuse a second refund while one is `requested` (409 `estorno_em_andamento`), honor the `Idempotency-Key` header. Then `refund_charge` ⇒ `done`; gateway error ⇒ `failed` + 502 `estorno_falhou`.
- **Webhook ↔ API reconciliation:** on any refund / partial / dispute event the handler calls `get_charge` and compares `GatewayCharge.refunds` with `commerce_refunds`: matches by `gateway_refund_id` mark rows `done`; any gateway refund with no row (made in the Asaas panel) becomes a `done` row with `requested_by=null`, `reason='gateway'`. Order status is derived from the totals.
- **Chargeback (D34):** `chargeback_opened` ⇒ `disputed` + `on_paused` + staff alert (e-mail to `contact_email` + order event); `won` ⇒ back (`on_resumed`); lost ⇒ `chargeback` + `on_revoked`. Job **`commerce_dispute_poll`** (every 6 h) calls `get_charge` on `disputed` orders to catch a loss with no webhook.
- **Expiry + recovery (D35):** jobs `commerce_expire_orders` (hourly; past-`expires_at` `pending_payment` ⇒ `expired` + `on_expired`; the `charge_failed/overdue` webhook does the same — first wins) and `commerce_expiry_reminders` (hourly; `before_expiry` 24 h before, `after_expiry` 24 h after; the link is a **signed, expiring `access_links` token**, not the bare order token; at most one e-mail per recipient per hour).
- **Regenerate payment (public):** conditional update on `(status, charge_attempts)` so two concurrent calls cannot both create a charge; max **5 attempts per order**, **≥60 s** between attempts (429 `muitas_tentativas`), rate limit `DEFAULT_PORTAL_RL` per IP+token. Order: `cancel_charge` on the current attempt — **if the cancel fails, refuse with 409 `cobranca_anterior_ativa`** (no second live charge) — then a new attempt ⇒ `expired|failed → pending_payment`. A method switch from `pending_payment` creates a new attempt with **no status change**; same method with an unexpired charge returns the existing one. If a superseded attempt is paid anyway (late Pix / boleto), the order records the extra payment, alerts staff and suggests a refund — never silent. Closes `NOC-REMEDIATE[commerce-regenerate-payment]` + `[commerce-gateway-cancel]`.
- **Fiscal purge (D30):** job `commerce_fiscal_purge` (daily) calls `purge_expired_fiscal_retention`. Closes `NOC-REMEDIATE[commerce-fiscal-purge-schedule]`.
- **Invoices (D36/D37):** on `→ paid`, if `auto_issue_invoices`, enqueue (jobs worker) one invoice per tax treatment present: `service_nfse` → `nfse`, `goods_nfe` → `nfe`; `rights_receipt` → none here (P5 receipt/certificate); `none` → none. On `authorized`, copy PDF + XML into the private bucket. Full refund or lost chargeback ⇒ enqueue cancel; a provider refusal (cancel window) records `rejection` + alerts staff.
- **NFS-e mode (D37):** `tax_regime ∈ {mei, simples}` ⇒ forced `nacional`; `municipal` ⇒ 422 `nfse_nacional_obrigatorio`. Other regimes default `municipal` and switch only via the cutover endpoint (D19; `KB § CONTEXT/PATTERNS/architect/approved-cutover.md`); the rollback to `municipal` during `validation_until` (default +60 days) is org-admin only and recorded in `nfse_cutover`.
- **Finance bridge (slice B owns it, not D):** through the `FinanceBooking` seam (§3.5) only — `→ paid` (`confirmed`) ⇒ `book_receivable`; `charge_paid/received` (or gateway sync) ⇒ `book_settlement(kind=payment)` with net + fee, **per installment credit for cards** (cash is booked when money is available, not when the card is approved); each `done` refund / lost chargeback ⇒ `book_settlement(kind=refund, external_ref=<refund id>)`.

### 2.5 Staff API additions (org admin unless marked "staff")
| Method + path | Body | Returns `data` |
|---|---|---|
| `GET /api/commerce/orders/{id}` (staff) | — | order + `charges`, `refunds`, `invoices`, `reminders` |
| `POST /api/commerce/orders/{id}/refunds` | `{amount_cents?, reason}` + header `Idempotency-Key` | refund (422 `valor_excede_saldo`, 409 `pedido_nao_reembolsavel` / `estorno_em_andamento`, 502 `estorno_falhou`) |
| `POST /api/commerce/orders/{id}/invoices` | `{kind}` | invoice (issue, or retry a rejected one) |
| `POST /api/commerce/invoices/{id}/cancel` | `{reason}` (≥15 chars) | invoice |
| `GET /api/commerce/fiscal` (staff) · `PUT /api/commerce/fiscal` | fiscal fields + `expected_version` | fiscal view — never includes provider tokens (422 `nfse_nacional_obrigatorio`) |
| `POST /api/commerce/fiscal/certificate` | multipart `.pfx` (**≤ 64 KB**) + `password` (≤ 128 chars) | `{certificate_valid_until, certificate_cnpj}`. The `.pfx` is opened locally (`cryptography` pkcs12) to read CNPJ + expiry; CNPJ ≠ store CNPJ ⇒ 422 `certificado_cnpj_divergente` **before** anything is sent; bad file/password ⇒ 422 `certificado_invalido` (generic). Then forwarded; never persisted (D38) |
| `POST /api/commerce/fiscal/nfse-cutover` | `{confirm: "MIGRAR PARA NFS-E NACIONAL"}` | fiscal view |
| `POST /api/commerce/fiscal/nfse-cutover/rollback` | `{confirm: "VOLTAR PARA NFS-E MUNICIPAL"}` | fiscal view (only within `validation_until`) |

### 2.6 Storefront API additions (public)
- `POST /api/storefront/checkout/quote` adds `installment_options: [{count, installment_cents, total_cents, interest_free}]` (card only).
- `POST /api/storefront/checkout` adds `installments: int = 1` (422 `parcelamento_invalido`).
- `POST /api/storefront/orders/{token}/payment` `{payment_method, installments?}` ⇒ `{status, checkout_url?, pix_qr?, expires_at}` — rules in §2.4; otherwise 409 `pedido_nao_pagavel`.
- Invoice webhook `POST /api/webhooks/invoices/{provider}/{org_id}`: per-org token in a **header** (never the query string), constant-time compare, fail-closed when unset; the `ref` must belong to `{org_id}`; inbox key `(provider, ref + ":" + status)`; the handler then calls `get(kind, ref)` and trusts only that (never the body's status / URLs).

---

## 3 · Finance organ (`noctusai_lib.domain.finance`, new) — slice C (model, service, API) + slice D (import, reconciliation, export)

Product-agnostic. `FinanceConfig(schema, table_prefix="fin_", org_id_expr=...)`; `finance_migration(cfg, schema) -> str` rendered into each consumer's migration + parity test. Router factory `make_finance_router(cfg, auth_dependency, admin_dependency)` at `/api/finance`. igig's later migration keeps its `fatura`/`fatura_item` (receivable + line items) and books one receivable per fatura (`source_ref = fatura.id`).

### 3.1 Enums
`AccountKind` = `checking` · `savings` · `cash` · `gateway` · `credit_card` · `investment` · `EntryDirection` = `payable` · `receivable` · `EntryStatus` = `open` · `partial` · `paid` · `cancelled` (`overdue` **computed on read**) · `CategoryDirection` = `income` · `expense` · `transfer` · `Frequency` = `daily` · `weekly` · `biweekly` · `monthly` · `bimonthly` · `quarterly` · `semiannual` · `annual` · `EntrySource` = `manual` · `recurrence` · `installment` · `commerce_order` · `import` · `external` · `SettlementKind` = `payment` · `refund` · `LedgerOrigin` = `settlement` · `fee` · `transfer` · `adjustment` · `opening` · `StatementFormat` = `ofx` · `csv` · `MatchStatus` = `unmatched` · `suggested` · `matched` · `ignored`.

### 3.2 Tables
| Table | Key columns |
|---|---|
| `fin_accounts` | `id` · `name` · `kind` · `bank_code` · `agency` · `number` · `opening_balance_cents` · `opening_date` · `gateway` · `active` · unique (org, `gateway`) where `kind='gateway'` |
| `fin_categories` | `id` · `parent_id` · `name` · `direction` · `is_default` · `active` · unique (org, parent, lower(name)); defaults seeded per org on first use |
| `fin_cost_centers` | `id` · `code` (unique per org) · `name` · `active` |
| `fin_entries` | `id` · `direction` · `status` · `description` · `counterparty_name` · `counterparty_doc` (CPF/CNPJ — LGPD, see §3.3) · `category_id` · `cost_center_id` · `expected_account_id` · `competence_month` (day 1) · `due_date` · `amount_cents` (>0) · `settled_cents` · `source` · `source_ref` (unique per org+source when not null) · `recurrence_id` · `installment_group_id` · `installment_n` · `installment_total` · `notes` · timestamps |
| `fin_recurrences` | `id` · `template` jsonb · `frequency` · `next_date` · `end_date` · `active` — generation idempotent on (`recurrence_id`, `due_date`) |
| `fin_settlements` | `id` · `entry_id` · `account_id` · `kind` · `settled_on` · `amount_cents` (>0) · `fee_cents` (≥0) · `method` · `external_ref` (gateway payment id for payments, refund id for refunds) · `statement_line_id` · `created_by` · `reversed_at` · `reversed_by` · `reversal_reason` — partial unique (`kind`, `external_ref`) where not null. **Never deleted**: a reversal sets `reversed_*` and books opposite ledger rows |
| `fin_ledger` | `id` · `account_id` · `occurred_on` · `direction` (`in`·`out`) · `amount_cents` (>0) · `origin` · `settlement_id` · `transfer_group` · `reverses_id` · `description` · unique (`settlement_id`, `origin`) where `settlement_id` not null and `reverses_id` is null |
| `fin_statement_imports` | `id` · `account_id` · `format` · `filename` · `sha256` (unique per account; 409 `extrato_ja_importado` never reveals other accounts) · `period_start` · `period_end` · `imported_by` · `at` |
| `fin_statement_lines` | `id` · `import_id` · `account_id` · `posted_on` · `amount_cents` (signed) · `description` · `fitid` (unique per account; CSV: hash of account + date + amount + description + **line position**) · `match_status` · `ledger_id` (unique when not null) · `suggested_entry_id` |
| `fin_attachments` | `id` · `entry_id` · `storage_path` (server-generated, org-prefixed, via `noctusai_lib.integrations.storage`) · `filename` · `content_type` · `size_bytes` · `uploaded_by` · `at` |
| `fin_gateway_sync` | `account_id` PK · `cursor` · `last_synced_at` · `last_error` |

### 3.3 Rules
- Installments by integer division; the last absorbs the remainder.
- `settled_cents` = Σ unreversed payment − Σ unreversed refund settlements; status recomputed (`open` / `partial` / `paid`). A settlement books ledger rows: net on the account (`settlement`) + `fee` `out` when `fee_cents > 0`.
- Every finance write checks that referenced ids (`account_id`, `category_id`, `cost_center_id`, `entry_id`) belong to the caller's org — beyond RLS.
- Transfers = two ledger rows sharing `transfer_group`; never an entry.
- Cash flow = realized (ledger) + projected (open entries by `due_date`); DRE by `competence_month` × category tree; aging = overdue receivables by counterparty.
- Cancelling an entry with unreversed settlements ⇒ 409 `lancamento_com_baixa`.
- **LGPD:** `counterparty_doc` is masked in lists and CSV exports (`***.456.789-**`) unless the caller is org admin; flagged via `noctus.dev.lgpd_flag`; kept as a fiscal record under the D30 retention rule; a commerce privacy deletion does not erase finance rows of paid orders (art. 16 II), mirroring D30.

### 3.4 API (`/api/finance`; reads = staff, writes + exports = org admin)
| Method + path | Notes |
|---|---|
| `GET/POST /accounts` · `PATCH …/{id}` · `GET …/{id}/balance?on=` | |
| `GET/POST /categories` · `PATCH/DELETE …/{id}` | in use ⇒ 409 `categoria_em_uso` |
| `GET/POST /cost-centers` · `PATCH …/{id}` | |
| `GET /entries?direction=&status=&overdue=&from=&to=&category_id=&cost_center_id=&q=&page=` · `POST` · `GET/PATCH …/{id}` · `POST …/{id}/cancel` | `POST` with `installments: n` creates the group |
| `POST /entries/{id}/settlements` · `POST /settlements/{id}/reverse {reason}` | |
| `GET/POST /recurrences` · `PATCH …/{id}` | job `finance_generate_recurrences` (daily) |
| `POST /transfers` | |
| `GET /reports/cashflow?…` · `GET /reports/dre?…` · `GET /reports/aging` | |
| `POST /statements` (multipart `file` ≤ **5 MB**, ≤ 50k lines, checked before parsing; `account_id`) · `GET /statements/{id}/lines` · `POST /statement-lines/{id}/match {entry_id}` · `POST …/{id}/ignore` | OFX 2.x via **`defusedxml`** (DTD/entities forbidden); OFX 1.x SGML via our own bounded parser; CSV with a column map. Auto-suggest: same amount, ±3 days, same direction. **Match order:** link to an unreconciled `fin_ledger` row first (no new money); create a settlement only when the entry is still open (fixes erp-imobiliario's never-paid defect without double-booking what commerce or gateway sync already settled) |
| `POST /accounts/{id}/gateway-sync` | pulls `list_balance_transactions` into the gateway account; rows not already booked by the commerce bridge listed for review; job `finance_gateway_sync` (every 6 h; failures in `last_error`, retried next tick) |
| `GET/POST /entries/{id}/attachments` · `DELETE /attachments/{id}` | 10 MB cap; pdf/png/jpg/xml validated by **magic bytes** (`media.validate_upload` precedent); served `Content-Disposition: attachment` via signed URL ≤ 10 min |
| `GET /exports/entries.csv?…` · `GET /exports/ledger.ofx?account_id=&from=&to=` | CSV cells starting with `= + - @ \t \r` get a `'` prefix; row cap 50k; org-scoped |

### 3.5 Seam for other organs
`FinanceBooking` Protocol (`domain/finance/booking.py`): `book_receivable(org_id, *, source, source_ref, description, counterparty_name, counterparty_doc, amount_cents, competence_month, due_date, category_hint) -> entry_id` (idempotent on `source`+`source_ref`) · `book_settlement(org_id, *, source, source_ref, kind, external_ref, amount_cents, fee_cents, settled_on, account_hint="gateway:asaas")` (idempotent on `kind`+`external_ref`). `NoopFinanceBooking` for products without finance; `make_finance_booking(...)` factory.

---

## 4 · Invoice organ (`noctusai_lib.integrations.invoices`, new) — slice E

`InvoiceProvider` Protocol + `FakeInvoiceProvider` + `FocusNFeInvoiceProvider` (`httpx`, Basic auth) + `make_invoice_provider(provider, use_fake, ...)` (fake-or-refuse). `types.py` owns `InvoiceKind` (`nfe`·`nfse`), `InvoiceStatus` (`processing`·`authorized`·`rejected`·`cancelled`·`error`), `NfseMode` (`nacional`·`municipal`). Lifted from `products/adconnect/backend/app/services/nfe_service.py` with its defects fixed: lookups/cancel by **our `ref`**; **no silent `pendente`** (unknown status ⇒ `InvoiceProviderError(code="unknown_status")`, 404 ⇒ `InvoiceNotFound`); **no `exc` logging of HTTP errors** (adconnect `nfe_service.py:293,352,374` log raw exceptions).

| Method | Returns |
|---|---|
| `verify_credentials()` | None / raises |
| `ensure_company(CompanyRequest)` | `ProviderCompany{ref, cnpj, nfse_mode, nfe_enabled, nfse_enabled, company_token}` — Focus `POST/PUT /v2/empresas`; `nfse_mode` maps to `habilita_nfsen_*` vs `habilita_nfse` |
| `upload_certificate(company_ref, *, pfx: bytes, password: str)` | `CertificateInfo{valid_until, subject_cnpj}` — bytes + password live only for the call |
| `set_nfse_mode(company_ref, mode)` | `ProviderCompany` |
| `issue(InvoiceRequest)` | `InvoiceResult` — idempotent on `ref`; NF-e `/v2/nfe`, municipal NFS-e `/v2/nfse`, NFS-e Nacional `/v2/nfsen` |
| `get(kind, ref)` · `cancel(kind, ref, *, reason)` | `InvoiceResult` |
| `fetch_document(url) -> bytes` | for the private-bucket copy |
| `parse_webhook(headers, body, *, token)` | `InvoiceEvent{ref, kind, status_hint, raw}` — header token, constant-time, fail-closed; `status_hint` is never authoritative (§2.6) |

Types: `CompanyRequest{cnpj, legal_name, trade_name, inscricao_municipal, inscricao_estadual, tax_regime, address, email, nfse_mode, enable_nfe}` · `InvoiceRequest{ref, kind, company_ref, issued_on, competence, taker{name, doc, email, address}, items[{description, quantity, unit_cents, total_cents, service_code, nbs_code, cfop, ncm, c_class_trib}], total_cents, iss_rate_bps, iss_retained, ibs_cbs: dict | None, additional_info}` · `InvoiceResult{ref, kind, status, number, series, access_key, verification_code, pdf_url, xml_url, rejection_reasons, raw}` (`raw` scrubbed of tokens).
**Credentials:** the Focus account token is platform tier (`resolve_credential("focusnfe_token")`); per-company tokens from `/v2/empresas` are stored encrypted per org (`noctusai_lib.security.encrypted_tokens` + `credential_resolvers`), never returned by any API, rotated on CNPJ change.
**Production guard (D36):** `producao` requires BOTH env `FOCUSNFE_ALLOW_PRODUCTION=1` AND a platform-tier credential `focusnfe_environment=producao`; the environment comes from config, never from a request; the adapter refuses a mismatch between token tier and environment.
**Tests:** Fake round-trip (issue → authorized → cancel; rejection; idempotent re-issue) · Focus adapter on recorded `httpx.MockTransport` fixtures · a test asserting no log record or exception payload contains the certificate bytes, password or tokens · one opt-in live homologação test (skipped without a token). `security` agent reviews before integrate.

---

## 5 · Frontend organ additions (`@noctusai/lib`) — slice F
`commerce/`: `RefundDialog` · `OrderMoneyPanel` (charges, refunds, invoices, reminders) · `InstallmentsSettings` · `FiscalSettingsForm` (regime-aware NFS-e mode, certificate upload, cutover + rollback danger dialogs with typed phrase) · storefront `InstallmentPicker` + order-page "gerar novo pagamento". `finance/` (new organ): `createFinanceHooks(apiBase)` · `EntriesTable` · `EntryForm` · `SettleDialog` · `AccountsManager` · `CategoryTree` · `CostCenters` · `CashflowChart` · `DreTable` · `AgingTable` · `StatementImport` + `ReconcileList` · `AttachmentsField` · `ExportMenu`. Two-signal loading everywhere; admin-only actions hidden for staff (server still enforces).

## 6 · Host product `products/commerce` — slice F
New migration (number via `noctus.dev.next_migration_number`) with the P4 commerce tables + `finance_migration` output + the jobs table if not present + parity tests; mount `make_finance_router`; register scheduler jobs `commerce_expire_orders`, `commerce_expiry_reminders`, `commerce_dispute_poll`, `commerce_fiscal_purge`, `finance_generate_recurrences`, `finance_gateway_sync` (`app/scheduler.py` + lifespan) and the jobs worker for invoices; pages `/admin/financeiro/*` + `status_pagina` rows (`desenvolvimento`); settings `FOCUSNFE_TOKEN`, `INVOICES_ALLOW_FAKE` (environment from the platform credential, §4).

## 7 · Open points
1. ~~Buyer interest default~~ — **answered D41**: platform default **1.99 % a.m.**, swappable without a code change. Resolution order: the store's `installment_interest_monthly_bps` (nullable; null = follow the platform) → platform-tier credential/setting `commerce_installment_interest_bps` (`resolve_credential`) → code constant `DEFAULT_INSTALLMENT_INTEREST_BPS = 199`. Changing the platform value affects new quotes only; a created charge keeps the total it was quoted.
2. **Slice A — Asaas "dispute lost" signal** (§1.3).

## 8 · Wave plan + collisions
Wave 1 = A (`integrations/payments/**`), C (`domain/finance/**`, model + service + API), E (`integrations/invoices/**`) — file-disjoint. Shared generated files (KB counts, `catalog.md`, seed barrels / `__init__` exports) may collide: the tech-lead re-runs gates on the merged tip. Wave 2 = B (commerce money states + finance bridge) and D (statement import, reconciliation, gateway sync, exports — inside `domain/finance/**` new files). Wave 3 = F.

## 9 · Wave-1 deltas (as shipped 2026-10-14 — these override the sections above)

| # | Section | Shipped | Why |
|---|---|---|---|
| W1 | §1.1 types | `PaymentMethod` for integrations is `Literal["pix","boleto","credit_card","undefined","other"]` in `integrations/payments/types.py` (same strings as the commerce enum) | integrations never import domain |
| W2 | §1.1 / §2.4 refunds | **Asaas refunds carry no id** (`GatewayRefund.id_at_gateway is None`). Slice B reconciles Asaas refunds by amount + timestamp against `GatewayCharge.refunds`; `commerce_refunds.gateway_refund_id` stays nullable and is only unique when set (Stripe) | Asaas API shape (`ASAAS-EVENTS.md`) |
| W3 | §1.3 / §2.4 disputes | **Asaas has no "dispute lost" webhook** — a loss is only `chargeback.status == "DISPUTE_LOST"` on the payment, which `get_charge` reports as `chargeback`. `commerce_dispute_poll` is REQUIRED, not a fallback. `DONE` is not treated as lost | docs.asaas.com/docs/chargeback |
| W4 | §1.1 statuses | Asaas `partially_refunded` is derived from `refunds[]`; `deleted: true` ⇒ `cancelled`; `REFUND_REQUESTED`/`REFUND_IN_PROGRESS` read as `received`. `installment_count` on `get_charge` costs one extra `GET /installments/{id}` | Asaas has no such statuses |
| W5 | §3.2 uniques | every unique is org-scoped: `(org_id, kind, external_ref)` etc.; money columns BIGINT | tenancy |
| W6 | §3.3 fees | the `settlement` ledger row is the GROSS settled amount; the `fee` row is OUT — net effect = amount − fee | |
| W7 | §3.5 | `book_settlement` returns the settlement id and creates the gateway account on demand; a replay returns 200 and heals missing ledger rows | |
| W8 | §3.4 | `make_finance_router(cfg, auth_dependency, admin_dependency, *, resolve_context, get_db, get_storage)`; `POST /entries` always returns a list (an installment group returns every installment) | |
| W9 | §3 open markers | `NOC-REMEDIATE[finance-settle-overpay-race]` → **slice B** (settle + reverse join the refund `FOR UPDATE` RPC shape) · `[finance-attachment-download-disposition]` (needs `StorageBackend.signed_url(download=)`; XML stored as octet-stream meanwhile) · `[finance-report-sql-aggregates]` · `finance-doc-retention-purge` (LGPD entry) | |
| W10 | §4 tokens | `ProviderCompany` has **no token field**; the provider hands per-company tokens to an injected `token_sink` (`CompanyTokenStore.sink_for(org_id)`), read back via `resolver_for`. Use one provider instance per request/org | security B3 |
| W11 | §4 certificate | `inspect_pkcs12(pfx, password, *, expected_cnpj=None)` enforces 64 KB / 128 chars / private key present and raises `InvoiceCertificateCnpjMismatch` (`certificado_cnpj_divergente`); `upload_certificate(..., expected_cnpj=)` too — the host's §2.5 check is now by construction | security S1 |
| W12 | §4 | `get`/`cancel` take optional `company_ref`; NFS-e lookups probe `/v2/nfsen` then `/v2/nfse` (finds pre-cutover documents); `ref`/`company_ref` validated `^[A-Za-z0-9_-]{1,64}$`; `InvoiceEvent.kind` may be `None` (Focus bodies don't say) | |
| W13 | §6 host | slice F adds the finance attachment path to `max_body_path_overrides` and registers `finance_generate_recurrences` (`generate_due_recurrences`) | |

Several Focus NFS-e Nacional field names and the webhook body shape are `UNVERIFIED:` in `focus.py` — the opt-in live homologação test settles them once a token exists (P6).

## 10 · DRE design (2026-10-14 — replaces the category-tree DRE of §3.3/§3.4)

> Source research + every provisional choice: `ACCOUNTANT-QUESTIONS.md`. Owner decisions D42–D51. **Provisional choices are data (a per-store mapping), never code** (D48), so an accountant can change them without touching money records.

### 10.1 Structure (D42 — NBC TG 1002 §5.1; NBC TG 1001 shape above R$4.8M)
`DreLine` enum, in statement order, with subtotals computed (never stored):
`gross_revenue` (a) · `deductions` (b) · **= net_revenue** (c) · `cost_of_sales` (d) · **= gross_result** (e) · `selling_expenses` (f) · `administrative_expenses` (g) · `other_operating` (h, +/−) · **= result_before_financial** (i) · `financial_revenue` (j) · `financial_expenses` (k) · **= result_before_income_taxes** (l) · `income_taxes` (m) · **= net_result** (n). Plus `unclassified` — shown in its own block, never silently dropped, with a warning (D47).
- Expenses by **function** (f/g/h) with each category as a detail row (D49). NBC TG 1002 §5.1 says lines "que apresentem valores relevantes" — zero lines are shown greyed with their help text, not hidden, so the owner learns the structure.
- **Standard switch:** trailing-12-month `gross_revenue` > R$4,800,000 ⇒ a warning that the store falls under NBC TG 1001 (expenses by function is then mandatory — already our shape) + a "talk to an accountant" alert.

### 10.2 Where each money fact lands
| Fact | Source of the number | DRE line | Status |
|---|---|---|---|
| Sale (order price, without buyer interest) | receivable `book_receivable` | category's line (default `gross_revenue`) | sourced |
| **Installment interest** charged to the buyer (D45) | booked as a SEPARATE receivable (`source_ref=<order>:interest`) at `→ paid` | `financial_revenue` | provisional — Q2 |
| Refunds / cancellations / discounts | `done` refund settlements on commerce receivables | `deductions` | sourced (Lei 6.404 art. 187 I; NBC TG 1002 §23.2; LC 123 art. 3 §1) |
| **Chargebacks** (D46) | lost-dispute refund settlements | `deductions` | provisional — Q3 |
| **Gateway fees** (D44) | `fin_settlements.fee_cents` (and gateway-sync fee rows) | `selling_expenses` | provisional — Q1 |
| **DAS** (D51) | payable in a category flagged `das` | **`unclassified` until set** ("awaiting classification" alert) | open — Q4 |
| Cost categories (D50) | payables in categories with `dre_line=cost_of_sales` | `cost_of_sales` | provisional — Q5 |
| Any category with no `dre_line` | — | `unclassified` + warning | — |

The DRE stays **accrual by `competence_month`** (Lei 6.404 art. 187 §1; NBC TG 1002 §25.1); refunds, chargebacks and fees take the competence month of the settlement that produced them.

### 10.3 Mapping (per store, data)
- `fin_categories.dre_line` (nullable `DreLine`) + `fin_categories.is_cost` folded into `dre_line=cost_of_sales`.
- `fin_dre_settings` (one row per org): `gateway_fee_line` (default `selling_expenses`), `installment_interest_line` (default `financial_revenue`), `chargeback_line` (default `deductions`), `das_line` (default NULL = awaiting), each with `provisional bool default true`, `confirmed_by`, `confirmed_at`, `note` — an accountant's confirmation clears `provisional`.
- Default category → line proposal: **pending owner review (Q7)** — see the table the tech-lead brought to the owner on 2026-10-14; not built until answered.

### 10.4 Guidance (D47) — part of the API, not only UI copy
`GET /api/finance/reports/dre` returns, besides lines/subtotals: `help` (per line: plain-language pt-BR "o que é", example, source citation) · `warnings[]` (`{code, severity, message, action}` — e.g. `categoria_sem_linha_dre`, `das_aguardando_classificacao`, `escolha_provisoria`, `limite_microentidade_excedido`, `receita_sem_categoria`) · `accountant_alerts[]` (when a professional is needed, and why). `GET /api/finance/accountant-checklist` returns every provisional choice + open question with sources (from `fin_dre_settings` + `ACCOUNTANT-QUESTIONS.md` content) and links the DRE CSV + entries CSV + ledger OFX exports.

### 10.5 Accountant review (2026-10-14 — D52–D56; overrides 10.2/10.3 where they differ)
Canonical sources: `KB § PATTERNS/finance/dre-structure.md`.
1. `fin_dre_settings.tax_regime` (`mei` · `simples` · `presumido` · `unknown`, default `unknown`, prefilled from the commerce store profile when present). It drives every default below; `unknown` raises `regime_nao_informado` (replaces `das_aguardando_classificacao`).
2. DAS: Simples → `deductions` + `das_split_irpj_csll bool default false` (true ⇒ the IRPJ/CSLL share, by the Anexo "percentual de repartição" the store enters, goes to `income_taxes`); MEI → `administrative_expenses`; Presumido → revenue taxes `deductions`, IRPJ/CSLL `income_taxes`.
3. `installment_interest_line` default `gross_revenue` (detail row "Juros de parcelamento"); the separate `<order>:interest` receivable stays. **Fix `domain/commerce/finance_bridge.book_receivable`** — today it books one receivable "interest included"; book principal + `:interest` separately.
4. Fees: `gateway_fee_line` (`selling_expenses`), `anticipation_fee_line` (`financial_expenses`), `chargeback_fee_line` (`selling_expenses`), `chargeback_line` (`deductions`) — all provisional.
5. **Simples tax-base report** (`GET /api/finance/reports/simples-base`), separate from the DRE: receita bruta = sales + installment interest, commission NOT netted, minus cancellations/refunds; juros de mora excluded; cash basis (receipt) until 2026-12-31, **invoice/competence basis from 2027-01-01** (Res. CGSN 190/2026 art. 2 §8, arts. 77–78 revoked). Helps the owner check the PGDAS-D number; never files anything.
6. **Managerial view**: contribution margin (variable = deductions + cost_of_sales + variable selling; fixed = administrative + the rest) from the same rows; totals reconcile to `net_result`. Categories carry `behavior` (`variable` · `fixed`, default by line).
7. MEI stores: statement titled "DRE gerencial (MEI não é obrigado a ter DRE)". Transfers never enter the DRE. Profit distribution / owner withdrawals are equity movements, not DRE lines (open — confirm with the contador).
8. No stock control ⇒ `cost_of_sales` = purchases in the month; warning `cmv_por_compras`.
9. Default categories → lines: the D56 table (`KB § PATTERNS/finance/dre-structure.md §2a`).

## 11 · DRE as shipped (2026-10-14, branch `feat/finance-dre` — deltas over §10 / §10.5)

| # | Section | Shipped | Why |
|---|---|---|---|
| X1 | §10.3 | `fin_dre_settings` holds the five line choices as columns (`gateway_fee_line`, `anticipation_fee_line`, `chargeback_line`, `chargeback_fee_line`, `installment_interest_line`) + `tax_regime` + `das_split_irpj_csll` + `das_irpj_csll_share_bps`; the per-choice `provisional / confirmed_by / confirmed_at / note` live in ONE jsonb `choice_meta` (`{choice: {...}}`, absent = provisional). `das_line` (§10.3) is gone — superseded by `tax_regime` (§10.5.1) | one JSON object beats 20 columns; a choice nobody confirmed is provisional by default |
| X2 | §10.2 | `fin_categories` gains `dre_line` (NULL = unclassified), `behavior` (NULL = the line's default) and **`is_das`** (the "category flagged `das`" of §10.2): a payable in an `is_das` category is routed by REGIME (Simples → `deductions`, + the IRPJ/CSLL share → `income_taxes` when split; MEI → `administrative_expenses`; Presumido/unknown → the category's own line). Children inherit the nearest ancestor's `dre_line`/`behavior` | the contract named the flag but no column |
| X3 | §10.1 | `net_result` EXCLUDES the `unclassified` block (reported as `unclassified.net_cents`, `included_in_net_result=false`), so a half-mapped tree never silently moves the bottom line; the warning says so | D47: shown, never dropped, never guessed |
| X4 | §10.4 | `GET /reports/dre?view=statement\|managerial` — the managerial view answers `managerial` (revenue, variable, contribution margin, fixed, other income, net result) INSTEAD of `statement`; both reconcile to `net_result_cents`. New routes: `GET/PUT /dre-settings`, `GET /reports/simples-base`, `GET /accountant-checklist`, `GET /exports/dre.csv` | |
| X5 | §10.5.1 | the regime prefill from the commerce store profile is a HOST seam: `make_finance_router(..., default_tax_regime=lambda ctx: ...)`, used only until the org saves its own settings (the finance organ never reads commerce tables) | organ isolation |
| X6 | §10.5.3 | `FinanceBooking.book_settlement(..., interest_source_ref=)`: a payment/refund of the whole charge goes to the principal entry first and the overflow to `<order>:interest` (second settlement `external_ref=<ref>:interest`, idempotent on its own; the fee rides on the first settlement written). The commerce bridge books the principal (`order.total_cents`) and the interest (`charge − total`) as separate receivables, categories "Vendas" / "Juros de parcelamento". Orders booked BEFORE this change (interest folded into one receivable) are not migrated — finance is not yet in prod | |
| X7 | §10.5.4 | every fee lands on `gateway_fee_line` today: settlement/gateway-sync data does not say antecipação or chargeback-fee apart from MDR. `dre.classify_fee()` is the single seam. **`NOC-REMEDIATE[finance-fee-kind-from-gateway]`** | no invented data |
| X8 | §10.5.5 | `simples-base` approximates the 2027 "faturamento" moment with the receivable's `competence_month`; receipts in 2027 of sales competent up to 2026-12 raise `transicao_caixa_faturamento` (not in any source read) instead of being counted or dropped | open question for the contador |
| X9 | §10.5.9 | existing orgs: the D56 table is applied ONCE (when no category of the org carries a `dre_line`): missing defaults are added, `dre_line`/`behavior`/`is_das` are filled only on DEFAULT rows where NULL. The legacy categories whose split is ambiguous (`Fornecedores`, `Impostos e taxas`, `Serviços de terceiros`) stay NULL → `categoria_sem_linha_dre` asks the owner. A deleted default is never resurrected | non-destructive |
| X10 | §10.2 | a fee on a PAYABLE's settlement (a bank charge for paying a bill) → `financial_expenses` (not `gateway_fee_line`, which is the sale's cost) | practice [publicação profissional]: tarifa bancária = resultado financeiro |
| X11 | §11 / security review | **financial statements are ADMIN-only** (tech-lead decision 2026-10-14): `GET /reports/dre`, `GET /reports/simples-base`, `GET /accountant-checklist` take the admin dependency (401 unauthenticated / 403 non-admin), matching `exports/dre.csv`; `reports/cashflow` and `reports/aging` stay staff-readable. Organ mounts decide admin from the SELECTED org's membership (`noctusai_seed.organ_auth.make_organ_auth`), never the home-org role | a P&L is not a staff-level read; the home-org role leaked admin across orgs |
