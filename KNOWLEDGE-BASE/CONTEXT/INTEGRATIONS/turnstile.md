# Cloudflare Turnstile — consume-side reference

> Seed organ: `noctusai_lib.integrations.turnstile`. Shipped 2026-09-16
> (products/community Module 2, `feat/community-m2-backend`, contract
> amendment P2) as a **seed-first capability lift** — no existing
> Turnstile helper was found anywhere in the tree (`grep -ril turnstile`
> across `products/`, `seed/`, `mcp/` returned nothing) before this
> landed, so the Protocol+Fake+Real+factory shipped in the seed directly
> rather than in the consuming product, per the contract's own
> instruction ("if it does not exist, put it in the seed — it is
> reusable by every public form we will ever ship").

## What ships (seed)

- **`noctusai_lib.integrations.turnstile`** — Protocol (`TurnstileVerifier`)
  + Fake (`FakeTurnstileVerifier`) + Real (`RealTurnstileVerifier`) +
  factory (`make_turnstile_verifier`). One verb: `async def verify(token,
  *, remote_ip=None) -> TurnstileVerificationResult`.
- **`TurnstileVerificationResult`** — `success: bool` +
  `error_codes: tuple[str, ...]` (Cloudflare's `error-codes` array,
  forensic) + `raw: dict` (the full `siteverify` JSON response).
- **`RealTurnstileVerifier`** — one HTTP call, no SDK exists to wrap:
  `POST https://challenges.cloudflare.com/turnstile/v0/siteverify` with
  `{secret, response, remoteip?}` as form data. `httpx.AsyncClient`,
  constructor-injectable `transport=` (test seam, mirrors
  `noctusai_lib.integrations.payments.real_asaas`'s convention — zero
  network in this package's own test suite via `httpx.MockTransport`).
  **Fails CLOSED, never open**: any transport error, timeout, or
  malformed JSON body is logged at WARNING and returned as
  `success=False` — never raised. A network hiccup must deny the
  request, not silently let a bot through, and a consumer's router does
  not need a second exception type alongside its `403`.
- **`FakeTurnstileVerifier`** — accepts any non-empty token by default
  (`accept=True`); `accept=False` at construction or
  `.rejected_tokens.add(token)` simulate the failure branch so a
  consumer's own test suite can drive both the 201-happy-path and the
  403-invalid-token path against the SAME instance.
- **`make_turnstile_verifier(*, use_fake=False, secret=None, ...)`** —
  returns the Fake when `use_fake=True` OR `secret` is falsy (same
  early-dev-bypass posture the platform already uses for webhook
  secrets, `bypass_when_unset`), else `RealTurnstileVerifier(secret=...)`.
  The bypass is narrower than the webhook one: an EMPTY token still
  403s even with no secret configured — only a "secret not yet issued"
  gap is bypassed, never a missing submission.

## Consume recipe

```python
from noctusai_lib.integrations.turnstile import make_turnstile_verifier

verifier = make_turnstile_verifier(secret=settings.community_turnstile_secret)
result = await verifier.verify(payload.turnstile_token, remote_ip=request.client.host if request.client else None)
if not result.success:
    raise http_error(403, "Verificação de segurança falhou. Recarregue a página e tente novamente.")
```

Tests inject `FakeTurnstileVerifier` directly (constructor DI — the
`di-test-seam` pattern), never via `make_turnstile_verifier(use_fake=True)`
mid-test, so a test can flip `accept=False` / `rejected_tokens` per case:

```python
service = CheckoutService(client, org_id=org_id, turnstile_verifier=FakeTurnstileVerifier(accept=False))
```

## First consumer

`products/community`'s public `POST /api/checkout` (module 2,
`app/services/checkout_service.py`) — Turnstile is the first of three
abuse-control legs alongside per-email/24h and per-org/hour rate caps
(contract amendments A10/P2). A missing or invalid `turnstile_token`
403s before any gateway call or DB write.

## Gaps

No JS-widget helper ships here (and none should — the frontend's
`VITE_TURNSTILE_SITE_KEY` + the `<div class="cf-turnstile">` widget is a
pure client-side concern, unrelated to this server-side verification
seam). No IP-reputation or bot-score threshold beyond Cloudflare's own
pass/fail — a consumer that later needs Cloudflare's score-based
"managed challenge" tier reads `raw` for the `score`/`action` fields the
Enterprise plan adds; this v1 only uses the boolean `success`.
