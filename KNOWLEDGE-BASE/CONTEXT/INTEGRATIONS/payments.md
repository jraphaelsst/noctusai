# Payments — recurring billing (consume-side reference)

> Seed organs: `noctusai_lib.integrations.payments` (gateway I/O) +
> `noctusai_lib.domain.payments` (pure business rules). Shipped
> 2026-09-16 (edicao-fotos-contract Slice S5, `ef-s5-payments`) as a
> **replication-to-seed lift** from two existing implementations —
> `products/p-studio`'s Asaas one-off-receivables adapter and
> `products/core`'s live Stripe billing (`stripe_service.py` +
> `billing_service.py`). **Neither existing product was refactored.**
> This organ ships ALONGSIDE both; migrating Core onto it is a separate,
> separately-consented slice. First consumer: `products/store` (one-off
> digital-product checkout, 2026-10-02) — see "One-off hosted checkout" below.

## What ships (seed)

- **`noctusai_lib.integrations.payments`** — Protocol (`PaymentGateway`)
  + Fake (`FakePaymentGateway`) + Real×2 (`StripePaymentGateway`,
  `AsaasPaymentGateway`) + factory (`make_payment_gateway`). Surface:
  `ensure_customer` · `create_subscription` / `get_subscription` /
  `cancel_subscription` · `get_fee_breakdown`. One error type shared by
  both Real adapters: `PaymentGatewayError` (never `HTTPException` — a
  gateway call can happen inside a webhook handler or a background job,
  not only inside an HTTP request; mirrors `products/p-studio`'s
  `ErroProvedor` rationale exactly).
- **`noctusai_lib.domain.payments`** — `SubscriptionState` (a total,
  explicit state machine: `trialing → active → past_due → grace →
  canceled|expired`, `incomplete` for a failed first charge; an
  unrecognized transition raises, never a silent no-op) + `EventInbox`
  (Protocol + Fake + RealSupabase + factory) proving a duplicate
  `(gateway, event_id)` webhook delivery is a no-op. Neither module
  imports `noctusai_lib.integrations.payments` — gateway status
  translation is the CALLER's job, keeping domain rules vendor-blind.
- **Money is `Money` (integer cents + explicit ISO currency), never
  float.** `FeeBreakdown` (`gross`/`fee`/`net`) enforces `gross == fee +
  net` at construction. `Money.from_decimal_reais(Decimal)` is the ONE
  legal on-ramp for a `Decimal` amount (Asaas reports Reais as a decimal
  string) — every other path works in cents from the start.
- **`stripe` SDK is now a seed pyproject dependency** (monolithic-install
  convention, same as `docxtpl`/`resvg-py`/`xhtml2pdf`), lazily imported
  inside `real_stripe.py`'s methods so the Fake path and the module
  import itself never require it.

## Consume recipe

```python
from noctusai_lib.integrations.payments import make_payment_gateway
from noctusai_lib.integrations.payments.types import SubscriptionRequest, Money

gateway = make_payment_gateway(provider="stripe", stripe_api_key=key)  # or "asaas"
customer = gateway.ensure_customer(external_reference=org_id, email=email, name=name)
subscription = gateway.create_subscription(
    SubscriptionRequest(
        external_reference=org_id,
        customer_id_at_gateway=customer.id_at_gateway,
        price=Money(2990, "BRL"),
        plan_ref="price_123",  # Stripe REQUIRES a pre-created Price id; Asaas ignores it
    )
)
fee = gateway.get_fee_breakdown(subscription.latest_charge_id_at_gateway)
assert fee.gross.amount_cents == fee.fee.amount_cents + fee.net.amount_cents
```

Webhook handler shape (idempotency + state machine composed by the consumer):

```python
from noctusai_lib.domain.payments import make_event_inbox, transition, SubscriptionState

inbox = make_event_inbox(supabase_client=db)  # or use_fake=True in tests
if not inbox.claim(gateway="stripe", event_id=event["id"]):
    return  # duplicate delivery — proven no-op, not an error
# ... translate event["data"]["object"]["status"] -> GatewaySubscriptionStatus,
# decide the target SubscriptionState, then:
updated = transition(current_subscription, SubscriptionState.PAST_DUE)
```

## Gateway asymmetry — the design decisions that mattered

- **`SubscriptionRequest.plan_ref` is optional and gateway-specific.**
  Stripe's idiomatic flow bills against a pre-created `Price` object —
  `StripePaymentGateway.create_subscription` REQUIRES `plan_ref` and
  raises `PaymentGatewayError` rather than synthesizing a throwaway
  Product/Price pair (that would pollute the Stripe dashboard's catalog
  per caller). Asaas has no equivalent first-class price catalog; its
  adapter bills directly off `price` / `billing_cycle` / `billing_method`
  and ignores `plan_ref` entirely.
- **Asaas subscription status is coarse by construction, not by
  modeling shortcut.** Asaas' `Subscription` object reports only
  `ACTIVE` / `EXPIRED` / `INACTIVE` — nothing as granular as Stripe's
  `past_due`. `AsaasPaymentGateway` maps `INACTIVE → incomplete` (covers
  both "never billed" and "manually deactivated", which Asaas itself
  does not distinguish at the subscription level). A consumer that needs
  finer-grained payment health inspects the subscription's generated
  `Payment` rows directly — the same status vocabulary
  `products/p-studio`'s `ProvedorAsaas._STATUS` already uses and
  confirmed against the live sandbox (lifted verbatim into
  `real_asaas.py`'s comments rather than re-probed).
- **Stripe reports fees in cents already; Asaas reports Reais as a
  decimal string.** `StripePaymentGateway.get_fee_breakdown` wraps
  `Charge.balance_transaction.{amount,fee,net}` directly.
  `AsaasPaymentGateway.get_fee_breakdown` reads `Payment.{value,netValue}`
  (both decimal-string Reais) and computes `fee = gross - net` via
  `Money.from_decimal_reais` — this is the package's only Decimal→cents
  conversion site.
- **`AsaasPaymentGateway.cancel_subscription` fetches before it
  deletes.** Asaas' `DELETE /subscriptions/{id}` returns only
  `{"deleted": true, "id": ...}`, not a full subscription row — the
  adapter GETs first so the caller still receives a complete
  `GatewaySubscription`, then marks it `EXPIRED` locally rather than
  re-fetching (Asaas may take a moment to reflect the terminal state).

## Why this is NOT `products/p-studio`'s `ProvedorCobranca`

`ProvedorCobranca` is one-off Pix/boleto/card **receivables** against a
real-estate ledger (`Cobranca`, `criar_cobranca`, `buscar_por_referencia`
for outbound-idempotency) — headed toward a Banco do Brasil adapter, not
Stripe/Asaas recurring billing. This package is recurring **subscriptions**
only. `AsaasPaymentGateway` deliberately does NOT import
`ProvedorAsaas`/`ClienteHTTP` (product code is never a seed dependency);
the Asaas status vocabulary is lifted as a documented fact, not a shared
import.

## Core consumes it (edicao-fotos R2, 2026-09-16)

`products/core` bills through this organ since migration `050_billing_gateways`
(written, not applied — owner consent). New subscriptions are
`subscriptions.automation_managed = true`; every row that predates 050 stays
`false` and keeps the old `billing_service.py` webhook handlers, so live legacy
customers see no change. `licenses.source` (`legacy`/`manual`/`subscription`)
is backfilled to `legacy` for every existing row, and the billing flow only
ever revokes `source='subscription'` rows of the subscription being ended.

Where things live in Core: `app/services/billing_context.py` (the DI seam:
gateway + hosted-checkout factories built from UI-entered keys, the
`payment_events` inbox, the PTAX adapter, a clock) ·
`billing_subscriptions.py` (state changes through `transition()`, licenses,
payments + fees) · `billing_webhooks.py` (inbox claim → dispatch → complete,
or `release()` on failure) · `billing_automations.py` (clock-driven sweeps
behind the `billing_automations_enabled` switch and `NOCTUS_SCHEDULERS_ENABLED`)
· `billing_events.py` (tries each configured mode's secret; the mode that
verifies travels with the event) · `routers/billing_admin.py` + `pages/admin/
AdminBilling.tsx` (plans/prices, keys, mode, automations, subscriptions,
payments, webhook URLs).

## Testing

All 86 tests run on Fakes/mocks — zero network, zero Stripe/Asaas keys:

- `tests/integrations/payments/test_types.py` — `Money` rejects float/bool
  amounts, currency-mismatch arithmetic raises, `FeeBreakdown`'s
  `gross == fee + net` invariant.
- `tests/integrations/payments/test_fake.py` — full `PaymentGateway`
  Protocol contract against `FakePaymentGateway`.
- `tests/integrations/payments/test_stripe_gateway.py` — `stripe` SDK
  substituted via `sys.modules` injection (an external-dependency DI
  seam, not a monkey-patch of our own code); covers status mapping,
  `plan_ref`-required guard, and `StripeError → PaymentGatewayError`
  translation.
- `tests/integrations/payments/test_asaas_gateway.py` — `httpx.MockTransport`
  (same convention as `tests/integrations/mailchimp/test_client.py`);
  covers customer reuse, status mapping, fetch-then-delete cancel, and
  Decimal-Reais→cents fee conversion.
- `tests/domain/payments/test_subscription.py` — every legal transition
  (parametrized) + every tested illegal transition raises; terminal
  states have zero legal next states.
- `tests/domain/payments/test_event_inbox.py` — **the duplicate-delivery
  test**: three `claim()` calls for the same `(gateway, event_id)` return
  `True, False, False` and never raise; a different gateway with the same
  `event_id` is NOT a duplicate (composite key); `RealSupabaseEventInbox`'s
  `23505`-unique-violation → duplicate branch is exercised with a scripted
  Supabase-client double (mirrors `RealSupabaseJobRepository`'s own
  shape-only test discipline — no live Postgres in this suite).

## Gaps

One-off charges stay out of scope (p-studio's `ProvedorCobranca`). Asaas has
no trial: Core offers trials through Stripe only and charges Asaas
subscriptions immediately. Stripe's `cancel_at_period_end` is called directly
by Core (`billing_subscriptions.schedule_stripe_cancel`) — not in the Protocol.

## Checkout + webhook parsing (`checkout.py` / `webhook_events.py`)

Shipped 2026-09-16 (products/community Wave 0, Slice P,
`feat/seed-payments-checkout-webhooks`) as two ADDITIVE-ONLY new files —
neither edits `protocol.py` / `factory.py` / `fake.py` / `real_stripe.py` /
`real_asaas.py`, composing the existing Real gateways instead. Landed
concurrently with `feat/ef-r2-billing` (core billing), which consumes and
extends the same package from a different angle; the two branches touch
disjoint files by construction.

- **`HostedCheckout`** — a sibling Protocol to `PaymentGateway`, not a
  wider surface on it: `create_checkout(CheckoutRequest) -> CheckoutSession`.
  `StripeHostedCheckout` / `AsaasHostedCheckout` each COMPOSE a
  `StripePaymentGateway` / `AsaasPaymentGateway` instance (reusing
  `ensure_customer`, the Stripe SDK lazy-import + error-translation
  helpers, and the Asaas HTTP primitive — never duplicating any of them).
  `FakeHostedCheckout` + `make_hosted_checkout(*, provider, use_fake, ...)`
  mirror `FakePaymentGateway` / `make_payment_gateway`'s shape exactly;
  `make_hosted_checkout` in fact DELEGATES gateway construction to
  `make_payment_gateway` so provider/api-key validation lives once.
  - **Stripe**: a Checkout Session in `mode="subscription"`
    (`stripe.checkout.Session.create`) IS the subscription-creation call —
    `create_subscription` / `stripe.Subscription.create` MUST NOT also run
    on this path (would attempt to bill twice). `plan_ref`,
    `success_url`, and `cancel_url` are all required; `subscription_id_at_gateway`
    on the returned `CheckoutSession` is `None` until the payer completes
    the hosted page (Stripe does not create the `Subscription` resource
    at Session-creation time).
  - **Asaas has no hosted-checkout resource.** `AsaasHostedCheckout`
    reuses `ensure_customer` + `create_subscription` verbatim (a real
    subscription exists immediately, unlike Stripe), then
    `GET /subscriptions/{id}/payments` for the first generated `Payment`
    and returns ITS `invoiceUrl` as the "checkout url". Only
    `billing_method="pix"` or `"boleto"` are accepted (no card
    hosted-checkout equivalent). For `pix`, also fetches
    `GET /payments/{id}/pixQrCode` and returns `PixQr(payload,
    encoded_image, expiration_date)`.
- **`parse_webhook_event(body, headers, *, gateway, stripe_webhook_secret=,
  asaas_webhook_token=) -> GatewayEvent`** — verifies + normalizes one
  inbound webhook delivery. Raises `PaymentWebhookSignatureError` (a new,
  separate type from `PaymentGatewayError` — a bad signature means nothing
  was called, it isn't "the gateway call failed").
  - **Stripe** — `stripe.Webhook.construct_event` (never reimplemented,
    per `noctusai_lib.security.webhook_signatures`'s own docstring naming
    this the one scheme that must go through the vendor SDK). **Finding
    from writing real-signed-payload tests (not a mocked SDK): a genuine
    `stripe.Webhook.construct_event` result is a `StripeObject`, which
    supports `in` / `[]` but NOT `.get()`** — unlike the plain `dict`
    `test_stripe_gateway.py`'s `sys.modules` double returns, and unlike
    what `real_stripe.py`'s own `_to_gateway_subscription` assumes
    (`sub.get("latest_invoice")` etc., only exercised there against that
    same dict-shaped test double). `webhook_events.py`'s `_stripe_field`
    helper does `key in obj else default` instead — works against both a
    real `StripeObject` and a plain dict. Event-type → `kind` mapping:
    `customer.subscription.{created,updated,deleted}` →
    `subscription_updated` (status re-mapped via `StripePaymentGateway.
    _map_status`, imported not re-derived); `invoice.{paid,payment_succeeded}`
    → `charge_paid`; `invoice.payment_failed` → `charge_failed`;
    `charge.refunded` → `charge_refunded`; anything else → `ignored`
    (not an error — a gateway adding an event type later must never 500).
  - **Asaas** — the `asaas-access-token` header, verified via
    `noctusai_lib.security.webhook_signatures.verify_basic_shared_secret`.
    **Finding: Asaas sends the raw configured token VERBATIM in this
    header — no `Basic`/base64 envelope, no username half** (confirmed
    against `docs.asaas.com/docs/webhook-authentication`), which does not
    literally match that helper's `Authorization: Basic
    base64("<user>:<secret>")` input shape. Reused anyway by wrapping the
    raw token in a synthetic empty-username Basic credential
    (`"Basic " + base64(":" + token)`, `expected_username=None`) so the
    constant-time `hmac.compare_digest` call is reused rather than
    duplicated a second time in this module. Event (`event` field) →
    `kind`: `PAYMENT_{CONFIRMED,RECEIVED}` → `charge_paid`;
    `PAYMENT_OVERDUE` → `charge_failed`; `PAYMENT_{REFUNDED,
    CHARGEBACK_REQUESTED}` → `charge_refunded`; anything else →
    `ignored`. **`subscription_updated` never fires on the Asaas path —
    Asaas' webhook catalog is PAYMENT-level only, there is no
    `SUBSCRIPTION_*` event; a consumer that needs the coarse
    ACTIVE/EXPIRED/INACTIVE subscription status polls
    `AsaasPaymentGateway.get_subscription` directly.**
  - **Finding: Asaas webhook payloads carry no stable per-delivery id**
    (no `id`/`eventId` field — confirmed against
    `docs.asaas.com/docs/webhook-events`; the payload shape is bare
    `{"event": ..., "payment": {...}}`). `GatewayEvent.event_id` is
    therefore DERIVED as `f"{event}:{payment_id}:{status}:{moment}"`
    (`moment` = `paymentDate` or `clientPaymentDate` or `dueDate`,
    whichever is present) — a genuine retry of the identical delivery
    produces the same key (dedupes via `EventInbox.claim`), a real status
    change on the same payment produces a different one. This is OUR
    construction, not a gateway guarantee — documented here so a future
    reader doesn't mistake it for one.
  - **`GatewayEvent.inbox_key`** is `(gateway, event_id)` — pass straight
    to `noctusai_lib.domain.payments.EventInbox.claim`. `GatewayEvent.
    subscription_status` (a `GatewaySubscriptionStatus`, the SAME type
    `PaymentGateway.get_subscription` returns — no parallel enum) is
    populated for Stripe subscription events and always `None` for Asaas
    (see above); a consumer maps it to a `SubscriptionState` transition
    itself, same as the existing consume-recipe above.
  - **`make_fake_gateway_event(...)`** — the dev/test seam: builds a
    `GatewayEvent` directly, bypassing `parse_webhook_event` and every
    signature check. Never call it from a real webhook route.

Tests: `tests/integrations/payments/test_checkout.py` (Stripe via a
`sys.modules` double — same DI-on-an-external-dependency seam as
`test_stripe_gateway.py` — plus Asaas via `httpx.MockTransport`; a
protocol-conformance + Fake/Real-parity check) and `test_webhook_events.py`
(Stripe verified against the REAL installed `stripe` SDK with real
HMAC-signed payloads generated from a test secret — no SDK
substitution needed, `construct_event` does pure local verification;
Asaas via a scripted `asaas-access-token` header). 129 payments tests
total (integrations + domain), still zero network / zero real Stripe or
Asaas keys.

## One-off hosted checkout (2026-10-02, `products/store`) — additive

N=2 lift (p-studio `criar_cobranca` + store). `CheckoutRequest.billing_cycle=None`
⇒ a single charge, no subscription; plus `description` and `due_days` (default 3).
`billing_method` gains `"undefined"` (same wire value as `"unspecified"`: Asaas
`billingType=UNDEFINED` — the payer picks PIX / boleto / card on Asaas' page).

- **Asaas** — `ensure_customer(tax_id=cpf)` → `POST /payments` {customer,
  billingType, value, dueDate=`today()+due_days`, description,
  externalReference, `callback:{successUrl, autoRedirect:true}` (only when
  `success_url` is set)} → `CheckoutSession(checkout_url=invoiceUrl,
  id_at_gateway=<pay_...>, subscription_id_at_gateway=None)`. No
  `/subscriptions` call is ever made.
- **Stripe** — Checkout Session `mode="payment"`; line item is `plan_ref` as a
  Price when given, else inline `price_data` (currency/amount from `price`,
  product name = `description`). `success_url` + `cancel_url` required.
- **Fake** — deterministic `pay_000001` ids / URL, no subscription id.
- Webhook parsing is unchanged: `PAYMENT_RECEIVED`/`PAYMENT_CONFIRMED` →
  `charge_paid`; `externalReference` → `GatewayEvent.external_reference`.

Subscription behaviour is byte-identical (the whole payments test dir stays
green). Consumers use only `make_hosted_checkout` + `parse_webhook_event` +
`make_event_inbox`.

## Additions from Core R2 (2026-09-16) — all additive

- `SubscriptionRequest.trial_days` (Stripe `trial_period_days`; Asaas moves the
  first `nextDueDate`), `ensure_customer(..., tax_id=)` (Asaas `cpfCnpj`; it
  refuses to charge a customer without one), `PaymentGateway.verify_credentials()`
  (read-only: Stripe `Balance.retrieve`, Asaas `GET /customers?limit=1`) for the
  admin "test connection" button. `AsaasPaymentGateway(today=...)` is the clock seam.
- `CheckoutRequest.trial_days` + `tax_id`; Stripe checkout now sends
  `payment_method_collection="always"` (card up front even when the trial makes
  the first invoice zero) and `client_reference_id`; Asaas checkout accepts
  `billing_method="card"` (the owner's rule: Asaas = Pix, boleto AND card).
- **`StripeObject` has no `.get()` and `dict(obj)` raises** (stripe 15). All
  Stripe field access goes through `payments/_stripe_fields.py`
  (`stripe_field`, `stripe_to_dict`), shared by `real_stripe`, `checkout` and
  `webhook_events`. `test_stripe_gateway.py`'s double now returns REAL
  `StripeObject`s — against the old adapter it fails 9 tests, which is the point.
- `real_stripe` reads `current_period_end` from the subscription items when the
  top-level field is absent (API 2025-03+), and fetches the balance transaction
  when it was not expanded.
- `FakePaymentGateway` raises `PaymentGatewayError(status=404)` for an unknown
  subscription (was a bare `KeyError`), matching the Real adapters.
- `EventInbox.release(gateway, event_id)` — undo a claim whose processing
  failed, so the gateway's retry is processed instead of read as a duplicate.
- State machine: `trialing → past_due|expired`, `past_due → canceled|expired`,
  `incomplete → canceled|trialing` are legal (Stripe produces each on its own).
- **Asaas event id:** the top-level `id` is used when the payload carries one;
  the derived key is the fallback, and for non-payment deliveries it is built
  from the `subscription` object. Before this, every `SUBSCRIPTION_*` delivery
  derived the same key (`SUBSCRIPTION_DELETED:::`) and the inbox would have
  dropped all but the first. Core acts on `SUBSCRIPTION_DELETED` /
  `SUBSCRIPTION_INACTIVATED` when they arrive; whether the live Asaas account
  emits them is unverified.

## Asaas hosted checkout — the site prerequisite + `check_checkout_readiness` (2026-10-03)

Asaas refuses a `callback.successUrl` (the post-payment redirect-back) unless the account has a website registered. Without it the first checkout fails with `400 invalid_object` — "Não há nenhum domínio configurado em sua conta. Cadastre um site em Minha Conta na aba Informações." `GET /v3/myAccount/commercialInfo` returns `site: null` in that state. Fix is operator-side: **Minha Conta › Informações › Site**.

Every `HostedCheckout` (`noctusai_lib.integrations.payments.checkout`) now exposes `check_checkout_readiness(success_url) -> list[ReadinessIssue]` (`code`, pt-BR `message`, `severity` `error|info`; `readiness_ok(issues)` = no errors). Fake + Real + factory parity:

- **Asaas**: `verify_credentials` first (401 / `invalid_environment` → "Chave inválida ou de outro ambiente (sandbox x produção)"); then `commercialInfo` — missing `site` → error `missing_site`; site present → `info` (`site_registered`) carrying the value. Whether Asaas also demands the callback domain equal the registered site is NOT a documented contract, so a domain mismatch is never raised as an error.
- **Stripe**: credentials only.
- **Fake**: `script_readiness([...])`, calls recorded.

Consumer wiring: store's `asaas_api_key` is `testable`; `app/key_testers.py` runs the check from the admin "Testar" button (seed `ApiKeysPanel` already renders Testar for `testable` keys — no FE change).

### Asaas environments + the readiness verdict, lifted (2026-10-13, commerce organ hardening)

- **Environment selector** — `real_asaas.ASAAS_BASE_URLS` (`sandbox` → `https://api-sandbox.asaas.com/v3`, `production` → `DEFAULT_BASE_URL`) + `asaas_base_url_for(env)`, which REFUSES an unknown name (`ValueError`) rather than falling back to production. An Asaas key belongs to one environment, so a consumer that lets the operator choose maps the choice through this, never a hard-coded URL.
- **`readiness_verdict(checkout, success_url) -> ReadinessVerdict(success, message)`** (`checkout.py`) — the "Testar" fold over `check_checkout_readiness`: no issue ⇒ `READINESS_READY_MESSAGE`; info-only ⇒ ready + the info lines; any error ⇒ not ready, issue lines only; a `PaymentGatewayError` ⇒ failed verdict, logged, never raised.
- **Commerce organ** consumes both: `CommerceConfig.asaas_environment_name` (per-org credential) + `asaas_default_environment` (`sandbox` — unset never moves real money); `AsaasCheckoutGateway.environment(org)` / `checkout_for_key(org, key)`; `noctusai_lib.domain.commerce.probe_api_key_readiness(gateway, cfg, org_id=, api_key=, public_url=)`. The host registers it through the seed `create_api_keys_router(org_testers={...})` seam (a tester that receives `(value, org_id)`), since the probe must run in the CALLER org's environment.
- **Consumer left to migrate:** `products/store` still carries its own `key_testers.py` + `asaas_base_url()` (inactive, slated for retirement — migrate or retire with it).

## One-off charge operations — `ChargeOperations` (2026-10-13, commerce P4 slice A)

Contract: `projects/commerce-seed-p4/CONTRACT.md` §1. New file `integrations/payments/charges.py`; additive — nothing above changed meaning.

- **Protocol `ChargeOperations`** (`get_charge` · `refund_charge(id, *, amount: Money | None, description)` · `cancel_charge` · `list_balance_transactions(*, since, cursor)`), with `FakeChargeOperations` (scriptable: `add_charge`, `mark_paid`, `open_dispute`/`win_dispute`/`lose_dispute`, `add_balance_transaction`), `AsaasChargeOperations`, `StripeChargeOperations`, and `make_charge_operations(...)` — fake-or-refuse, same args/validation as `make_hosted_checkout` (it delegates to `make_payment_gateway`).
- **Types** (`types.py`): `ChargeStatus` (`pending|confirmed|received|overdue|partially_refunded|refunded|disputed|chargeback|cancelled`), `PaymentMethod` (`pix|boleto|credit_card` + `undefined`/`other` for Asaas `UNDEFINED`/debit/transfer — the integrations layer never imports the commerce enum), `GatewayCharge`, `GatewayRefund`, `BalanceTransaction`, `BalanceTransactionPage`.
- **No silent default.** Unknown gateway status ⇒ `PaymentGatewayError(code="unknown_charge_status")`; unknown payment method ⇒ `unknown_payment_method`. The one catch-all is the statement's `other` kind (both vendors document their type lists as open-ended).
- **Guards run before calling out:** refund above `amount − refunded` ⇒ `refund_exceeds_balance`; refund of an unpaid/cancelled/refunded charge ⇒ `charge_not_refundable`; cancel of a paid charge ⇒ `charge_already_paid` (refund it instead).
- **Asaas:** refund `POST /v3/payments/{id}/refund {value, description}` (an explicit value is always sent — `None` means "remaining", computed from the read); cancel `DELETE /v3/payments/{id}`; statement `GET /v3/financialTransactions` (cursor = offset). Asaas lists refunds **without an id** (`GatewayRefund.id_at_gateway is None` — reconcile by amount/time). `partially_refunded` is derived (refund total vs value; Asaas has no such status). A lost chargeback is `payment.chargeback.status == "DISPUTE_LOST"` on `get_charge` — Asaas sends **no** "lost" webhook. Full event/status table + sources: `integrations/payments/ASAAS-EVENTS.md`.
- **Stripe:** accepts `cs_` / `pi_` / `ch_` ids. Refund `POST /v1/refunds`; cancel = expire the Checkout Session or cancel the PaymentIntent; statement `GET /v1/balance_transactions` (cursor = last id). A charge line's fee is split into a separate `<id>:fee` line so ledgers see the same shape from both gateways. `confirmed` vs `received` comes from the balance transaction's `available_on`.
- **`CheckoutRequest` additions:** `installment_count` (default 1; `>1` only for a one-off card charge — Asaas sends `installmentCount` + `totalValue` and returns the FIRST parcela, the parcelamento id is in `raw["installment"]`; Stripe refuses with `installments_unsupported`) and `customer_reference` (when set, `ensure_customer` is keyed on it — one gateway customer per buyer; `external_reference` stays the per-charge conciliation key).
- **`GatewayEvent.detail` + new kinds** (`charge_partially_refunded`, `charge_dispute`, `charge_cancelled`) per CONTRACT §1.3. **Existing kind mappings are pinned unchanged** by `tests/integrations/payments/test_webhook_events_p4.py`. Asaas `PAYMENT_PARTIALLY_REFUNDED` / `PAYMENT_DELETED` moved from `ignored`; Stripe `charge.dispute.created|closed` moved from `ignored` (a `closed` with status other than won/lost stays `ignored`).
