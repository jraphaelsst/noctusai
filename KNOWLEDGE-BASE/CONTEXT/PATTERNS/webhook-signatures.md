# Webhook signature verification

> Every inbound webhook the platform receives MUST verify its payload's
> origin before any side effect (DB write, queue enqueue, downstream
> API call). Forging a webhook to drive privileged actions is a
> well-trodden attack path and the cost of verification is trivially
> small — there's no engineering excuse for an unsigned receiver.

## The four shapes

Every external webhook fits one of four shapes. Pick the matching pattern
and STOP. Don't roll your own — the helpers in
`noctusai_lib.security.webhook_signatures` cover three of them, the
fourth uses the vendor SDK.

### 1. HMAC-SHA256 with `sha256=…` prefix (Hub-Signature scheme)

**Used by:** Meta Lead Ads (`X-Hub-Signature-256`), GitHub, generic
custom webhooks that follow Hub-Signature.

**Helper:** `verify_hmac_sha256(body, signature, secret)`

**Sample:**
```python
from noctusai_lib.security.webhook_signatures import verify_hmac_sha256

body = await request.body()
sig = request.headers.get("X-Hub-Signature-256", "")
if not verify_hmac_sha256(body, sig, settings.meta_webhook_secret):
    raise HTTPException(401, "invalid signature")
```

### 2. HMAC-SHA256 hex (no algorithm prefix)

**Used by:** WAHA (`X-Webhook-Hmac-SHA256`), internal NoctusAI-to-NoctusAI
webhooks, simple shared-secret schemes.

**Helper:** `compute_hmac_sha256_hex(body, secret)` (compute then
`hmac.compare_digest` against the header).

**Sample:**
```python
import hmac
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

body = await request.body()
provided = request.headers.get("X-Webhook-Hmac-SHA256", "")
expected = compute_hmac_sha256_hex(body, settings.waha_webhook_hmac_secret)
if not hmac.compare_digest(expected, provided.strip()):
    raise HTTPException(401, "invalid signature")
```

### 3. Svix protocol

**Used by:** Resend (and any provider built on Svix's webhook
infrastructure). Three headers: `svix-id`, `svix-timestamp`,
`svix-signature`. Signed payload is `f"{id}.{timestamp}.{body}"`. Secret
is base64-encoded; Resend prefixes it `whsec_`.

**Helper:** `verify_svix_signature(...)` — handles the `whsec_` prefix
strip, base64 decode, multi-version header parsing.

**Sample:**
```python
from noctusai_lib.security.webhook_signatures import verify_svix_signature

body = await request.body()
if not verify_svix_signature(
    svix_id=request.headers.get("svix-id", ""),
    svix_timestamp=request.headers.get("svix-timestamp", ""),
    body=body,
    signature_header=request.headers.get("svix-signature", ""),
    secret=settings.resend_webhook_secret,
):
    raise HTTPException(401, "invalid signature")
```

### 4. Vendor SDK (Stripe)

Stripe ships its own verifier (`stripe.Webhook.construct_event`) that
also checks the timestamp tolerance. **Use it. Don't wrap it. Don't
reinvent it.**

```python
import stripe
event = stripe.Webhook.construct_event(
    payload=body,
    sig_header=request.headers.get("Stripe-Signature", ""),
    secret=settings.stripe_webhook_secret,
)
```

## Universal rules

- **Verify before parsing.** Read the raw body once, verify, *then*
  parse JSON. Re-encoding parsed JSON changes whitespace and breaks
  the signature.
- **Constant-time compare.** All three lib helpers use
  `hmac.compare_digest` internally so verification time is independent
  of where two signatures diverge — no timing side-channel bug.
  When you compare manually (pattern #2), use `hmac.compare_digest` too.
- **Bypass with a WARNING when the secret is unset.** Dev environments
  often run the bot without the real provider configured. Make the
  unsafe state observable: log
  `<SECRET_NAME> unset — accepting webhook without verification` at
  WARNING and continue. Production deploys must set the secret; CI
  should fail if the env doesn't.
- **One secret per provider per environment.** Don't re-use the WAHA
  secret for Meta. Don't share secrets across products. Rotation
  should be a single-product operation.
- **Don't log the secret. Don't log the signature.** Both leak through
  to log aggregators. Log the `svix-id` / payload event type for
  diagnostics; not the signed material.

## Where the helpers live

- `noctusai_lib.security.webhook_signatures` — canonical home for
  patterns 1–3.
- `core/backend/app/services/stripe_service.construct_webhook_event` —
  the Stripe SDK call (pattern 4).

If you're adding a new webhook receiver and your provider doesn't fit
patterns 1–3 (and isn't Stripe), open a discussion before rolling your
own — the surface area should grow only when a real new pattern shows
up.

## Current adopters

- ✅ `core` — Stripe billing webhooks (pattern 4)
- ✅ `erp-imobiliario` — WAHA (pattern 2 via `app/webhook_utils`),
  Meta Lead Ads (pattern 1), digital-signature providers (pattern 1).
  `webhook_utils.py` re-exports from `noctusai_lib.security` — new
  ERP code should import from `noctusai_lib` directly.
- ✅ `mailing` — Resend (pattern 3) — verification added 2026-05-02
  alongside this doc; previously a TODO.
- ✅ `whatsapp-google-scheduling` (sibling repo) — WAHA (pattern 2)
  via vendored copy of `noctusai_lib.security.webhook_signatures` until
  it's installable as a published package.

When a new product comes online, append it here. Make divergence
visible.
