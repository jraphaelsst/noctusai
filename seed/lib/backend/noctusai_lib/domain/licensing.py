"""Product license gate — "does this org hold an ACTIVE license for this product?"

Round 2 (2026-10-06). A user whose EFFECTIVE org (see
``noctusai_lib.api.auth.effective_org``) has no active license for the product
is blocked server-side on every authenticated API call. The gate lives inside
the seed's trusted auth dependencies, so a product gets it by construction and
writes zero code for it; ``core`` (the dashboard) is exempt.

Shape (CLAUDE.md §1 — Fake + Real + factory):

* :func:`org_has_product_license` — the pure Real check over a ``public``-schema
  service-role client. Fails CLOSED: a DB error raises
  :class:`LicenseCheckUnavailable` (callers answer 503), never "allowed".
  Positive answers are cached in-process for :data:`POSITIVE_TTL_S`; negatives
  are NEVER cached (a freshly granted license must work on the next request).
* :class:`LicenseChecker` Protocol + :class:`RealLicenseChecker` /
  :class:`FakeLicenseChecker` + :func:`make_license_checker` (Fake under pytest
  unless ``force_real=True`` — same precedent as ``make_audit_sink``: a product's
  ``app.main`` is built at import time, before any per-test seam exists).
* :func:`configure_license_gate` / :func:`enforce_license` — the process-level
  gate ``create_product_app`` configures once; the trusted auth deps call
  :func:`enforce_license` at request time. A process that never configured a
  gate (a bare seed-lib unit test) enforces nothing.

There is deliberately NO ``role == 'admin'`` license bypass anywhere: the only
way a superadmin reaches a product he has no home license for is a live
``act_as_sessions`` row, whose target org then has to hold the license.

KB § PATTERNS/backend/tenancy-license-and-act-as.md
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

from fastapi import HTTPException

from noctusai_lib.primitives.roles import is_customer_role

logger = logging.getLogger(__name__)

#: Product slug that is never license-gated (the dashboard itself).
CORE_SLUG = "core"

#: Seconds a POSITIVE license answer is cached in-process.
POSITIVE_TTL_S = 60.0

ORG_SEM_LICENCA_CODE = "org_sem_licenca"
ORG_SEM_LICENCA_MESSAGE = "Sua organização não tem acesso a este produto."


class LicenseCheckUnavailable(RuntimeError):
    """The license lookup could not be answered (DB / transport error)."""


def org_sem_licenca() -> HTTPException:
    """The 403 every license refusal raises — flat ``{"detail", "code"}`` body
    (the seed error shape, see ``primitives.exceptions.http_exception_handler``)."""
    return HTTPException(
        status_code=403,
        detail={"detail": ORG_SEM_LICENCA_MESSAGE, "code": ORG_SEM_LICENCA_CODE},
    )


def _parse_timestamp(value: Any) -> datetime:
    ts = str(value).replace("Z", "+00:00").replace(" ", "T")
    ts = re.sub(r"([+-]\d{2})$", r"\1:00", ts)
    parsed = datetime.fromisoformat(ts)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def license_rows_valid(rows: list[dict], *, now: Optional[datetime] = None) -> bool:
    """``True`` when any ``licenses`` row (already filtered ``status='active'``)
    is permanent (``fim IS NULL``) or ends in the future. An unparseable ``fim``
    is skipped + logged, never treated as valid."""
    now = now or datetime.now(timezone.utc)
    for lic in rows:
        fim = lic.get("fim")
        if fim is None:
            return True
        try:
            if _parse_timestamp(fim) > now:
                return True
        except (ValueError, TypeError) as exc:
            logger.warning(
                "licensing: license id=%s has unparseable fim=%r (%s); skipping",
                lic.get("id"), fim, exc,
            )
    return False


# ---------------------------------------------------------------------------
# Real check
# ---------------------------------------------------------------------------

_cache: dict[tuple[str, str], float] = {}
_cache_lock = threading.Lock()


def clear_license_cache() -> None:
    """Drop every cached positive answer (tests, and an explicit revoke path)."""
    with _cache_lock:
        _cache.clear()


def _product_row(core_client: Any, product_slug: str) -> Optional[dict]:
    result = (
        core_client.table("products")
        .select("id, aceita_clientes")
        .eq("slug", product_slug)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def org_has_product_license(
    core_client: Any,
    org_id: Any,
    product_slug: str,
    *,
    ttl_s: float = POSITIVE_TTL_S,
) -> bool:
    """Does ``org_id`` hold an ACTIVE, non-expired license for ``product_slug``?

    ``core_client`` MUST be the ``public``-schema service-role client
    (``DatabaseModule.get_core_client()``). A slug with no ``products`` row has
    no license by definition (``False``). Raises :class:`LicenseCheckUnavailable`
    on any lookup error — fail closed, never "allowed".
    """
    if not org_id or not product_slug:
        return False
    key = (str(org_id), product_slug)
    now_mono = time.monotonic()
    with _cache_lock:
        expires = _cache.get(key)
        if expires is not None and expires > now_mono:
            return True
    try:
        product = _product_row(core_client, product_slug)
        if product is None:
            return False
        result = (
            core_client.table("licenses")
            .select("id, fim")
            .eq("org_id", str(org_id))
            .eq("product_id", product["id"])
            .eq("status", "active")
            .execute()
        )
    except Exception as exc:
        logger.error(
            "license_lookup_error org=%s product=%s — failing closed",
            org_id, product_slug, exc_info=True,
        )
        raise LicenseCheckUnavailable(str(exc)) from exc
    if license_rows_valid(result.data or []):
        with _cache_lock:
            _cache[key] = now_mono + ttl_s
        return True
    return False


def org_has_license_for_product_id(core_client: Any, org_id: Any, product_id: Any) -> bool:
    """Uncached form of the check keyed by ``products.id`` (core's SSO flows
    already hold the product row). Same validity rule, one source of truth
    (:func:`license_rows_valid`); lookup errors propagate (fail closed)."""
    if not org_id or not product_id:
        return False
    result = (
        core_client.table("licenses")
        .select("id, fim")
        .eq("org_id", str(org_id))
        .eq("product_id", product_id)
        .eq("status", "active")
        .execute()
    )
    return license_rows_valid(result.data or [])


def licensed_product_ids(core_client: Any, org_id: Any) -> list:
    """``products.id`` of every product ``org_id`` holds a valid license for."""
    result = (
        core_client.table("licenses")
        .select("id, product_id, fim")
        .eq("org_id", str(org_id))
        .eq("status", "active")
        .execute()
    )
    out: list = []
    for lic in result.data or []:
        if license_rows_valid([lic]) and lic["product_id"] not in out:
            out.append(lic["product_id"])
    return out


def product_accepts_customers(core_client: Any, product_slug: str) -> bool:
    """``products.aceita_clientes`` for ``product_slug`` (``False`` when no row).
    Raises :class:`LicenseCheckUnavailable` on a lookup error."""
    try:
        product = _product_row(core_client, product_slug)
    except Exception as exc:
        logger.error(
            "license_lookup_error product=%s (aceita_clientes) — failing closed",
            product_slug, exc_info=True,
        )
        raise LicenseCheckUnavailable(str(exc)) from exc
    return bool(product and product.get("aceita_clientes"))


# ---------------------------------------------------------------------------
# Checker Protocol + Fake + Real + factory
# ---------------------------------------------------------------------------


class LicenseChecker(Protocol):
    def has_license(self, org_id: Any, product_slug: str) -> bool: ...

    def accepts_customers(self, product_slug: str) -> bool: ...


class RealLicenseChecker:
    """Reads ``public.licenses`` / ``public.products`` via the core client."""

    def __init__(self, get_core_client: Callable[[], Any]) -> None:
        self._get_core_client = get_core_client

    def has_license(self, org_id: Any, product_slug: str) -> bool:
        return org_has_product_license(self._get_core_client(), org_id, product_slug)

    def accepts_customers(self, product_slug: str) -> bool:
        return product_accepts_customers(self._get_core_client(), product_slug)


@dataclass
class FakeLicenseChecker:
    """In-memory checker. ``allow_all=True`` (the pytest default) licenses
    everyone; otherwise only ``licensed`` ``(org_id, slug)`` pairs pass.
    ``unavailable=True`` simulates a DB outage (raises)."""

    allow_all: bool = True
    licensed: set[tuple[str, str]] = field(default_factory=set)
    customer_slugs: set[str] = field(default_factory=set)
    unavailable: bool = False
    calls: list[tuple[str, str]] = field(default_factory=list)

    def has_license(self, org_id: Any, product_slug: str) -> bool:
        self.calls.append((str(org_id), product_slug))
        if self.unavailable:
            raise LicenseCheckUnavailable("fake outage")
        return self.allow_all or (str(org_id), product_slug) in self.licensed

    def accepts_customers(self, product_slug: str) -> bool:
        if self.unavailable:
            raise LicenseCheckUnavailable("fake outage")
        return self.allow_all or product_slug in self.customer_slugs


def make_license_checker(
    get_core_client: Optional[Callable[[], Any]] = None,
    *,
    force_real: bool = False,
) -> LicenseChecker:
    """Real checker normally; allow-all Fake under pytest unless ``force_real``
    (see module docstring). No ``get_core_client`` ⇒ Fake."""
    if not force_real and "pytest" in sys.modules:
        return FakeLicenseChecker()
    if get_core_client is None:
        return FakeLicenseChecker()
    return RealLicenseChecker(get_core_client)


# ---------------------------------------------------------------------------
# Process-level gate (configured once by create_product_app)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LicenseGate:
    product_slug: str
    checker: LicenseChecker
    exempt: bool = False
    #: ``() -> public-schema service-role client`` — lets the BASE auth dependency
    #: (``make_get_current_user`` / ``ProductDependencies.get_current_user``)
    #: resolve the caller's effective org without any per-product wiring.
    get_core_client: Optional[Callable[[], Any]] = None

    @property
    def enforcing(self) -> bool:
        """``False`` for core and for the permissive pytest Fake (allow-all) — the
        base dep then skips the effective-org lookup entirely (zero extra queries)."""
        if self.exempt:
            return False
        return not (isinstance(self.checker, FakeLicenseChecker) and self.checker.allow_all)


_gate: Optional[LicenseGate] = None


def configure_license_gate(
    product_slug: Optional[str],
    checker: Optional[LicenseChecker] = None,
    *,
    exempt: bool = False,
    get_core_client: Optional[Callable[[], Any]] = None,
) -> None:
    """Install (or, with ``product_slug=None``, remove) the process gate.

    ``core`` is always exempt, whatever ``exempt`` says."""
    global _gate
    if product_slug is None or checker is None:
        _gate = None
        return
    _gate = LicenseGate(
        product_slug=product_slug,
        checker=checker,
        exempt=exempt or product_slug == CORE_SLUG,
        get_core_client=get_core_client,
    )


def get_license_gate() -> Optional[LicenseGate]:
    return _gate


def enforce_license(org_id: Any, org_role: Optional[str], *, allow_customer: bool = False) -> None:
    """Raise 403 ``org_sem_licenca`` (or 503 on a lookup outage) unless
    ``org_id`` may use this product. No gate configured / core ⇒ no-op.

    A customer (``org_role`` in ``CUSTOMER_ORG_ROLES``) that a route admits via
    ``allow_customer=True`` needs the license AND ``products.aceita_clientes``.
    """
    gate = _gate
    if gate is None or gate.exempt or not org_id:
        return
    try:
        if not gate.checker.has_license(org_id, gate.product_slug):
            raise org_sem_licenca()
        if allow_customer and is_customer_role(org_role):
            if not gate.checker.accepts_customers(gate.product_slug):
                raise org_sem_licenca()
    except LicenseCheckUnavailable:
        raise HTTPException(
            status_code=503, detail="Falha ao verificar a licença da organização"
        )


def enforce_license_for_user(user_id: Any) -> None:
    """License gate for the BASE authenticated dependency (auth without an org
    lookup): resolve the caller's EFFECTIVE org (act-as aware) and enforce.

    No gate / core / permissive Fake ⇒ no-op with NO queries. A caller with no
    ``noctus_users`` row or no org reaches no tenant data (every org-scoped dep
    already 403s them), so there is nothing to license — passes through.
    A lookup error fails closed (503). Customers are checked with
    ``allow_customer=True`` (license AND ``products.aceita_clientes``).
    """
    gate = _gate
    if gate is None or not gate.enforcing or gate.get_core_client is None or user_id is None:
        return
    from noctusai_lib.api.auth.effective_org import resolve_effective_org

    try:
        eff = resolve_effective_org(gate.get_core_client(), user_id)
    except Exception:
        logger.error("license_gate_org_lookup_error user_id=%s — failing closed", user_id, exc_info=True)
        raise HTTPException(status_code=503, detail="Falha ao resolver organizacao do usuario")
    if eff is None or not eff.org_id:
        return
    enforce_license(eff.org_id, eff.org_role, allow_customer=True)


__all__ = [
    "enforce_license_for_user",
    "CORE_SLUG",
    "FakeLicenseChecker",
    "LicenseChecker",
    "LicenseCheckUnavailable",
    "LicenseGate",
    "ORG_SEM_LICENCA_CODE",
    "ORG_SEM_LICENCA_MESSAGE",
    "RealLicenseChecker",
    "clear_license_cache",
    "configure_license_gate",
    "enforce_license",
    "get_license_gate",
    "license_rows_valid",
    "make_license_checker",
    "licensed_product_ids",
    "org_has_license_for_product_id",
    "org_has_product_license",
    "org_sem_licenca",
    "product_accepts_customers",
]
