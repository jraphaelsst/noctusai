# Commerce seed P4 — money — Project Document

> Living document. Zero-context reader: start with the roadmap `project-history/roadmaps/commerce-seed-2026-10.md` (decisions D1–D40, phases P0–P13), then `projects/commerce-seed-p3/PROJECT.md` (what P3 shipped), then this file. Live tracker: https://claude.ai/artifact/4mn1fH7nk2fsVeKQHdGdr4.

- **Created:** 2026-10-13
- **Last updated:** 2026-10-13
- **Status:** 🟡 Wave 1 merged 2026-10-14 (A payments, C finance, E invoices — merged-tip green); wave 2 (B money states, D reconciliation) next
- **Owner / stakeholders:** noc owner · tech-lead session · architect + security (advisors)
- **Related docs:** roadmap · `projects/commerce-seed-p3/CONTRACT.md` · `KB § PATTERNS/architect/approved-cutover.md` · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `INTEGRATIONS/payments.md`
- **Project slug:** `commerce-seed-p4` (cross-product seed work → `projects/`)

---

## 1. Context & Purpose

P4 makes commerce handle money end to end: the payments organ gains refunds, installments, chargebacks and expiry; a shared seed **finance** module gives every store payables, receivables, cash flow and reconciliation; a seed **invoice** adapter issues NF-e / NFS-e. All as seed organs consumed by `products/commerce` (validated at gate T2).

## 2. Confirmed constraints (owner decisions, 2026-10-13)

- **D32 refunds** — full + partial, refund history per order.
- **D33 installments** — default 3x interest-free (seller absorbs) / max 12x; per-store override in `/admin/loja`.
- **D34 chargeback** — own state `contestado`; delivery paused; admin alerted; back to `pago` if won.
- **D35 expiry** — `expirado` + stock released + reminder e-mails before/after + buyer regenerates payment.
- **D36 invoices** — Focus NFe as Real adapter, **Fake-first, homologação-only, no contract until P6**.
- **D37 NFS-e by regime** — MEI + Simples → NFS-e Nacional from day one (CGSN 191/2026, mandatory 2026-11-01); municipal only for non-Simples stores in own-system cities, whose switch keeps D19's danger alert + Approve.
- **D38 certificates** — A1 .pfx + password forwarded to the provider, never persisted by us.
- **D39/D40 finance** — per-store AP + AR + cash flow + CSV/OFX export; design in §3.

## 3. Finance design (D40) — sources

| Piece | Lifted from | Notes |
|---|---|---|
| Receivables (`competência` vs `vencimento`, idempotent monthly close, DRE, defaulters, CSV) | igig `011_igig_financeiro.sql`, `services/financeiro_service.py` | strongest base (survey 2026-10-13) |
| Gateway fields on the entry, first-settlement-wins transition, webhook record→apply→reprocess | p-studio `003_integracao_bancaria.sql`, `integracao_service.py` | re-express over the seed payments organ + `event_inbox` |
| Cash ledger in integer cents, idempotent payment/refund booking | community `013_ninho_vazio.sql:281` | partial unique indexes on payment / refund ids |
| Bank accounts, hierarchical categories seeded per org, recurrence | personal-finance `001`, `recorrentes_service.py:26` | |
| Payables recurrence + installments | orbity `006_financial_core.sql:93` | orbity never generated installments — we do |
| Statement/movement table shapes | erp-imobiliario `004_mvp_expansion.sql:163` | its matching is rewritten (date tolerance + marks paid); its `referencia` bug not carried |
| Settlement reconciliation | seed `payments/types.py` `FeeBreakdown`, core `050_billing_gateways.sql` | no re-fork |
| **New** | — | OFX/CSV statement parsers, cost centers, receipt attachments, CSV/OFX export |

## 4. Slice plan (contract-first; file-disjoint waves)

| Wave | Slice | Scope | Owner |
|---|---|---|---|
| 0 | **C0 contract** | `CONTRACT.md`: payments Protocol additions, order state machine (+`contestado`, `expirado`, partial refund), finance tables + API, invoice Protocol + `nfse_mode` | tech-lead |
| 1 | **A payments organ** | `ChargeOperations` (get/refund full+partial/cancel/balance feed), installments on one-off checkout, `GatewayEvent.detail` + additive kinds (CONTRACT §1), one-off expiry; split `external_reference` from order id; Fake + Asaas + Stripe parity | backend |
| 1 | **C finance organ** | `domain/finance` SQL generator + service: accounts, categories, cost centers, payables/receivables with recurrence + installments, ledger, attachments | backend |
| 1 | **E invoice organ** | `integrations/invoices`: Protocol + Fake + Focus (NF-e, municipal NFS-e, NFS-e Nacional, company + cert forward), webhooks, `nfse_mode` per org with approved cutover | backend + security review |
| 2 | **B commerce money states** | refunds table + history, `contestado`, `expirado` + stock release, regenerate payment, gateway cancel, reminder + fiscal-purge jobs on the seed scheduler | backend |
| 2 | **D reconciliation + import/export** | gateway sync, OFX/CSV import + matching, CSV/OFX export (paid orders → receivables is slice B via `FinanceBooking`) | backend |
| 3 | **F host + pages** | `products/commerce` wiring + `/admin/financeiro`, refunds UI, installments settings, invoices + certificate upload + cutover button | frontend + backend |

Exit criteria (roadmap P4): Asaas sandbox e2e; invoice Fake round-trip; Focus homologação round-trip.

## 5. Markers this phase closes

- `NOC-REMEDIATE[commerce-regenerate-payment]` (slice B) · `[commerce-gateway-cancel]` (B) · `[commerce-fiscal-purge-schedule]` (B — the seed scheduler `noctusai_lib/api/scheduler.py` already exists, so the P5 "job runner" destination was drift).

## 6. Owner actions (not blocking P4 code)

- Asaas support: does a chargeback reverse the split? (t314)
- Before P6: Focus NFe Growth contract; ask sales about the reseller token for `/v2/empresas` and their NT 009 date.
- Per store at onboarding: A1 certificate, inscrição municipal, tax regime; accountant confirms NBS / cClassTrib / CFOP per product type.

## 7. Open questions

_None open._
