"""The ONE effective-org resolver every trusted auth path routes through.

"Which org is this request for?" is answered here, once; every path calls it, so
the license gate and every org-scoped read agree on the org.

Trust model (never weakened): everything comes from the trusted
``public.noctus_users`` row (``org_id`` + ``org_role`` + ``role``) and the
``public.platform_org_selections`` row; ``user_metadata`` is never consulted.

**Home by default.** A caller's effective org is their own home org (for a multi-org
member: their LAST-ACTIVE org -- ``noctus_users.org_id`` follows their selection, owner
decision Q3, 2026-10-13). The ONE exception is the platform org picker (owner decision
2026-10-08): PLATFORM STAFF (``noctus_users.role='admin'`` AND home org ``is_platform``)
with a LIVE selection for this product -- bound to THIS login (the token's ``session_id``),
made at ``aal2``, target still licensed -- resolve to the selected org with the ``owner``
role. Anyone else resolves home...

**...except a MEMBER on a picker-ready product (multi-org S2 2026-10-13; owner decisions
D1/D5 2026-10-14).** An ELIGIBLE org is an ACTIVE, non-customer ``public.org_memberships`` row
whose org is licensed for the product and in which the user is NOT blocked from the product
(``org_member_product_access``, D5) -- all re-read on EVERY request (revocation by recheck;
nothing in the JWT). A live selection of an eligible org (same login binding) resolves to it
with the role **of that membership**, never the home profile role (owner in A + member in B is
a member in B). Without one: >=2 eligible orgs -> ``409 org_selection_required`` on every
gated path (the choice is made on every entry, D1); exactly one -> that org, silently, with
its membership role; none -> the home org (the license gate then judges it). No ``aal2`` for
members (Q1). A home org the user is no longer an ACTIVE member of -- or is blocked from the
product in (D5, on ANY product with a gate, picker-ready or not) -- is never served.

**Every entry is a choice** (owner decision 2026-10-12). Staff on a picker-ready product
with NO valid live selection do NOT silently resolve home on a GATED path: the resolver
refuses ``409 org_selection_required`` (``require_selection=True``, the default) so no
product data is served until the picker has been answered. Only the ungated
``/api/me/access`` (which must answer so the picker can load) passes
``require_selection=False`` and gets the staff home snapshot. Staff whose token lacks
the required ``aal2`` keep the MFA path unchanged (home + ``mfa_required``). The
``X-Noctus-Acting-Org`` header is an intent pin: when present and different from the
resolved org the request is refused ``409 org_selection_changed`` (the SPA refetches
and reopens the picker). It only NARROWS -- it can refuse a request, never widen one; on a
product without the picker it is ignored.

The NoctusAI platform org reaches every product because it holds an active license
for every product by construction (core 068), not because of any role check here.

KB § PATTERNS/backend/tenancy-license-gate.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

from fastapi import HTTPException

from noctusai_lib.api.audit.types import AuditActor
from noctusai_lib.api.auth._blocking import run_parallel
from noctusai_lib.api.auth.mfa.aal import read_session_claims
from noctusai_lib.primitives.roles import is_customer_role

logger = logging.getLogger(__name__)

#: ``noctus_users.role`` of platform staff. Read ONLY from the trusted row.
STAFF_ROLE = "admin"
#: The org role an acting staff member has inside the selected org.
ACTING_ORG_ROLE = "owner"
#: Home ``org_role`` platform staff additionally needs (superadmin flag + platform org + this).
STAFF_ORG_ROLES = frozenset({"owner", "admin"})
#: Audit role stamped on rows written while acting (the client sees "Suporte NoctusAI").
ACTING_AUDIT_ROLE = "platform_support"
#: Intent-pin request header (also PostgREST: helper treats it as narrowing only).
ACTING_ORG_HEADER = "x-noctus-acting-org"
ORG_SELECTION_CHANGED_CODE = "org_selection_changed"
#: 409 code: platform staff on a picker-ready product with no live selection reached a
#: gated route -- the SPA must (re)open the required picker; nothing resolves home.
ORG_SELECTION_REQUIRED_CODE = "org_selection_required"


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
    #: A non-staff MEMBER on a picker-ready product holding >=2 eligible orgs (the switcher).
    member_can_select: bool = False
    #: A member with >=2 eligible orgs and no valid live selection: a choice is required
    #: (only observable on the ungated bootstrap path -- gated paths raise 409).
    member_choice_required: bool = False
    #: A member's ELIGIBLE orgs for this product as ``((org_id, org_role), ...)`` (D1): active,
    #: non-customer, licensed, not blocked. Empty when not evaluated (staff, not-ready product).
    eligible: tuple[tuple[str, str], ...] = ()

    @property
    def acting(self) -> bool:
        """Platform staff acting inside another org (a member in their own selected org is
        never "acting": their profile follows the selection, and their audit actor is plain)."""
        return self.is_staff and self.selection_id is not None and self.org_id != self.home_org_id


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


def org_selection_required() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "detail": "Selecione a organização para continuar.",
            "code": ORG_SELECTION_REQUIRED_CODE,
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


class _Prefetched:
    """A read issued ALONGSIDE the ``noctus_users`` row instead of after it (one Supabase round
    trip of wall time saved on every gated request). Which branch consumes it is only known once
    the row is in, so its outcome is held: :meth:`get` returns the value or re-raises the read's
    own error at the point of use -- a branch that needs it fails closed exactly as a serial read
    would; a branch that does not need it is never failed by it."""

    __slots__ = ("_ok", "_value")

    def __init__(self, fn: Callable[[], Any]) -> None:
        try:
            self._ok, self._value = True, fn()
        except Exception as exc:  # held, re-raised by get() on the branch that reads it
            self._ok, self._value = False, exc

    def get(self) -> Any:
        if not self._ok:
            raise self._value
        return self._value


def _prefetch(fn: Callable[[], Any]) -> Callable[[], _Prefetched]:
    return lambda: _Prefetched(fn)


#: The profile read. The home org's ``is_platform`` rides along as a PostgREST embed (through
#: ``noctus_users_org_id_fkey``) -- the staff rule needs it, and a separate read after the row
#: was a second serial round trip on every staff request.
PROFILE_COLUMNS = "org_id, org_role, role, organizations(is_platform)"


def staff_role_of(row: Optional[dict]) -> Optional[str]:
    """The staff rule over ONE profile row read with the home org embedded (see
    :data:`PROFILE_COLUMNS`): ``"owner"`` | ``"admin"`` for platform staff, else ``None``. A row
    without the embed is not staff (fail closed)."""
    if not row:
        return None
    home = row.get("organizations") or {}
    if (
        row.get("role") == STAFF_ROLE
        and row.get("org_role") in STAFF_ORG_ROLES
        and bool(row.get("org_id"))
        and bool(home.get("is_platform"))
    ):
        return str(row.get("org_role"))
    return None


def platform_staff_role(core_client: Any, user_id: Any) -> Optional[str]:
    """``"owner"`` | ``"admin"`` for PLATFORM STAFF, else ``None``. Staff = ``noctus_users.role
    ='admin'`` AND home ``org_role`` owner/admin AND the home org ``is_platform`` -- an explicit
    grant, NEVER derived from ``org_role`` alone. The returned role is the platform-org role:
    ``owner`` is THE NoctusAI owner (owner decision D2, 2026-10-14: the only one who may override
    the last-owner rule), ``admin`` a NoctusAI admin. SQL twin: ``public.platform_staff_role``
    (core ``member_access_rules``). Raises on a DB error (callers fail closed)."""
    if user_id is None:
        return None
    rows = (
        _tbl(core_client, "noctus_users").select(PROFILE_COLUMNS)
        .eq("id", str(user_id)).limit(1).execute().data or []
    )
    return staff_role_of(rows[0] if rows else None)


def is_platform_staff(core_client: Any, user_id: Any) -> bool:
    """Trusted check: :func:`platform_staff_role` is not ``None``. Raises on a DB error."""
    return platform_staff_role(core_client, user_id) is not None


def acting_audit_actor(user_id: Any, eff: Optional["EffectiveOrg"]) -> Optional[AuditActor]:
    """The client-visible audit actor for a request made while ACTING in a customer org
    (``org_id`` = the target, tagged with the home org + selection id), else ``None``."""
    if eff is None or not eff.acting:
        return None
    return AuditActor(
        user_id=str(user_id) if user_id is not None else None,
        org_id=eff.org_id, role=ACTING_AUDIT_ROLE,
        acting_org_id=eff.home_org_id, act_as_session_id=eff.selection_id,
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
    require_selection: bool = True,
) -> Optional[EffectiveOrg]:
    """The caller's effective org, or ``None`` when no ``noctus_users`` row.

    ``require_selection`` (default ``True`` -- every gated path): platform staff on a
    picker-ready product whose token passes the MFA requirement but who hold no valid
    live selection are refused ``409 org_selection_required`` instead of resolving home.
    ``False`` only for the ungated picker bootstrap (``/api/me/access``).

    ``core_client`` MUST be the ``public``-schema service-role client. ``product_slug``
    is REQUIRED (``None`` only for core / an unconfigured process: no picker). Without
    ``token`` + ``selection_store`` the answer is simply the home org. Raises on a DB /
    transport error (callers fail closed -- never a metadata fallback), on a lapsed
    license lookup (``LicenseCheckUnavailable``), and 409 on an intent-pin mismatch.
    """
    if user_id is None:
        return None
    from noctusai_lib.domain.licensing import CORE_SLUG

    def _user_rows() -> list:
        return (
            _tbl(core_client, "noctus_users").select(PROFILE_COLUMNS)
            .eq("id", str(user_id)).limit(1).execute().data or []
        )

    picker = selection_store is not None and bool(product_slug) and product_slug != CORE_SLUG
    ready = picker and bool(token) and selection_store.product_ready(product_slug)
    # The reads below depend only on (user_id, product_slug), never on the row: issue them WITH
    # the row read. Every branch that runs consumes the ones it needs (revocation by recheck is
    # unchanged -- still fresh reads on this very request, never cached).
    session_id: Optional[str] = None
    aal = "aal1"
    memberships = blocked = live = None
    if not picker:
        rows = _user_rows()
    elif not ready:
        rows, blocked = run_parallel(
            _user_rows, _prefetch(lambda: selection_store.blocked_orgs(user_id, product_slug)),
        )
    else:
        session_id, aal = read_session_claims(token, user_id=user_id)
        sid = session_id
        rows, memberships, blocked, live = run_parallel(
            _user_rows,
            _prefetch(lambda: selection_store.memberships(user_id)),
            _prefetch(lambda: selection_store.blocked_orgs(user_id, product_slug)),
            _prefetch(lambda: selection_store.live(user_id, product_slug) if sid else None),
        )
    if not rows:
        return None
    row = rows[0]
    home = EffectiveOrg(org_id=row.get("org_id"), org_role=row.get("org_role"), home_org_id=row.get("org_id"))

    if not picker:
        return home
    if not ready:
        # D5: a member blocked from this product in their home org is never served it.
        if home.org_id and str(home.org_id) in blocked.get():
            return EffectiveOrg(org_id=None, org_role=None, home_org_id=home.org_id)
        return home
    if staff_role_of(row) is None:
        return _resolve_member(
            user_id, home, product_slug=product_slug, token=token, acting_header=acting_header,
            selection_store=selection_store, license_checker=license_checker,
            require_selection=require_selection, prefetched=(memberships, blocked, live),
        )

    mfa_ok = aal == "aal2" or not selection_store.requires_mfa(product_slug)
    staff_home = EffectiveOrg(
        org_id=home.org_id, org_role=home.org_role, home_org_id=home.org_id,
        is_staff=True, mfa_required=not mfa_ok,
    )
    eff = staff_home
    if session_id and mfa_ok:
        sel = live.get()
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
    if require_selection and mfa_ok and eff.selection_id is None:
        raise org_selection_required()
    return eff


def _resolve_member(
    user_id: Any,
    home: EffectiveOrg,
    *,
    product_slug: str,
    token: str,
    acting_header: Optional[str],
    selection_store: Any,
    license_checker: Any,
    require_selection: bool,
    prefetched: tuple[_Prefetched, _Prefetched, _Prefetched],
) -> EffectiveOrg:
    """The effective org of a NON-staff user on a picker-ready product (S2 + owner D1/D5).

    Trust: the selection row (``selection_store.live``) says WHAT was chosen; whether the user
    may still act there is re-read from ``org_memberships`` (``selection_store.memberships``) and
    the D5 blocks (``selection_store.blocked_orgs``) on this very request, so ending a membership
    or blocking the product ends the selection at once. The role is the membership's role in the
    effective org -- never the home profile role. No aal2 (Q1).

    ELIGIBLE = ACTIVE, non-customer, licensed for the product, not blocked. A valid selection
    wins; else >=2 eligible -> a choice (409 on gated paths, D1: every entry); exactly 1 -> that
    org silently; 0 -> the home org when it is still an ACTIVE, unblocked membership (the license
    gate judges it -- an end customer's home lands here), else no org. SQL twin:
    ``current_org_id_for`` (parity: ``verify_db_guards`` member probes)."""
    pin = _clean_header(acting_header)

    def _pinned(eff: EffectiveOrg) -> EffectiveOrg:
        if pin is not None and eff.org_id is not None and pin != str(eff.org_id).lower():
            raise org_selection_changed()
        return eff

    if is_customer_role(home.org_role):
        # An end customer never picks an org; the license gate judges home (SQL: the member
        # branch is skipped for a customer profile and the home rule answers NULL).
        if home.org_id and str(home.org_id) in prefetched[1].get():
            return EffectiveOrg(org_id=None, org_role=None, home_org_id=home.org_id)
        return _pinned(home)
    session_id, _aal = read_session_claims(token, user_id=user_id)

    def licensed(org_id: Any) -> bool:
        return license_checker is None or bool(license_checker.has_license(org_id, product_slug))

    # Three independent fresh reads (revocation by recheck: still never cached), issued by
    # resolve_effective_org together with the noctus_users row -- one round trip, not four.
    memberships, blocked, sel = (p.get() for p in prefetched)
    active = {str(m.org_id): m for m in memberships}
    eligible = {
        org: m for org, m in active.items()
        if not is_customer_role(m.org_role) and org not in blocked and licensed(org)
    }
    eligible_view = tuple(sorted((org, m.org_role) for org, m in eligible.items()))
    choice_required = False
    if sel is not None and sel.auth_session_id == session_id and str(sel.target_org_id) in eligible:
        m = eligible[str(sel.target_org_id)]
        eff = EffectiveOrg(
            org_id=str(sel.target_org_id), org_role=m.org_role,
            home_org_id=home.org_id, selection_id=sel.id,
        )
    elif len(eligible) >= 2:
        choice_required = True
        if require_selection:
            raise org_selection_required()
        home_eligible = eligible.get(str(home.org_id)) if home.org_id else None
        eff = EffectiveOrg(
            org_id=home.org_id if home_eligible else None,
            org_role=home_eligible.org_role if home_eligible else None,
            home_org_id=home.org_id,
        )
    elif len(eligible) == 1:
        (org, m), = eligible.items()
        eff = EffectiveOrg(org_id=org, org_role=m.org_role, home_org_id=home.org_id)
    else:
        home_member = active.get(str(home.org_id)) if home.org_id else None
        if home_member is None or str(home.org_id) in blocked:
            eff = EffectiveOrg(org_id=None, org_role=None, home_org_id=home.org_id)
        else:
            eff = EffectiveOrg(
                org_id=home.org_id, org_role=home_member.org_role, home_org_id=home.org_id,
            )
    eff = replace(
        eff, member_can_select=len(eligible) >= 2, member_choice_required=choice_required,
        eligible=eligible_view,
    )
    return _pinned(eff)


def resolve_effective_org_for_request(
    core_client: Any,
    user_id: Any,
    *,
    token: Optional[str] = None,
    acting_header: Optional[str] = None,
    require_selection: bool = True,
) -> Optional[EffectiveOrg]:
    """:func:`resolve_effective_org` with the process license gate's product slug,
    selection store and license checker (what ``create_product_app`` configured).
    No gate configured / core => the home org. ``require_selection`` as there."""
    from noctusai_lib.api.request_memo import memoize_for_request
    from noctusai_lib.domain.licensing import get_license_gate

    gate = get_license_gate()
    if gate is None or gate.exempt:
        slug = None

        def _compute() -> Optional[EffectiveOrg]:
            return resolve_effective_org(core_client, user_id, product_slug=None)
    else:
        slug = gate.product_slug

        def _compute() -> Optional[EffectiveOrg]:
            return resolve_effective_org(
                core_client, user_id, product_slug=gate.product_slug, token=token,
                acting_header=acting_header, selection_store=gate.selection_store,
                license_checker=gate.checker, require_selection=require_selection,
            )

    # Per-request memo (never across requests): the base auth dep, the licence gate and the
    # organ auth wrapper all ask this for the same request. Keyed on EVERY input that changes
    # the answer; errors are never stored (memoize_for_request), so a failure re-fails closed.
    return memoize_for_request(
        ("effective_org", id(core_client), str(user_id), token, acting_header, slug,
         bool(require_selection), gate is None or gate.exempt),
        _compute,
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
    "ACTING_AUDIT_ROLE",
    "ACTING_ORG_ROLE",
    "STAFF_ORG_ROLES",
    "acting_audit_actor",
    "ORG_SELECTION_CHANGED_CODE",
    "ORG_SELECTION_REQUIRED_CODE",
    "STAFF_ROLE",
    "EffectiveOrg",
    "is_platform_staff",
    "platform_staff_role",
    "PROFILE_COLUMNS",
    "staff_role_of",
    "org_selection_changed",
    "org_selection_required",
    "resolve_effective_org",
    "resolve_effective_org_for_request",
    "resolve_effective_org_via",
]
