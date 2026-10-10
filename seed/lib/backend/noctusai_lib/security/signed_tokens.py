"""Purpose-bound HMAC tokens for public links (unsubscribe, email confirmation,
click tracking, ...).

A token is ``<body>.<mac>``: ``body`` is base64url(JSON ``{"p": purpose,
"d": payload, "e": expiry|null}``) and ``mac`` is base64url(HMAC-SHA256(secret,
f"{purpose}.{body}")). The purpose is inside BOTH the body and the MAC, so a
token minted for one purpose never verifies for another (a click token is not an
unsubscribe token), and a payload cannot be edited without the secret — which is
what makes a signed redirect target safe from open-redirect abuse.

Formalized 2026-10-10 (social-wiring email marketing P1b): the unsubscribe link
hand-rolled its own HMAC, and three more public-link kinds were about to.
``verify`` never raises on a bad token — it returns ``None`` (the caller answers
400); an empty secret raises at ``sign`` time, because a token signed with ``""``
is forgeable by anyone.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Callable, Optional


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, purpose: str, body: str) -> str:
    return _b64(hmac.new(secret.encode(), f"{purpose}.{body}".encode(), hashlib.sha256).digest())


def sign(
    purpose: str,
    payload: dict[str, Any],
    secret: str,
    *,
    ttl_seconds: Optional[int] = None,
    now: Callable[[], float] = time.time,
) -> str:
    """Mint a token for ``purpose`` carrying ``payload`` (JSON-serialisable).
    ``ttl_seconds=None`` never expires (an unsubscribe link must keep working)."""
    if not secret:
        raise ValueError("signed_tokens.sign: an empty secret makes every token forgeable")
    if not purpose:
        raise ValueError("signed_tokens.sign: purpose is required")
    expiry = int(now()) + ttl_seconds if ttl_seconds else None
    body = _b64(json.dumps({"p": purpose, "d": payload, "e": expiry},
                           separators=(",", ":"), sort_keys=True).encode())
    return f"{body}.{_mac(secret, purpose, body)}"


def verify(
    purpose: str,
    token: str,
    secret: str,
    *,
    now: Callable[[], float] = time.time,
) -> Optional[dict[str, Any]]:
    """The payload when ``token`` was signed for ``purpose`` with ``secret`` and
    has not expired; ``None`` otherwise (malformed, forged, other purpose,
    expired, empty secret)."""
    if not secret or not token or token.count(".") != 1:
        return None
    body, mac = token.split(".", 1)
    if not hmac.compare_digest(mac, _mac(secret, purpose, body)):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("p") != purpose:
        return None
    expiry = data.get("e")
    if expiry is not None and int(now()) >= int(expiry):
        return None
    payload = data.get("d")
    return payload if isinstance(payload, dict) else None


__all__ = ["sign", "verify"]
