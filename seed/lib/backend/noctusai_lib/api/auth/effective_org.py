"""The ONE effective-org resolver every trusted auth path routes through.

"Which org is this request for?" is answered here, once; every path calls it, so
the license gate and every org-scoped read agree on the org.

Trust model (never weakened): everything comes from the trusted
``public.noctus_users`` row (``org_id`` + ``org_role`` + ``role``) and the
``public.platform_org_selections`` row; ``user_metadata`` is never consulted.

**Home by default.** A caller's effective org is their own home org. The ONE
exception is the platform org picker (owner decision 2026-10-08): PLATFORM STAFF
(``noctus_users.role='admin'`` AND home org ``is_platform``) with a LIVE selection
for this product -- bound to THIS login (the token's ``session_id``), made at
``aal2``, target still licensed -- resolve to the selected org with the ``owner``
role. Anyone else, and staff without a valid selection, resolve home. The
``X-Noctus-Acting-Org`` header is an intent pin: when present and different from the
resolved org the request is refused ``409 org_selection_changed`` (the SPA refetches
and reopens the picker); for non-staff it is ignored.

The NoctusAI platform org reaches every product because it holds an active license
for every product by construction (core 068), not because of any role check here.

KB § PATTERNS/backend/tenancy-license-gate.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import HTTPException

from noctusai_lib.api.auth.mfa.aal import read_session_claims
from noctusai_lib.primitives.roles import is_customer_role

logger = logging.getLogger(__name__)

#: ``noctus_users.role`` of platform staff. Read ONLY from the trusted row.
STAFF_ROLE = "admin"
#: The org role an acting staff member has inside the selected org.
ACTING_ORG_ROLE = "owner"
#: Intent-pin request header (also PostgREST: helper treats it as narrowing only).
ACTING_ORG_HEADER = "x-noctus-acting-org"
ORG_SELECTION_CHANGED_CODE = "org_selection_changed"


@dataclass(frozen=True)
class EffectiveOrg:
    org_id: Optional[str]
    org_role: Optional[str]
    home_org_id: Optional[str] = None
    #: Live selection id when staff is acting through the picker (target may equal home).
    selection_id: Optional[str] = None
    #: Evaluated ONLY on a picker-ready product with a token; ``False`` = not staff OR not evaluated.
    is_staff: bool = False
    #: Staff on a picker-ready product whose token is not aal2.
    mfa_required: bool = False

    @property
    def acting(self) -> bool:
        return self.selection_id is not None and self.org_id != self.home_org_id


def _tbl(client: Any, name: str):
    """``client.table(name)``; ``from_`` for clients that only expose that alias
    (both exist on a real Supabase client -- the seed's two historical call styles)."""
    fn = getattr(client, "table", None) or client.from_
    return fn(name)


def org_selection_changed() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "detail": "A organização selecionada mudou. Selecione novamente.",
            "code": ORG_SELECTION_CHANGED_CODE,
        },
    )


def _clean_header(value: Any) -> Optional[str]:
    """A usable ``X-Noctus-Acting-Org`` value (``str``, non-blank) else ``None`` -- a
    direct (non-HTTP) call of a dependency hands us FastAPI's ``Header`` default object."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value.lower() or None


def acting_header_of(request: Any) -> Optional[str]:
    """The raw ``X-Noctus-Acting-Org`` value of a request-like (``None`` for no request /
    a stand-in without headers -- the direct-call shape of a dependency)."""
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    return headers.get(ACTING_ORG_HEADER)


def _home_is_platform(core_client: Any, org_id: Any) -> bool:
    if not org_id:
        return False
    rows = (
        _tbl(core_client, "organizations").select("is_platform")
        .eq("id", str(org_id)).limit(1).execute().data or []
    )
    return bool(rows and rows[0].get("is_platform"))


def is_platform_staff(core_client: Any, user_id: Any) -> bool:
    """Trusted check: ``noctus_users.role='admin'`` AND the home org ``is_platform`` (and the
    home ``org_role`` is not a customer role). Explicit grant only -- NEVER derived from
    ``org_role``. Raises on a DB error (callers fail closed)."""
    if user_id is None:
        return False
    rows = (
        _tbl(core_client, "noctus_users").select("org_id, org_role, role")
        .eq("id", str(user_id)).limit(1).execute().data or []
    )
    if not rows:
        return False
    row = rows[0]
    return (
        row.get("role") == STAFF_ROLE
        and not is_customer_role(row.get("org_role"))
        and _home_is_platform(core_client, row.get("org_id"))
    )


def resolve_effective_org(
    core_client: Any,
    user_id: Any,
    *,
    product_slug: Optional[str],
    token: Optional[str] = None,
    acting_header: Optional[str] = None,
    selection_store: Any = None,
    license_checker: Any = None,
) -> Optional[EffectiveOrg]:
    """The caller's effective org, or ``None`` when no ``noctus_users`` row.

    ``core_client`` MUST be the ``public``-schema service-role client. ``product_slug``
    is REQUIRED (``None`` only for core / an unconfigured process: no picker). Without
    ``token`` + ``selection_store`` the answer is simply the home org. Raises on a DB /
    transport error (callers fail closed -- never a metadata fallback), on a lapsed
    license lookup (``LicenseCheckUnavailable``), and 409 on an intent-pin mismatch.
    """
    if user_id is None:
        return None
    rows = (
        _tbl(core_client, "noctus_users").select("org_id, org_role, role")
        .eq("id", str(user_id)).limit(1).execute().data or []
    )
    if not rows:
        return None
    row = rows[0]
    home = EffectiveOrg(org_id=row.get("org_id"), org_role=row.get("org_role"), home_org_id=row.get("org_id"))
    from noctusai_lib.domain.licensing import CORE_SLUG

    if (
        row.get("role") != STAFF_ROLE
        or not token
        or selection_store is None
        or not product_slug
        or product_slug == CORE_SLUG
        or is_customer_role(row.get("org_role"))
        or not selection_store.product_ready(product_slug)
        or not _home_is_platform(core_client, home.org_id)
    ):
        return home

    session_id, aal = read_session_claims(token, user_id=user_id)
    staff_home = EffectiveOrg(
        org_id=home.org_id, org_role=home.org_role, home_org_id=home.org_id,
        is_staff=True, mfa_required=(aal != "aal2"),
    )
    eff = staff_home
    if session_id and aal == "aal2":
        sel = selection_store.live(user_id, product_slug)
        if (
            sel is not None
            and sel.auth_session_id == session_id
            and (license_checker is None or license_checker.has_license(sel.target_org_id, product_slug))
        ):
            same = str(sel.target_org_id) == str(home.org_id)
            eff = EffectiveOrg(
                org_id=sel.target_org_id,
                org_role=home.org_role if same else ACTING_ORG_ROLE,
                home_org_id=home.org_id, selection_id=sel.id, is_staff=True, mfa_required=False,
            )
    pin = _clean_header(acting_header)
    if pin is not None and pin != str(eff.org_id).lower():
        raise org_selection_changed()
    return eff


def resolve_effective_org_for_request(
    core_client: Any,
    user_id: Any,
    *,
    token: Optional[str] = None,
    acting_header: Optional[str] = None,
) -> Optional[EffectiveOrg]:
    """:func:`resolve_effective_org` with the process license gate's product slug,
    selection store and license checker (what ``create_product_app`` configured).
    No gate configured / core => the home org."""
    from noctusai_lib.domain.licensing import get_license_gate

    gate = get_license_gate()
    if gate is None or gate.exempt:
        return resolve_effective_org(core_client, user_id, product_slug=None)
    return resolve_effective_org(
        core_client, user_id, product_slug=gate.product_slug, token=token,
        acting_header=acting_header, selection_store=gate.selection_store,
        license_checker=gate.checker,
    )


def resolve_effective_org_via(
    get_core_client_fn: Callable[[], Any], user_id: Any,
    *, token: Optional[str] = None, acting_header: Optional[str] = None,
) -> Optional[EffectiveOrg]:
    """:func:`resolve_effective_org_for_request` taking the client accessor the seed factories hold."""
    return resolve_effective_org_for_request(
        get_core_client_fn(), user_id, token=token, acting_header=acting_header
    )


__all__ = [
    "ACTING_ORG_HEADER",
    "ACTING_ORG_ROLE",
    "ORG_SELECTION_CHANGED_CODE",
    "STAFF_ROLE",
    "EffectiveOrg",
    "is_platform_staff",
    "org_selection_changed",
    "resolve_effective_org",
    "resolve_effective_org_for_request",
    "resolve_effective_org_via",
]
