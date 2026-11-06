"""HMAC-signed OAuth ``state`` token — tamper-evident org binding.

Security context (``sw-meta-org-auth-wiring``): the Meta / Google Calendar
OAuth ``state`` parameter round-trips through a THIRD-PARTY redirect
(Facebook / Google) with no session cookie attached on the way back — the
callback can't take ``Depends(get_current_user_org)``. Before this module,
``state`` was an UNSIGNED ``{org_id}:{nonce}`` pair the callback trusted
verbatim: an attacker could mint their own ``state=<victim-org>:<nonce>``,
start their own consent flow, then trick the victim (or a bot) into
completing the redirect — landing the attacker's OAuth credential under
the victim's org (a confused-deputy write / login-CSRF, the same class of
vulnerability the account-lookup IDOR this branch closes elsewhere).

:func:`sign_oauth_state` binds the state to the org resolved from the
AUTHENTICATED session that started the flow (``oauth/start``, gated on
``Depends(get_current_user_org)``) plus a random nonce, and appends an
HMAC-SHA256 tag keyed on ``settings.jwt_secret`` — the same signing key
``app/modules/email_marketing/routers/unsubscribe.py`` already uses for
its own HMAC-signed link tokens (N=2 recurrence of "sign a short-lived
token with the product's JWT secret"). :func:`verify_oauth_state`
re-derives the tag and rejects on any mismatch via ``hmac.compare_digest``
(constant-time) BEFORE the callback does anything with the decoded
org_id — verify-then-use, never use-then-verify.

Uses the seed's ``noctusai_lib.security.webhook_signatures.compute_hmac_sha256_hex``
primitive rather than hand-rolling ``hmac.new(...).hexdigest()`` a third
time in this product.
"""
from __future__ import annotations

import hmac
import secrets
from uuid import UUID

from fastapi import HTTPException, status
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

from app.config import settings

__all__ = ["sign_oauth_state", "verify_oauth_state", "verify_oauth_state_full"]


def sign_oauth_state(org_id: UUID, marca_id: str = "") -> str:
    """Build a tamper-evident OAuth ``state`` token.

    Without ``marca_id``: ``{org_id}:{nonce}:{hmac}`` (the calendar / org-level shape). With it (the
    multi-account flows carry the client the new account links to through the redirect):
    ``{org_id}:{nonce}:{marca_id}:{hmac}`` -- the marca is INSIDE the signed payload, so it can't be swapped.

    ``org_id`` MUST be the org resolved from the caller's authenticated
    session -- never a caller-supplied value -- or the signature just
    certifies an attacker-chosen org.
    """
    nonce = secrets.token_urlsafe(16)
    payload = f"{org_id}:{nonce}:{marca_id}" if marca_id else f"{org_id}:{nonce}"
    sig = compute_hmac_sha256_hex(payload.encode("utf-8"), settings.jwt_secret)
    return f"{payload}:{sig}"


def verify_oauth_state_full(state: str) -> tuple[UUID, str]:
    """Verify + decode a state token -> ``(org_id, marca_id_or_empty)``.

    Raises ``400`` on malformed shape OR signature mismatch -- never returns an
    org_id that wasn't verified. Constant-time compare (``hmac.compare_digest``)
    so a timing side-channel can't help an attacker forge the tag. Accepts the
    3-part (no marca) and 4-part (with marca) shapes of :func:`sign_oauth_state`.
    """
    parts = state.split(":")
    if len(parts) not in (3, 4):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token malformed.",
        )
    sig = parts[-1]
    payload = ":".join(parts[:-1])
    expected = compute_hmac_sha256_hex(payload.encode("utf-8"), settings.jwt_secret)
    if not sig or not hmac.compare_digest(expected, sig):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token failed signature verification.",
        )
    try:
        return UUID(parts[0]), (parts[2] if len(parts) == 4 else "")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state token does not encode a valid org_id.",
        ) from exc


def verify_oauth_state(state: str) -> UUID:
    """Verify + decode a state token to its org (``verify_oauth_state_full`` minus the marca)."""
    return verify_oauth_state_full(state)[0]
