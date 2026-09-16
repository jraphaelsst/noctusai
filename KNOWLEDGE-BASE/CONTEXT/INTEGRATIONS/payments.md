# Payments — recurring billing (consume-side reference)

> Seed organs: `noctusai_lib.integrations.payments` (gateway I/O) +
> `noctusai_lib.domain.payments` (pure business rules). Shipped
> 2026-09-16 (edicao-fotos-contract Slice S5, `ef-s5-payments`) as a
> **replication-to-seed lift** from two existing implementations —
> `products/p-studio`'s Asaas one-off-receivables adapter and
> `products/core`'s live Stripe billing (`stripe_service.py` +
> `billing_service.py`). **Neither existing product was refactored.**
> This organ ships ALONGSIDE both; migrating Core onto it is a separate,
> separately-consented slice. No consumer exists yet — this is a Phase 1
> seed-capability lift; Phase 2 wires an external app onto it.

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

## Why this is NOT `products/core`'s billing

`products/core`'s `stripe_service.py` (thin SDK wrapper, Checkout
Sessions, Customer Portal) and `billing_service.py` (org-scoped
subscription bookkeeping against Supabase, webhook handlers) are LIVE
with real customers. **Untouched by this slice.** The seed organ's
`StripePaymentGateway` covers a narrower, gateway-agnostic surface
(no Checkout Sessions, no Customer Portal — those are UI-adjacent flows
a consumer builds on top) so it can also stand in for Asaas without a
consumer ever branching on gateway name. Migrating Core onto this organ
is future work requiring explicit consent (Core's billing is a
prod-live surface — see `KB § PATTERNS/devops/prod-exposure-consent.md`).

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

## Gaps / not-yet-consumed

No product consumes this yet (Phase 1 seed lift only). Checkout/hosted-page
flows, one-off charges, and Core's live billing migration are explicitly
out of scope for this slice. `RealSupabaseEventInbox` and
`RealSupabaseJobRepository`-style Supabase adapters are shape-only —
the first consumer ships the `payment_gateway_events` migration
(`primary key (gateway, event_id)`) documented in `event_inbox.py`.
