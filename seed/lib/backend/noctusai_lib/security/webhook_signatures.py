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
import inspect
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional, Union

from fastapi import Depends, HTTPException, Request

DEFAULT_MAX_AGE_SECONDS = 300

logger = logging.getLogger(__name__)

WebhookScheme = Literal["sha256_prefixed", "sha256_hex", "svix"]

_DEFAULT_SIGNATURE_HEADER: dict[str, str] = {
    "sha256_prefixed": "X-Hub-Signature-256",
    "sha256_hex": "X-Webhook-Hmac-SHA256",
    "svix": "svix-signature",
}


def compute_hmac_sha256_hex(body: bytes, secret: str) -> str:
    """Hex-encoded HMAC-SHA256 of `body` keyed with `secret`.

    Use when the provider sends a bare hex digest (e.g. WAHA) without
    an algorithm-name prefix. Compare against the header value with
    `hmac.compare_digest`.
    """
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _within_replay_window(
    timestamp_value: int | None,
    max_age_seconds: int,
    now: int | None = None,
) -> bool:
    """Check that a provider-supplied unix timestamp is within tolerance.

    `None` ⇒ no replay protection requested (caller opts out). A non-None
    value outside `[now - max_age, now + max_age]` is rejected — both past
    (capture-and-replay) and future (clock-skew abuse).
    """
    if timestamp_value is None:
        return True
    current = now if now is not None else int(time.time())
    return abs(current - timestamp_value) <= max_age_seconds


def verify_hmac_sha256(
    body: bytes,
    signature: str,
    secret: str,
    *,
    timestamp_value: int | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    """Verify a `sha256=<hex>`-style signature header.

    Args:
        body: Raw request body bytes (DO NOT use the parsed JSON — re-encoding
              changes whitespace and breaks the signature).
        signature: The full header value, e.g. `"sha256=abc123..."`.
        secret: Shared secret the provider signed with.
        timestamp_value: Optional unix timestamp from a provider-sent header
              (e.g. Meta's `X-Hub-Timestamp` when present). Pass `None` to
              opt out of replay protection. Default `None`.
        max_age_seconds: Replay window when `timestamp_value` is supplied.
              Default 300s, matching Stripe's tolerance.

    Returns:
        True if the signature matches AND (when supplied) the timestamp
        falls inside `±max_age_seconds`. Wrong secret, tampered body,
        missing header, empty signature, or expired timestamp all return False.
    """
    if not signature or not secret:
        return False
    if not _within_replay_window(timestamp_value, max_age_seconds):
        return False
    expected = "sha256=" + compute_hmac_sha256_hex(body, secret)
    return hmac.compare_digest(expected, signature)


def verify_hmac_sha256_hex(
    body: bytes,
    signature_hex: str,
    secret: str,
    *,
    timestamp_value: int | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    """Verify a bare-hex HMAC-SHA256 signature (no `sha256=` prefix).

    Symmetric counterpart to :func:`verify_hmac_sha256` for providers that
    send the digest as plain hex (e.g. WAHA, internal NoctusAI-to-NoctusAI
    webhooks). Constant-time compare. Forces callers off `==` and saves
    everyone from forgetting `hmac.compare_digest`.

    Args:
        body: Raw request body bytes.
        signature_hex: Hex digest from the header (no prefix).
        secret: Shared secret.
        timestamp_value: Optional unix timestamp for replay-window enforcement.
        max_age_seconds: Replay window. Default 300s.

    Returns:
        True on match; False on tamper / wrong-secret / missing input /
        expired timestamp.
    """
    if not signature_hex or not secret:
        return False
    if not _within_replay_window(timestamp_value, max_age_seconds):
        return False
    expected = compute_hmac_sha256_hex(body, secret)
    return hmac.compare_digest(expected, signature_hex)


def verify_svix_signature(
    *,
    svix_id: str,
    svix_timestamp: str,
    body: bytes,
    signature_header: str,
    secret: str,
    enforce_replay_window: bool = False,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    """Verify a Svix-protocol webhook signature (Resend and similar).

    Svix signs `f"{svix_id}.{svix_timestamp}.{body_text}"` with HMAC-SHA256
    keyed on the secret's base64-decoded payload. The header may carry
    multiple `v1,<base64>` entries (whitespace-separated) so the provider
    can rotate keys without breakage; we accept the first that matches.

    Args:
        svix_id: Value of the `svix-id` header.
        svix_timestamp: Value of the `svix-timestamp` header (unix seconds).
        body: Raw request body bytes.
        signature_header: Value of the `svix-signature` header. Format
            `"v1,<base64> v1,<base64-rotated>"`.
        secret: Webhook secret as Resend/Svix issues it. Accepts both raw
            base64 ("AbCd…") and the `whsec_<base64>` form they show in
            their UI.
        enforce_replay_window: When True, also require `svix_timestamp`
            to fall within `±max_age_seconds` of `time.time()`. Default
            False so existing callers don't break; flip on to close
            capture-and-replay. Svix's reference verifier defaults this on.
        max_age_seconds: Replay window. Default 300s.

    Returns:
        True if any version in the header matches AND (when requested)
        the timestamp is fresh; False otherwise.
    """
    if not (svix_id and svix_timestamp and signature_header and secret):
        return False
    if enforce_replay_window:
        try:
            ts = int(svix_timestamp)
        except (TypeError, ValueError):
            return False
        if not _within_replay_window(ts, max_age_seconds):
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


# ── FastAPI dependency factory ────────────────────────────────────────


@dataclass(frozen=True)
class ResolvedSecret:
    """Returned by a `SecretResolver`: the per-request secret plus optional context.

    `extras` lets the resolver pass through a config row / org_id / payload
    snippet the resolver had to fetch anyway, so the handler doesn't repeat
    the lookup. Default `None` for static-secret cases.
    """

    secret: Optional[str]
    extras: Any = None


@dataclass(frozen=True)
class VerifiedWebhook:
    """Yielded by `webhook_endpoint` after the dependency runs.

    Reaching the handler means signature verification passed OR the unset-
    secret bypass fired (with WARNING). `body` is the raw bytes the
    signature was checked against — the handler MUST parse JSON from this,
    not from a re-read `request.body()`.
    """

    body: bytes
    extras: Any = None


SecretResolverResult = Union[Optional[str], ResolvedSecret]
SecretResolver = Callable[
    [Request, bytes],
    Union[Awaitable[SecretResolverResult], SecretResolverResult],
]


def static_secret_resolver(secret: Optional[str]) -> SecretResolver:
    """Resolver for the simple case where the secret is fixed at boot.

    Wrap a settings/env-derived secret string. `None` / empty triggers the
    unset-secret path (bypass-with-WARNING when `bypass_when_unset=True`,
    otherwise 401).
    """

    async def _resolve(request: Request, body: bytes) -> ResolvedSecret:
        return ResolvedSecret(secret=secret or None)

    return _resolve


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def webhook_endpoint(
    *,
    secret_resolver: SecretResolver,
    scheme: WebhookScheme = "sha256_prefixed",
    signature_header: Optional[str] = None,
    timestamp_header: Optional[str] = None,
    svix_id_header: str = "svix-id",
    svix_timestamp_header: str = "svix-timestamp",
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    enforce_replay_window: bool = False,
    bypass_when_unset: bool = False,
    log_prefix: str = "webhook",
):
    """Build a FastAPI dependency that verifies an inbound webhook signature.

    Replaces the verify-then-raise dance hand-rolled in every receiver.

    Args:
        secret_resolver: Callable `(request, body) -> ResolvedSecret | str | None`,
            sync or async. Receives the raw body so resolvers that key
            secrets off payload contents (e.g. `page_id`, `assinatura_id`)
            have what they need. Return `None` / empty string to signal
            "no secret configured" — handled per `bypass_when_unset`.
        scheme: Which signature shape to verify. `sha256_prefixed` (Meta /
            GitHub), `sha256_hex` (WAHA, internal), or `svix` (Resend).
        signature_header: Header to read the signature from. Defaults per
            scheme when None.
        timestamp_header: Optional header carrying a unix timestamp for
            replay-window enforcement (HMAC schemes only). When set, an
            invalid integer raises 401.
        svix_id_header / svix_timestamp_header: Override Svix header names
            if a provider deviates.
        max_age_seconds: Replay window. Default 300s.
        enforce_replay_window: When True under `scheme="svix"`, require
            the `svix-timestamp` to fall within `±max_age_seconds`.
        bypass_when_unset: When True and the resolver returns no secret,
            log WARNING + pass through (early-dev / unconfigured-tenant
            affordance). When False, raise 401.
        log_prefix: Prefix for diagnostic WARNING logs.

    Returns:
        A `Depends(...)` object. Handlers receive `VerifiedWebhook(body, extras)`.
    """

    if signature_header is None:
        signature_header = _DEFAULT_SIGNATURE_HEADER[scheme]

    async def dependency(request: Request) -> VerifiedWebhook:
        body = await request.body()
        resolver_out = secret_resolver(request, body)
        resolver_out = await _maybe_await(resolver_out)
        if isinstance(resolver_out, ResolvedSecret):
            secret, extras = resolver_out.secret, resolver_out.extras
        else:
            secret, extras = resolver_out, None

        if not secret:
            if bypass_when_unset:
                logger.warning(
                    "%s: secret unset — accepting webhook without verification",
                    log_prefix,
                )
                return VerifiedWebhook(body=body, extras=extras)
            raise HTTPException(status_code=401, detail="webhook secret not configured")

        ts_value: Optional[int] = None
        if timestamp_header is not None:
            ts_raw = request.headers.get(timestamp_header)
            if ts_raw:
                try:
                    ts_value = int(ts_raw)
                except ValueError:
                    raise HTTPException(
                        status_code=401, detail="invalid webhook timestamp"
                    )

        ok = False
        if scheme == "sha256_prefixed":
            ok = verify_hmac_sha256(
                body,
                request.headers.get(signature_header, ""),
                secret,
                timestamp_value=ts_value,
                max_age_seconds=max_age_seconds,
            )
        elif scheme == "sha256_hex":
            ok = verify_hmac_sha256_hex(
                body,
                request.headers.get(signature_header, ""),
                secret,
                timestamp_value=ts_value,
                max_age_seconds=max_age_seconds,
            )
        elif scheme == "svix":
            ok = verify_svix_signature(
                svix_id=request.headers.get(svix_id_header, ""),
                svix_timestamp=request.headers.get(svix_timestamp_header, ""),
                body=body,
                signature_header=request.headers.get(signature_header, ""),
                secret=secret,
                enforce_replay_window=enforce_replay_window,
                max_age_seconds=max_age_seconds,
            )
        else:  # pragma: no cover — Literal narrows this off
            raise HTTPException(status_code=500, detail="unsupported webhook scheme")

        if not ok:
            logger.warning("%s: signature verification failed", log_prefix)
            raise HTTPException(status_code=401, detail="invalid webhook signature")

        return VerifiedWebhook(body=body, extras=extras)

    return Depends(dependency)
