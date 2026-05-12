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
- **Replay window when the provider sends a timestamp.** Pass it to
  `verify_hmac_sha256(..., timestamp_value=ts)` /
  `verify_hmac_sha256_hex(..., timestamp_value=ts)` or set
  `enforce_replay_window=True` on `verify_svix_signature(...)`.
  Default tolerance is 300s (matches Stripe). Capture-and-replay is
  a real attack against any verified-but-stateless receiver; if the
  provider sends a timestamp, enforce the window.
- **LGPD lens applies after verification.** Verified-but-unparsed
  payloads from Meta / Resend / WhatsApp commonly carry PII (names,
  email addresses, phone numbers, message bodies). Once the body is
  parsed, every downstream write (DB row, audit log, queue payload)
  is a personal-data event under LGPD. Apply the standard checklist:
  documented basis, retention rule, no cross-product spillover, no
  response cache for clinical text. → `KB § PATTERNS/lgpd.md`.

## Where the helpers live

- `noctusai_lib.security.webhook_signatures` — canonical home for
  patterns 1–3.
- `core/backend/app/services/stripe_service.construct_webhook_event` —
  the Stripe SDK call (pattern 4).

If you're adding a new webhook receiver and your provider doesn't fit
patterns 1–3 (and isn't Stripe), open a discussion before rolling your
own — the surface area should grow only when a real new pattern shows
up.

---

## The 5-pin compliance contract (formalized 2026-05-09)

**Every webhook receiver MUST satisfy all 5 pins.** The seed ships a
canonical reference at `products/seed/backend/app/routers/webhook_router.py`
+ `tests/routers/test_webhook_router.py` that demonstrates all 5; new
products inherit it via `scaffold_product` and rename per vendor.

| Pin | Rule | Why | Anti-shape |
|---|---|---|---|
| **1** | Use `webhook_endpoint(...)` from `noctusai_lib.security.webhook_signatures` (or Stripe SDK for pattern 4) | One decorator replaces hand-rolled HMAC dance; verification BEFORE any DB work | Hand-rolled `hmac.compare_digest` in the handler body |
| **2** | Per-request `ResolvedSecret` resolver (lambda reads `settings.<vendor>_webhook_secret` at request time) | Honors test-time monkeypatches on `settings`; avoids the import-time-capture trap | `static_secret_resolver(settings.foo_secret)` at module load |
| **3** | `bypass_when_unset=` flag explicitly set (True for early-dev, False for production-strict) | Boots cleanly before secret is configured; bypass logs a WARNING — never silent | Flag omitted (default False is technically compliant but easy to miss) |
| **4** | `@limiter.limit(settings.webhook_rate_limit)` decorator | DDOS guard on a public endpoint — every receiver is unauth so rate-limit is the only throttle | No limiter; only the FastAPI default trust |
| **5** | Status-code-pinned tests (`assert resp.status_code == N`) | The keeper detector `check_test_status_assertion` enforces this; substring body checks miss 4xx slips | Asserting only on `resp.json()` / `resp.text` |

**Test shape — copy from the seed reference:**

```python
def test_valid_signature_returns_200(self, client, monkeypatch):
    monkeypatch.setattr(settings, "<vendor>_webhook_secret", SECRET)
    body = b'<canonical-event>'
    resp = client.raw().post("/api/webhooks/<vendor>",
        content=body,
        headers={..., "content-type": "application/json"})
    assert resp.status_code == 200

def test_tampered_body_returns_401(...): ...
def test_missing_signature_headers_returns_401(...): ...
def test_unset_secret_bypasses_with_warning(self, client, monkeypatch, caplog):
    # caplog at WARNING level on logger="noctusai_lib.security.webhook_signatures"
    ...
    assert resp.status_code == 200
    assert any("bypass" in r.message.lower() for r in caplog.records)
```

**Stripe carve-out (pattern 4).** Pins 1+2+3 don't apply (Stripe SDK
owns secret resolution); pins 4+5 still apply. The Stripe receiver in
`core/billing.py` was missing pin 4 until 2026-05-09 — fixed inline.

---

## Current adopters

- ✅ `core` — Stripe billing webhooks (pattern 4) — pins 4+5 enforced 2026-05-09
- ✅ `erp-imobiliario` — WAHA (pattern 2), Meta Lead Ads (pattern 1) — all 5 pins from launch
- ✅ `mailing` — Resend (pattern 3) — all 5 pins from 2026-05-02
- ✅ `imobi-scheduling` — WAHA (pattern 2) — all 5 pins from launch (consolidates the earlier `media-scheduling` port deleted 2026-05-11)
- ✅ `whatsapp-google-scheduling` (sibling repo) — WAHA (pattern 2)
  via vendored copy until published-package shape lands.

When a new product comes online, the inherited seed skeleton already
satisfies all 5 pins — replace `_resolve_example_secret` + the endpoint
body, keep the rest. Append to this list to make divergence visible.
