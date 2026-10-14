# Asaas — events, statuses and the "dispute lost" signal (verified 2026-10-13)

Verified against the live Asaas docs while building `charges.py` (commerce P4 slice A).

Sources:
- Webhook events: https://docs.asaas.com/docs/webhook-para-cobrancas
- Chargeback object (`chargeback.status` / `reason`): https://docs.asaas.com/docs/chargeback
- Refund: https://docs.asaas.com/reference/estornar-cobranca (`POST /v3/payments/{id}/refund`, body `value`, `description`, `splitRefunds`; card or Pix only; partial refunds allowed up to the paid total; fees are NOT returned on refund so a full Pix refund right after receipt can 400 for lack of balance)
- Refund installment (verified 2026-10-14): https://docs.asaas.com/reference/refund-installment (`POST /v3/installments/{id}/refund`, body `{"value": number}` ONLY -- no `description`; "to perform a full refund, do not provide refund amounts. To refund partially, provide `value`"; credit-card installments in `RECEIVED`/`CONFIRMED` only; the response is the installment object, NOT a refund; "in case of a timeout or inconclusive response, retrieve the installment before repeating the operation"). Partial installment refunds ARE supported. The installment id is `payment.installment` on every parcela.
- List payments of an installment: https://docs.asaas.com/reference/list-payments-of-a-installment (`GET /v3/installments/{id}/payments`, paged `offset`/`limit`/`hasMore`, each item a full payment with its own `refunds[]`). `charges.py` reads a parcelamento through this and folds the parcelas (`get_installment`).
- Refund fields: https://docs.asaas.com/docs/refunds (`refunds[]` item: `dateCreated`, `status` PENDING/CANCELLED/DONE, `value`, `description`, ... -- still NO id)
- Delete: https://docs.asaas.com/reference/excluir-cobranca (`DELETE /v3/payments/{id}`; not a refund; emits `PAYMENT_DELETED`; restorable)
- Statement: https://docs.asaas.com/reference/recuperar-extrato (`GET /v3/financialTransactions`, `startDate`/`finishDate`/`offset`/`limit<=100`/`order`; `type` is open-ended, "do not break on an unknown type")
- Installments: https://docs.asaas.com/docs/criar-uma-cobranca-parcelada (`POST /v3/payments` with `installmentCount` + `totalValue`)

## Event names

Cycle: `PAYMENT_CREATED`, `PAYMENT_AWAITING_RISK_ANALYSIS`, `PAYMENT_APPROVED_BY_RISK_ANALYSIS`, `PAYMENT_REPROVED_BY_RISK_ANALYSIS`, `PAYMENT_AUTHORIZED`, `PAYMENT_UPDATED`, `PAYMENT_CONFIRMED` (paid, balance not yet available), `PAYMENT_RECEIVED` (balance available), `PAYMENT_CREDIT_CARD_CAPTURE_REFUSED`, `PAYMENT_ANTICIPATED`, `PAYMENT_OVERDUE`, `PAYMENT_DELETED`, `PAYMENT_RESTORED`.
Refund / chargeback: `PAYMENT_REFUNDED`, `PAYMENT_PARTIALLY_REFUNDED`, `PAYMENT_REFUND_IN_PROGRESS`, `PAYMENT_REFUND_DENIED` (boleto only), `PAYMENT_RECEIVED_IN_CASH_UNDONE`, `PAYMENT_CHARGEBACK_REQUESTED` ("chargeback received"), `PAYMENT_CHARGEBACK_DISPUTE` ("in dispute after documents were submitted"), `PAYMENT_AWAITING_CHARGEBACK_REVERSAL` ("dispute WON, awaiting the acquirer's transfer").
Others: dunning (`PAYMENT_DUNNING_*`), boleto view/cancel, split (`PAYMENT_SPLIT_*`).

All names used by `webhook_events.py` exist as written.

## Payment `status` enum (`GET /v3/payments/{id}`)

`PENDING, RECEIVED, CONFIRMED, OVERDUE, REFUNDED, RECEIVED_IN_CASH, REFUND_REQUESTED, REFUND_IN_PROGRESS, CHARGEBACK_REQUESTED, CHARGEBACK_DISPUTE, AWAITING_CHARGEBACK_REVERSAL, DUNNING_REQUESTED, DUNNING_RECEIVED, AWAITING_RISK_ANALYSIS`. There is **no partially-refunded status** and no cancelled status (a removed charge has `deleted: true`); `charges.py` derives `partially_refunded` from `refunds[]` and `cancelled` from `deleted`.

## How a LOST chargeback dispute is signalled

**Asaas has no "dispute lost" webhook.** The only chargeback events are `…_CHARGEBACK_REQUESTED` (opened), `…_CHARGEBACK_DISPUTE` (evidence submitted) and `…_AWAITING_CHARGEBACK_REVERSAL` (won). A loss is visible only on the payment object: `payment.chargeback.status` takes `REQUESTED | IN_DISPUTE | DISPUTE_LOST | REVERSED | DONE`, and `DISPUTE_LOST` = lost. The statement also gets a `CHARGEBACK` line (balance blocked); a won dispute adds `CHARGEBACK_REVERSAL`.

Consequence: `AsaasChargeOperations.get_charge` returns `status="chargeback"` for `DISPUTE_LOST` and `disputed` for `REQUESTED`/`IN_DISPUTE` (`REVERSED` = won => the underlying status stands). Slice B's `commerce_dispute_poll` job is therefore REQUIRED, not a nicety, to catch an Asaas loss. Open point: the docs describe `DONE` only as "process concluded"; it is not treated as lost.

Not verifiable from docs alone (sandbox/live check still owed): the exact moment `chargeback.status` flips to `DISPUTE_LOST`, and whether a refunded-by-Asaas Pix shows `REFUND_IN_PROGRESS` before `REFUNDED`.

## Installment (parcelamento) refunds -- what the code relies on, and what is NOT verifiable from docs

* Stripe: a card "installment" is a single PaymentIntent/charge, so the normal `refund_charge` applies; `StripeChargeOperations.get_installment` / `refund_installment` raise `installments_unsupported` (the Stripe checkout seam refuses `installment_count > 1` anyway).
* Asaas: one `POST /installments/{id}/refund` (full: no body value; partial: `value`). The value is "debited from the accounts involved"; how it is DISTRIBUTED over the parcelas is not documented. `get_installment` therefore never assumes a split: it sums `refunds[]` over all parcelas and groups them by `dateCreated` (one refund operation = one `GatewayRefund`, `id_at_gateway=None`, `pending` if any piece is). `dateCreated` is date-granular, so the grouping is NOT trusted for accounting: two same-second operations merge and one operation can carry different stamps across parcelas. Commerce therefore reconciles installment orders by TOTALS only (`gateway refunded - sum(done local)`: `requested` rows settle oldest-first while the delta covers them; one `gateway` row for a leftover positive delta; nothing is inserted for a delta <= 0), and `refund_installment` decides success from `after.refunded - before.refunded >= value`, never from the group count.
* Refund POST outcome: per the Asaas docs a timeout/inconclusive response must be resolved by reading the installment before repeating. A retryable error (timeout/5xx) or anything after the POST was sent leaves the local row `requested` (blocks new refunds with `estorno_em_andamento`; reconcile settles it, or fails it after `STALE_REQUESTED_AFTER`). Only a pre-call refusal (`refund_exceeds_balance`, `charge_not_refundable`, ...) or a non-retryable 4xx marks it `failed`. A failed read-back after the POST returns `pending`, not an error. Same rule for single-charge refunds.
* Webhooks: a refund fires `PAYMENT_REFUNDED` / `PAYMENT_PARTIALLY_REFUNDED` per affected parcela payment id. The commerce webhook handles the stored (first) parcela as the current charge and a later parcela whose gateway read carries this order's `externalReference`; a later parcela is applied only if its gateway read carries this order's `externalReference` AND `installment` equal to the stored parcelamento id; an unknown id (404) or a foreign one is IGNORED + staff alert (never an exception: that would make Asaas retry and pause the queue). Both re-read the WHOLE parcelamento, so the order converges regardless of which parcela's event arrives first.

