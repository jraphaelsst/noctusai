# Asaas — events, statuses and the "dispute lost" signal (verified 2026-10-13)

Verified against the live Asaas docs while building `charges.py` (commerce P4 slice A).

Sources:
- Webhook events: https://docs.asaas.com/docs/webhook-para-cobrancas
- Chargeback object (`chargeback.status` / `reason`): https://docs.asaas.com/docs/chargeback
- Refund: https://docs.asaas.com/reference/estornar-cobranca (`POST /v3/payments/{id}/refund`, body `value`, `description`, `splitRefunds`; card or Pix only; partial refunds allowed up to the paid total; fees are NOT returned on refund so a full Pix refund right after receipt can 400 for lack of balance)
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
