"""The public accept link -- a signed, expiring token over the commerce organ's mechanism.

`commerce.access_links.sign_token / verify_token` (HMAC-SHA256 over a small JSON claim, base64url) with purpose
`quote_accept` and the quote id as subject. The token binds ORG + PURPOSE: a `my_orders` token cannot open a
quote, and a token minted for another org's quote is useless. The secret is resolved per request by the host
(`get_link_secret`), never captured at import.

The public route has no session, so the org is read from the (MAC-covered) claim -- `peek_org` -- and then the
token is verified against THAT org; a forged claim fails the MAC before anything is trusted.

Every failure (malformed, forged, expired, wrong purpose, foreign org) is the SAME 404 `link_invalido`
(`errors.bad_link`): the response never says which, so a probe learns nothing.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from noctusai_lib.domain.commerce.access_links import sign_token, verify_token
from noctusai_lib.domain.commerce.errors import CommerceError

from ._common import to_date
from .config import QuotesConfig
from .errors import LINK_INDISPONIVEL, QuotesError, bad_link

PURPOSE_QUOTE_ACCEPT = "quote_accept"


def link_ttl_minutes(cfg: QuotesConfig, valid_until: Any, *, now: Optional[datetime] = None) -> int:
    """`cfg.link_ttl_days`, capped so the link dies with the end of the validity day (never longer than the offer)."""
    base = cfg.link_ttl_days * 24 * 60
    day = to_date(valid_until)
    if day is None:
        return base
    end = datetime.combine(day, time.min, tzinfo=cfg.tz) + timedelta(days=1)
    minutes = int((end - (now or datetime.now(timezone.utc))).total_seconds() // 60)
    return max(1, min(base, minutes))


def mint_token(secret: str, cfg: QuotesConfig, quote: dict, *, now: Optional[datetime] = None) -> str:
    """A fresh accept link token for `quote` (503 `link_indisponivel` when the host has no secret)."""
    try:
        return sign_token(
            secret,
            purpose=PURPOSE_QUOTE_ACCEPT,
            org_id=quote["org_id"],
            subject=quote["id"],
            ttl_minutes=link_ttl_minutes(cfg, quote.get("valid_until"), now=now),
            at=now,
        )
    except CommerceError as exc:  # no secret configured
        raise QuotesError(LINK_INDISPONIVEL, "Links de orçamento não estão configurados.", 503) from exc


def _b64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def peek_org(token: str) -> str:
    """The org the (still UNVERIFIED) token claims. Only ever used to pick the org to verify AGAINST."""
    try:
        body = (token or "").split(".")[0]
        return str(json.loads(_b64(body))["o"])
    except Exception as exc:  # noqa: BLE001 - any malformed token is the same indistinguishable answer
        raise bad_link() from exc


def open_token(secret: str, token: str, *, now: Optional[datetime] = None) -> tuple[str, str]:
    """`(org_id, quote_id)` of a valid token, else `bad_link()` (404)."""
    org_id = peek_org(token)
    try:
        claim = verify_token(secret, token, purpose=PURPOSE_QUOTE_ACCEPT, org_id=org_id, at=now)
    except CommerceError as exc:
        raise bad_link() from exc
    return org_id, str(claim["s"])


__all__ = ["PURPOSE_QUOTE_ACCEPT", "link_ttl_minutes", "mint_token", "open_token", "peek_org"]
