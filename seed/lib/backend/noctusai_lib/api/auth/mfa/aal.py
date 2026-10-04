"""Authenticator-assurance-level (``aal``) reading — the ONLY place the claim is decoded.

Supabase stamps every access token with ``aal`` = ``"aal1"`` (one factor)
or ``"aal2"`` (a verified TOTP factor on top). ``auth.get_user`` returns
only the user, never the claims, so the platform never saw the level.

SECURITY — read this before calling anything here
-------------------------------------------------
Decoding a JWT *without verifying its signature* is only sound when the
token was ALREADY authenticated by the auth provider. An unverified claim
from a client-supplied token is attacker-controlled (a forged ``aal2``).
So the public surface is shaped to make the unsafe call impossible:

* :func:`read_aal` takes the ``validated_user`` that ``auth.get_user``
  returned for this token (see ``validate_bearer_token``) and refuses
  unless the token's ``sub`` claim equals that user's id — the token is
  bound to an acceptance, not merely "some JWT".
* :func:`read_aal_issued` is for a token the auth provider handed *us*
  directly (a refresh / verify response we received server-side),
  never one a client sent.

Anything missing, garbled or unbound resolves to ``"aal1"`` — never to
``"aal2"``. Fail toward the weaker assurance.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

Aal = Literal["aal1", "aal2"]


def _claims(token: str) -> dict[str, Any]:
    """PRIVATE. Unverified payload decode — never call outside this module."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (IndexError, ValueError, TypeError, AttributeError) as exc:
        logger.debug("mfa.aal: undecodable token (%s) — treating as aal1", type(exc).__name__)
        return {}
    return data if isinstance(data, dict) else {}


def _aal_of(claims: dict[str, Any]) -> Aal:
    return "aal2" if claims.get("aal") == "aal2" else "aal1"


def read_aal(access_token: str, *, validated_user: Any) -> Aal:
    """The ``aal`` of a client-supplied token ALREADY accepted by ``auth.get_user``.

    ``validated_user`` is the user object that call returned. The token's
    ``sub`` must equal ``validated_user.id``; otherwise (or on any
    missing/garbled claim) the result is ``"aal1"``.
    """
    if validated_user is None:
        return "aal1"
    claims = _claims(access_token)
    uid = getattr(validated_user, "id", None)
    if uid is None or str(claims.get("sub")) != str(uid):
        return "aal1"
    return _aal_of(claims)


def read_aal_issued(access_token: Optional[str]) -> Optional[Aal]:
    """The ``aal`` of a token the auth provider issued to US (server-side).

    ``None`` when there is no token. NEVER pass a client-supplied token.
    """
    if not access_token:
        return None
    return _aal_of(_claims(access_token))


__all__ = ["Aal", "read_aal", "read_aal_issued"]
