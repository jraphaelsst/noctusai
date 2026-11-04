"""M2M token policy — prefixes, the server-side scope allow-list, rotation.

* **Prefix.** Every new token is ``noc_`` (``NEW_TOKEN_PREFIX``). ``pk_`` is
  still ACCEPTED while live tokens are reissued
  (``NOC-REMEDIATE[pk-prefix-cutoff]`` at each acceptance site); the cutoff
  ships last. Stripe ``pk_`` keys are unrelated.
* **Scope allow-list.** Scopes come from a server-side registry, never from
  request input. A product registers the scopes it serves; mint refuses any
  other. A list built with ``TokenScopeAllowList(...)`` is strict; the
  process-global ``TOKEN_SCOPES`` stays permissive until a product opts in with
  ``TOKEN_SCOPES.enforce()`` (NOC-REMEDIATE[scope-allowlist-strict]: flip the
  default once every consumer registers).
* **Rotate.** mint new -> return it -> revoke old.

See ``KB § PATTERNS/backend/platform-grants.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Iterable, Optional
from uuid import UUID

from noctusai_lib.api.auth._token_prefixes import (
    ACCEPTED_TOKEN_PREFIXES,
    LEGACY_TOKEN_PREFIX,
    NEW_TOKEN_PREFIX,
    has_api_token_prefix,
)

if TYPE_CHECKING:  # pragma: no cover
    from noctusai_lib.api.auth.session.types import AuthContext
    from noctusai_lib.api.auth.session.token_admin import (
        ApiTokenInfo,
        MintedApiToken,
        ProductTokenAdmin,
    )

# Scope of the one-shot token a control plane uses to deliver a grant.
GRANT_RECEIVE_SCOPE = "platform:grant-receive"

__all__ = [
    "ACCEPTED_TOKEN_PREFIXES",
    "GRANT_RECEIVE_SCOPE",
    "LEGACY_TOKEN_PREFIX",
    "NEW_TOKEN_PREFIX",
    "TOKEN_SCOPES",
    "MfaRequiredError",
    "MintPolicy",
    "RotatedToken",
    "TokenScopeAllowList",
    "UnknownTokenScopeError",
    "has_api_token_prefix",
    "rotate_token",
]


class UnknownTokenScopeError(ValueError):
    """A mint asked for scopes the server does not register."""

    def __init__(self, unknown: Iterable[str]) -> None:
        self.unknown = tuple(sorted(set(unknown)))
        super().__init__(f"unknown token scopes: {', '.join(self.unknown)}")


class TokenScopeAllowList:
    """Server-side registry of scopes a token may carry."""

    def __init__(self, scopes: Iterable[str] = (), *, strict: bool = True) -> None:
        self._scopes: set[str] = set(scopes)
        self._strict = strict

    def register(self, *scopes: str) -> None:
        self._scopes.update(scopes)

    def enforce(self) -> None:
        """Make the list refuse unregistered scopes."""
        self._strict = True

    @property
    def strict(self) -> bool:
        return self._strict

    def __contains__(self, scope: object) -> bool:
        return scope in self._scopes

    def validate(self, scopes: Iterable[str]) -> list[str]:
        """Return ``scopes`` as a list, or raise :class:`UnknownTokenScopeError`."""
        wanted = list(scopes)
        if self._strict:
            unknown = [s for s in wanted if s not in self._scopes]
            if unknown:
                raise UnknownTokenScopeError(unknown)
        return wanted


class MfaRequiredError(PermissionError):
    """The mint policy demands an MFA-verified (``aal2``) caller."""


def _mfa_not_required(ctx: "AuthContext") -> bool:
    return False


@dataclass(frozen=True)
class MintPolicy:
    """Who may mint/rotate a token. MFA is NOT required by default; core wires
    ``require_mfa`` to a platform setting (off until the owner turns it on)."""

    require_mfa: Callable[["AuthContext"], bool] = field(default=_mfa_not_required)

    def enforce(self, ctx: "AuthContext") -> None:
        """Raise :class:`MfaRequiredError` when MFA is required and ``ctx`` is not ``aal2``."""
        if self.require_mfa(ctx) and ctx.aal != "aal2":
            raise MfaRequiredError("mfa_required")


# Process-global registry. Permissive until a product calls ``.enforce()``.
TOKEN_SCOPES = TokenScopeAllowList(strict=False)


@dataclass(frozen=True)
class RotatedToken:
    """Result of :func:`rotate_token`: the new token (secret shown once) and the
    revoked predecessor."""

    new: "MintedApiToken"
    old: "ApiTokenInfo"


def rotate_token(
    admin: "ProductTokenAdmin",
    schema: str,
    old_token_id: UUID,
    *,
    org_id: UUID,
    expires_at: Optional[datetime] = None,
    keep_expiry: bool = True,
    minted_by: Optional[UUID] = None,
) -> RotatedToken:
    """Mint a replacement for ``old_token_id`` (same label/scopes/issuer/principal),
    then revoke the old one.

    ``keep_expiry=True`` copies the old ``expires_at`` (NULL stays NULL);
    ``keep_expiry=False`` uses ``expires_at``. If revoking the old token fails
    the new one is revoked again and the error re-raised, so a failed rotation
    never leaves two live tokens.

    Raises:
        LookupError: ``old_token_id`` is not a token of ``org_id`` in ``schema``.
    """
    old = next(
        (t for t in admin.list_tokens(schema, org_id=org_id) if t.id == old_token_id),
        None,
    )
    if old is None:
        raise LookupError(f"token {old_token_id} not found for org {org_id} in {schema}")
    minted = admin.mint(
        schema,
        org_id=org_id,
        label=old.label,
        scopes=list(old.scopes),
        expires_at=old.expires_at if keep_expiry else expires_at,
        principal_agent_id=old.principal_agent_id,
        issuer=old.issuer,
        minted_by=minted_by,
    )
    try:
        revoked = admin.revoke(schema, old.id, org_id=org_id)
    except Exception:
        admin.revoke(schema, minted.info.id, org_id=org_id)
        raise
    if not revoked:
        admin.revoke(schema, minted.info.id, org_id=org_id)
        raise RuntimeError(f"rotate_token: could not revoke old token {old.id}")
    return RotatedToken(new=minted, old=old)
