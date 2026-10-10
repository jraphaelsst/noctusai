"""SSO redemption regime -- ONE predicate, derived from the product catalog.

Phase 2.1 of the SSO identity-hardening roadmap
(``project-history/roadmaps/sso-identity-hardening-2026-10.md``) moves the SSO
token from the query string to the URL fragment and makes ``product_slug``
mandatory at redemption. Products on the OLD ``SSOCallback`` (reads only
``?token=``, sends no slug) must keep working until they are rebuilt, so the
regime is MIXED and derived from ``public.products`` -- never from a hand list:

* ``strict``  -- fragment launch (``/sso#token=``); ``/api/sso/session``
  requires ``product_slug`` == the token's product claim.
* ``legacy``  -- query launch (``/sso?token=``); slug optional (but, when sent,
  still bound to the token's product).

ALLOWLIST: ``legacy`` ONLY for an active, dev-scoped catalog row. Everything
else -- live, NULL/unknown scope, inactive, any future value, a missing row --
is ``strict``. A dev product becomes strict automatically the moment it is
promoted to ``live`` (which must first rebuild it on the current seed).

Strictness comes ONLY from the token's product row; nothing in the request may
influence it.
"""
from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

from noctusai_lib.config.product_urls import resolve_product_url

SSORegime = Literal["strict", "legacy"]


def sso_regime(row: Optional[Mapping[str, Any]]) -> SSORegime:
    """``"legacy"`` iff ``row.ativo is True and row.deploy_scope == "dev"``."""
    if row and row.get("ativo") is True and row.get("deploy_scope") == "dev":
        return "legacy"
    return "strict"


class ProductUrlUnresolvable(Exception):
    """No launch URL can be resolved for the product (no PRODUCT_URL_<SLUG> /
    PRODUCT_URL_PATTERN override and no usable `url_base` row). Routers map it
    to a typed 409 BEFORE minting a token — never a 500 after one."""


def resolve_launch_base(slug: str, product_row: Mapping[str, Any]) -> str:
    """The product's launch base URL, or ProductUrlUnresolvable."""
    try:
        return resolve_product_url(slug, db_url_base=product_row.get("url_base"))
    except ValueError as e:
        raise ProductUrlUnresolvable(str(e)) from e


def build_sso_launch_url(slug: str, product_row: Mapping[str, Any], sso_token: str,
                         base: Optional[str] = None) -> str:
    """Absolute product URL carrying the token in the regime's transport.

    strict -> ``<base>/sso#token=<t>`` (a fragment never reaches an access log
    or a ``Referer``); legacy -> ``<base>/sso?token=<t>``. The base is resolved
    through ``resolve_product_url`` so a deploy overrides the DB-stored URL.
    """
    base = base if base is not None else resolve_launch_base(slug, product_row)
    if sso_regime(product_row) == "legacy":
        return f"{base}/sso?token={sso_token}"
    return f"{base}/sso#token={sso_token}"


# ---------------------------------------------------------------------------
# Browser-bind (roadmap P2.2): launch sets an HttpOnly nonce cookie on core and
# puts hash(nonce) in the token (`bnd`); redeem compares them.
# ---------------------------------------------------------------------------

SSO_BIND_COOKIE_PREFIX = "sso_bnd_"
SSO_BIND_COOKIE_PATH = "/api/sso/session"


def sso_bind_cookie_name(jti: str) -> str:
    """One cookie PER LAUNCH, named after the token's jti: two concurrent
    launches (two tabs, two products) never overwrite each other's nonce."""
    return f"{SSO_BIND_COOKIE_PREFIX}{jti}"


def new_bind_nonce() -> tuple[str, str]:
    """``(nonce, hash)``: the nonce goes ONLY into the Set-Cookie; the hash into the token."""
    import hashlib
    import secrets

    nonce = secrets.token_urlsafe(32)
    return nonce, hashlib.sha256(nonce.encode()).hexdigest()


def bind_matches(nonce: str, bnd: str) -> bool:
    import hashlib
    import hmac

    return hmac.compare_digest(hashlib.sha256(nonce.encode()).hexdigest(), bnd)


def unbound_redeem_allowed(regime: SSORegime) -> bool:
    """May a redeem that carries NO bind cookie proceed?

    NOC-REMEDIATE[sso-unbound-redeem-allow]: True for every regime while the
    fleet still runs SSOCallbacks that never send credentials (legacy
    orbity/p-studio, and any strict product not yet rebuilt). Flip to
    ``regime == "legacy"`` (strict => absent cookie 401s) when the
    ``sso_unbound_redeem`` count for STRICT products is zero for 7 consecutive
    days after the fleet rebuild that carries the credentials:'include'
    SSOCallback (roadmap P2.2 trigger T6). Single switch -- do not inline.
    """
    return True


BindVerdict = Literal["bound", "mismatch", "unbound_allowed", "unbound_rejected", "no_bnd"]


def bind_verdict(cookie_nonce: Optional[str], bnd: Optional[str], *, allow_unbound: bool) -> BindVerdict:
    """Pure browser-bind decision (no I/O, no request).

    ``no_bnd`` -- token minted before P2.2 (no claim): nothing to check.
    ``bound`` -- cookie present and hash matches.  ``mismatch`` -- cookie present,
    hash differs (a relayed token).  Cookie absent: ``unbound_allowed`` or
    ``unbound_rejected`` per ``allow_unbound`` (``unbound_redeem_allowed(regime)``).
    """
    if not bnd:
        return "no_bnd"
    if cookie_nonce is None:
        return "unbound_allowed" if allow_unbound else "unbound_rejected"
    return "bound" if bind_matches(cookie_nonce, bnd) else "mismatch"
