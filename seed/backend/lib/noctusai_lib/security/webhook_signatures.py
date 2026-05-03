"""Webhook signature verification primitives.

Three patterns cover every inbound webhook NoctusAI receives:

1. **HMAC-SHA256 with `sha256=…` prefix** — Meta Lead Ads (`X-Hub-Signature-256`),
   GitHub, generic webhook providers that follow the Hub-Signature scheme.
   Use `verify_hmac_sha256(body, signature, secret)`.

2. **HMAC-SHA256 hex (no prefix)** — WAHA, internal NoctusAI-to-NoctusAI
   webhooks, simple shared-secret schemes.
   Use `compute_hmac_sha256_hex(body, secret)` and `hmac.compare_digest`.

3. **Svix-protocol** — Resend (and any provider built on Svix). Headers
   `svix-id`, `svix-timestamp`, `svix-signature`; signed message is
   `f"{id}.{timestamp}.{body}"`; secret is base64-encoded `whsec_…`.
   Use `verify_svix_signature(svix_id, svix_timestamp, body, signature_header, secret)`.

4. **Vendor SDK** — Stripe ships its own verifier
   (`stripe.Webhook.construct_event`). Don't wrap it. Don't reinvent it.
   See `core/backend/app/services/stripe_service.construct_webhook_event`
   for the call shape.

All checks use `hmac.compare_digest` so verification time is independent
of where two signatures diverge — no timing-side-channel bug.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def compute_hmac_sha256_hex(body: bytes, secret: str) -> str:
    """Hex-encoded HMAC-SHA256 of `body` keyed with `secret`.

    Use when the provider sends a bare hex digest (e.g. WAHA) without
    an algorithm-name prefix. Compare against the header value with
    `hmac.compare_digest`.
    """
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_hmac_sha256(body: bytes, signature: str, secret: str) -> bool:
    """Verify a `sha256=<hex>`-style signature header.

    Args:
        body: Raw request body bytes (DO NOT use the parsed JSON — re-encoding
              changes whitespace and breaks the signature).
        signature: The full header value, e.g. `"sha256=abc123..."`.
        secret: Shared secret the provider signed with.

    Returns:
        True if the signature matches; False otherwise. Wrong secret,
        tampered body, missing header, or empty signature all return False.
    """
    if not signature or not secret:
        return False
    expected = "sha256=" + compute_hmac_sha256_hex(body, secret)
    return hmac.compare_digest(expected, signature)


def verify_svix_signature(
    *,
    svix_id: str,
    svix_timestamp: str,
    body: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """Verify a Svix-protocol webhook signature (Resend and similar).

    Svix signs `f"{svix_id}.{svix_timestamp}.{body_text}"` with HMAC-SHA256
    keyed on the secret's base64-decoded payload. The header may carry
    multiple `v1,<base64>` entries (whitespace-separated) so the provider
    can rotate keys without breakage; we accept the first that matches.

    Args:
        svix_id: Value of the `svix-id` header.
        svix_timestamp: Value of the `svix-timestamp` header.
        body: Raw request body bytes.
        signature_header: Value of the `svix-signature` header. Format
            `"v1,<base64> v1,<base64-rotated>"`.
        secret: Webhook secret as Resend/Svix issues it. Accepts both raw
            base64 ("AbCd…") and the `whsec_<base64>` form they show in
            their UI.

    Returns:
        True if any version in the header matches; False otherwise.
    """
    if not (svix_id and svix_timestamp and signature_header and secret):
        return False
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_"):]
    try:
        secret_bytes = base64.b64decode(secret)
    except (ValueError, TypeError):
        return False
    signed_payload = f"{svix_id}.{svix_timestamp}.{body.decode('utf-8', errors='replace')}".encode("utf-8")
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
    ).decode("ascii")
    for entry in signature_header.split():
        if "," not in entry:
            continue
        version, sig = entry.split(",", 1)
        if version != "v1":
            continue
        if hmac.compare_digest(expected, sig):
            return True
    return False
