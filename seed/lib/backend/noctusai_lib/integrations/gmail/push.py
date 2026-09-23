"""Pub/Sub PUSH receiver helpers for Gmail watch notifications.

Pure and framework-free: a product's webhook route (FastAPI, anything)
hands these the raw body + the `Authorization` header and branches on
the typed errors. No request object, no framework import, no I/O except
the Google cert fetch inside the default OIDC verifier.

**Flow** (per push request Pub/Sub makes to our endpoint)::

    claims = verify_push_token(
        request.headers.get("authorization"),
        audience=settings.gmail_push_audience,
        expected_service_account=settings.gmail_push_service_account,
    )                                       # GmailPushAuthError → 401
    note = parse_push_envelope(await request.body())
                                            # GmailPushEnvelopeError → 400
    # enqueue (note.email_address, note.history_id); return 204 FAST —
    # Pub/Sub redelivers anything not acked within the ack deadline.

**Order matters.** Verify BEFORE parsing/processing — an unauthenticated
body must never reach business logic (webhook verify-before-side-effect,
`KB § PATTERNS/security/webhook-signatures.md`).

**What the notification carries.** Only `emailAddress` + `historyId` —
never the message. The consumer maps the address to its connected
mailbox and calls `GmailClient.list_history(<stored cursor>)`; the
notification's own `history_id` is the mailbox's id AFTER the change, so
it is NOT the cursor to query from (querying from it returns nothing).

**Why `expected_service_account` matters.** A Google-signed ID token is
mintable by ANY Google service account for ANY audience, so an
audience-only check proves "Google signed it", not "OUR subscription sent
it". Pin the push service account configured on the subscription
(`ensure_push_subscription(push_service_account=...)`). Omitting it is
allowed (local tooling) but logged at WARNING on every call.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from google.auth.exceptions import GoogleAuthError

from noctusai_lib.integrations.gmail.errors import (
    GmailPushAuthError,
    GmailPushEnvelopeError,
)

logger = logging.getLogger(__name__)

GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})

TokenVerifier = Callable[[str, str], Mapping[str, Any]]
"""`(jwt, audience) -> claims`. Must verify signature, expiry, issuer and
audience, raising `ValueError` (or a `google.auth` error) on any failure.
The default is `google.oauth2.id_token.verify_oauth2_token`; tests inject
a deterministic one (DI seam — no patching)."""


@dataclass(frozen=True)
class GmailPushNotification:
    """One Gmail change notification decoded from a Pub/Sub push.

    `history_id` is normalised to `str` (Gmail publishes it as a JSON
    number; every Gmail API surface takes/returns it as a string).
    `pubsub_message_id` is Pub/Sub's id — use it to de-duplicate
    redeliveries (Pub/Sub is at-least-once)."""

    email_address: str
    history_id: str
    pubsub_message_id: str = ""
    publish_time: str = ""
    subscription: str = ""


def parse_push_envelope(body: bytes | str | Mapping[str, Any]) -> GmailPushNotification:
    """Decode a Pub/Sub push body into a `GmailPushNotification`.

    Accepts the raw bytes/str body or an already-parsed mapping. Raises
    `GmailPushEnvelopeError` on anything that is not a Pub/Sub envelope
    whose base64 `message.data` is Gmail's
    ``{"emailAddress": ..., "historyId": ...}`` — never returns a partial
    notification."""
    if isinstance(body, Mapping):
        envelope: Any = body
    else:
        try:
            envelope = json.loads(body)
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            raise GmailPushEnvelopeError("push body is not valid JSON") from exc
    if not isinstance(envelope, Mapping):
        raise GmailPushEnvelopeError("push body is not a JSON object")
    message = envelope.get("message")
    if not isinstance(message, Mapping):
        raise GmailPushEnvelopeError("push envelope has no 'message' object")
    data_b64 = message.get("data")
    if not isinstance(data_b64, str) or not data_b64:
        raise GmailPushEnvelopeError("push message has no 'data'")
    try:
        padded = data_b64 + "=" * (-len(data_b64) % 4)
        # Pub/Sub uses standard base64; accept urlsafe too (both alphabets
        # decode identically once '-_' are mapped).
        raw = base64.b64decode(padded.replace("-", "+").replace("_", "/"), validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise GmailPushEnvelopeError("push message 'data' is not base64 JSON") from exc
    if not isinstance(payload, Mapping):
        raise GmailPushEnvelopeError("push message 'data' is not a JSON object")
    email_address = payload.get("emailAddress")
    history_id = payload.get("historyId")
    if not isinstance(email_address, str) or not email_address:
        raise GmailPushEnvelopeError("gmail notification has no 'emailAddress'")
    if isinstance(history_id, bool) or not isinstance(history_id, (int, str)):
        raise GmailPushEnvelopeError("gmail notification has no 'historyId'")
    history_str = str(history_id).strip()
    if not history_str.isdigit():
        raise GmailPushEnvelopeError(f"gmail 'historyId' is not numeric: {history_id!r}")
    return GmailPushNotification(
        email_address=email_address,
        history_id=history_str,
        pubsub_message_id=str(message.get("messageId") or message.get("message_id") or ""),
        publish_time=str(message.get("publishTime") or message.get("publish_time") or ""),
        subscription=str(envelope.get("subscription") or ""),
    )


def _default_verifier(token: str, audience: str) -> Mapping[str, Any]:
    """Verify with google-auth (fetches + checks Google's signing certs)."""
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, Request(), audience=audience)


def verify_push_token(
    authorization_header: str | None,
    audience: str,
    expected_service_account: str | None = None,
    *,
    verifier: TokenVerifier | None = None,
) -> dict[str, Any]:
    """Verify the Google-signed OIDC token Pub/Sub attaches to a push.

    Checks, in order: a ``Bearer <jwt>`` header is present; the JWT
    verifies (signature · expiry · `aud == audience` — via `verifier`,
    default google-auth); the issuer is Google; and, when
    `expected_service_account` is given, ``email == expected`` with
    ``email_verified`` true. Returns the verified claims.

    Raises `GmailPushAuthError` on ANY failure (never returns falsy)."""
    if not audience:
        raise GmailPushAuthError("audience is required to verify a push token")
    if not authorization_header:
        raise GmailPushAuthError("missing Authorization header")
    scheme, _, token = authorization_header.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise GmailPushAuthError("Authorization header is not 'Bearer <token>'")

    verify = verifier or _default_verifier
    try:
        claims = dict(verify(token, audience))
    except ValueError as exc:
        raise GmailPushAuthError(f"push token failed verification: {exc}") from exc
    except GoogleAuthError as exc:
        # e.g. TransportError fetching Google's certs — not a ValueError.
        # Rejecting is correct: Pub/Sub redelivers the push.
        logger.warning("gmail.push_token_verifier_error %s", type(exc).__name__)
        raise GmailPushAuthError(f"push token could not be verified: {exc}") from exc

    if claims.get("aud") != audience:
        raise GmailPushAuthError("push token audience mismatch")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GmailPushAuthError(f"push token issuer is not Google: {claims.get('iss')!r}")
    if expected_service_account is None:
        logger.warning(
            "gmail.push_token_audience_only — no expected_service_account pinned; "
            "any Google-signed token for this audience is accepted"
        )
        return claims
    if claims.get("email") != expected_service_account:
        raise GmailPushAuthError("push token was not issued for the expected service account")
    if claims.get("email_verified") is not True:
        raise GmailPushAuthError("push token email is not verified")
    return claims


__all__ = [
    "GOOGLE_ISSUERS",
    "GmailPushNotification",
    "TokenVerifier",
    "parse_push_envelope",
    "verify_push_token",
]
