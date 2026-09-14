"""The approval assertion (contract §D) — minted by the agents control
plane after a human approved a specific tool call, verified by the
product that receives the write (academia-de-reciclagem today).

**Only the agents control plane ever calls :func:`mint_assertion`.** The
Julia CLI subprocess never sees ``approval_assertion_secrets`` — the
``env -i`` wrapper (contract §E.5, ``bin/julia-cli-exec``) guarantees that
independently of this module.

:func:`verify_assertion` is shipped here because G2 owns the minting side
and both sides must agree byte-for-byte on the canonical-JSON hash. It
implements §D steps 1-7 only — step 8 ("`approved_by` holds the WRITE role
set in this org") needs org-membership data this module has no access to
(the verifying product's own auth layer resolves that). **Reuse
destination:** this is genuinely cross-product (an academia-shaped
verifier, and any FUTURE audience this pattern grows to, both need step
1-7 verification against the exact same claim shape) — it belongs in
``noctusai_lib.security.approval_assertion`` once a second consumer needs
it. Kept product-local here per the G2 brief; promoting it is a one-file
move plus an import-path update, not a rewrite (no product-specific state
is closed over).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt

__all__ = [
    "AssertionInvalid",
    "canonical_body_sha256",
    "mint_assertion",
    "VerifiedAssertion",
    "verify_assertion",
]

_ALGORITHM = "HS256"
_DEFAULT_TTL_SECONDS = 60


class AssertionInvalid(Exception):
    """Any of §D's verification steps 1-7 failed. Callers map this to
    HTTP 403 ``assertion_invalid`` (contract §B.0) — the same bucket for
    every sub-reason, so a probing caller cannot distinguish "bad
    signature" from "expired" from "wrong path" by response shape."""


def canonical_body_sha256(body: dict[str, Any]) -> str:
    """sha256 hex digest of ``body``'s canonical JSON form (contract §D:
    UTF-8, sorted keys, no insignificant whitespace)."""
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mint_assertion(
    *,
    approval_id: UUID,
    secret: str,
    agent_id: UUID,
    org_id: UUID,
    tool_name: str,
    method: str,
    path: str,
    body: dict[str, Any],
    approved_by: UUID,
    requested_by: UUID,
    aud: str,
    iss: str = "agents",
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> str:
    """Mint the compact JWS (HS256) for exactly the method/path/body of
    ONE approved write (contract §D claims block, verbatim field set).

    ``approval_id`` becomes ``jti`` — contract §D: ``"jti": "<approval
    uuid>"``. It is also the single-use replay key academia's
    ``approval_consumptions(jti)`` insert guards (§A.10), so it must be
    the SAME id as the ``approvals`` row the human decided on, never a
    freshly minted one.
    """
    now = int(time.time())
    payload = {
        "jti": str(approval_id),
        "iss": iss,
        "aud": aud,
        "sub": str(agent_id),
        "org": str(org_id),
        "tool": tool_name,
        "method": method,
        "path": path,
        "body_sha256": canonical_body_sha256(body),
        "approved_by": str(approved_by),
        "requested_by": str(requested_by),
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


@dataclass(frozen=True)
class VerifiedAssertion:
    """The claim set, once every §D step 1-7 check has passed."""

    jti: UUID
    sub: UUID  # agent id
    org: UUID
    tool: str
    method: str
    path: str
    body_sha256: str
    approved_by: UUID
    requested_by: UUID
    iat: int
    exp: int


def verify_assertion(
    token: str,
    *,
    secret_candidates: list[str],
    aud: str,
    org_id: UUID,
    method: str,
    path: str,
    body: dict[str, Any],
    tool_for_route: str,
    iss: str = "agents",
) -> VerifiedAssertion:
    """Implements contract §D steps 1-7, in order, failing closed on the
    first mismatch. Step 8 (approver role check) is NOT here — see the
    module docstring.

    1. Signature — tried against every ``secret_candidates`` entry (key
       rotation: academia accepts any configured key; §D "Rotation =
       prepend the new key, deploy both, then drop the old one").
    2. ``aud`` — enforced by :func:`jwt.decode`'s own ``audience=``.
    3. ``exp`` — enforced by :func:`jwt.decode`'s own expiry check.
    4. ``org`` equals the token's org (the caller passes the RESOLVED
       org from ITS OWN authenticated context, never trusting a claim
       alone to establish scope).
    5. ``sub`` — left to the caller to further match against
       ``ctx.principal_agent_id`` if it wants a stricter bind; this
       function only asserts ``sub`` parses as a UUID (contract step 5
       compares it against "the token's principal agent", which is a
       fact this module doesn't hold — the HTTP layer that resolved the
       product-token IS the one place that fact lives).
    6. ``body_sha256`` equals the canonical hash of the RECEIVED body.
    7. ``method``/``path`` equal the received request exactly, and
       ``tool`` equals the tool the route mapping expects for THIS route
       (``tool_for_route`` — the caller looks that mapping up from
       contract §C, e.g. via the route's own registration).

    Raises :class:`AssertionInvalid` with a specific ``reason`` on the
    first failing step (never partial — every earlier step already
    passed by construction of ``jwt.decode`` succeeding).
    """
    if not secret_candidates:
        raise AssertionInvalid("no approval_assertion_secrets configured")

    claims: dict[str, Any] | None = None
    last_error: Exception | None = None
    for candidate in secret_candidates:
        try:
            claims = jwt.decode(
                token,
                candidate,
                algorithms=[_ALGORITHM],
                issuer=iss,
                audience=aud,
                options={
                    "require": [
                        "jti",
                        "iss",
                        "aud",
                        "sub",
                        "org",
                        "tool",
                        "method",
                        "path",
                        "body_sha256",
                        "approved_by",
                        "requested_by",
                        "iat",
                        "exp",
                    ]
                },
            )
            break
        except jwt.ExpiredSignatureError as exc:
            # Step 3 failed with an otherwise-valid signature — no point
            # trying the remaining candidates, the token itself is stale.
            raise AssertionInvalid("assertion expired") from exc
        except jwt.InvalidTokenError as exc:
            last_error = exc
            continue

    if claims is None:
        raise AssertionInvalid("assertion signature invalid") from last_error

    # Step 4 — org.
    if claims["org"] != str(org_id):
        raise AssertionInvalid("assertion org does not match the token's org")

    # Step 5 — sub must at least be a well-formed agent id. Callers that
    # hold the token's ``principal_agent_id`` compare it themselves.
    try:
        sub = UUID(str(claims["sub"]))
    except (ValueError, TypeError) as exc:
        raise AssertionInvalid("assertion sub is not a UUID") from exc

    # Step 6 — body hash.
    if claims["body_sha256"] != canonical_body_sha256(body):
        raise AssertionInvalid("assertion body_sha256 does not match the received body")

    # Step 7 — method, path, tool.
    if claims["method"] != method:
        raise AssertionInvalid("assertion method does not match the received request")
    if claims["path"] != path:
        raise AssertionInvalid("assertion path does not match the received request")
    if claims["tool"] != tool_for_route:
        raise AssertionInvalid("assertion tool does not map to this route")

    return VerifiedAssertion(
        jti=UUID(str(claims["jti"])),
        sub=sub,
        org=UUID(str(claims["org"])),
        tool=claims["tool"],
        method=claims["method"],
        path=claims["path"],
        body_sha256=claims["body_sha256"],
        approved_by=UUID(str(claims["approved_by"])),
        requested_by=UUID(str(claims["requested_by"])),
        iat=int(claims["iat"]),
        exp=int(claims["exp"]),
    )
