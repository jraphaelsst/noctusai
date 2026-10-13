"""Signed, expiring e-mail links -- the buyer's only "login" (D26: guest checkout).

Two purposes share one mechanism (HMAC-SHA256 over a small JSON claim, base64url):

* `my_orders`      -- "see my orders" magic link (subject = customer id);
* `privacy_verify` -- confirms a privacy request came from the mailbox owner
  (subject = privacy-request id).

The signing secret is resolved per request by the host (`get_link_secret`), never
captured at import. A token is bound to its ORG and purpose: a `my_orders` token
cannot verify a privacy request, and a token minted for one store is useless on
another store's host. Constant-time compare; expiry is checked after the
signature so a forged claim never reaches the clock.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from noctusai_lib.integrations.email.types import EmailSender, OutgoingEmail

from ._common import now
from .errors import CommerceError

logger = logging.getLogger(__name__)

PURPOSE_MY_ORDERS = "my_orders"
PURPOSE_PRIVACY_VERIFY = "privacy_verify"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, body: str) -> str:
    return _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())


def sign_token(
    secret: str,
    *,
    purpose: str,
    org_id: Any,
    subject: Any,
    ttl_minutes: int,
    at: Optional[datetime] = None,
) -> str:
    if not secret:
        raise CommerceError("link_indisponivel", "Links por e-mail não estão configurados.", 503)
    claim = {
        "p": purpose,
        "o": str(org_id),
        "s": str(subject),
        "x": int(((at or now()) + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    body = _b64(json.dumps(claim, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_mac(secret, body)}"


def _bad() -> CommerceError:
    return CommerceError("link_invalido", "Link inválido ou expirado.", 400)


def verify_token(
    secret: str, token: str, *, purpose: str, org_id: Any, at: Optional[datetime] = None
) -> dict:
    """The claim `{p, o, s, x}` of a valid token; `CommerceError(link_invalido, 400)` otherwise."""
    if not secret or not token or token.count(".") != 1:
        raise _bad()
    body, mac = token.split(".")
    if not hmac.compare_digest(mac, _mac(secret, body)):
        raise _bad()
    try:
        claim = json.loads(_unb64(body))
    except (ValueError, UnicodeDecodeError) as exc:
        raise _bad() from exc
    if claim.get("p") != purpose or claim.get("o") != str(org_id):
        raise _bad()
    if int(claim.get("x", 0)) < int((at or now()).timestamp()):
        raise _bad()
    return claim


async def send_link_email(
    sender: EmailSender, *, to: str, store_name: str, subject: str, intro: str, url: str, ttl_minutes: int
) -> None:
    text = (
        f"{intro}\n\n{url}\n\n"
        f"Este link vale por {ttl_minutes} minutos. Se você não pediu isso, ignore esta mensagem.\n\n— {store_name}"
    )
    html = (
        f"<p>{intro}</p><p><a href=\"{url}\">{url}</a></p>"
        f"<p>Este link vale por {ttl_minutes} minutos. Se você não pediu isso, ignore esta mensagem.</p><p>— {store_name}</p>"
    )
    await sender.send(OutgoingEmail(to=[to], subject=subject, html=html, text=text))


__all__ = [
    "PURPOSE_MY_ORDERS",
    "PURPOSE_PRIVACY_VERIFY",
    "send_link_email",
    "sign_token",
    "verify_token",
]
