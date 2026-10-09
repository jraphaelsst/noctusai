"""Platform org picker -- the live-selection store (Protocol + Real + Fake + factory).

Platform staff (``noctus_users.role='admin'`` AND home org ``is_platform``) pick, once
per product per LOGIN (Supabase auth ``session_id``), which org they work in. The
selection lives in ``public.platform_org_selections`` (core 070, service-role only);
this module is the ONLY Python reader/writer. All writes go through the SECURITY DEFINER
RPCs ``platform_org_selection_set`` / ``platform_org_selection_end``, which re-check
staff + license themselves -- the server is the authority, the SPA only asks.

* :class:`RealOrgSelectionStore` -- a ``public``-schema service-role client.
* :class:`FakeOrgSelectionStore` -- in-memory, same contract (tests).
* :func:`make_org_selection_store` -- Real normally, Fake under pytest (like
  ``make_license_checker``) unless ``force_real``.

Errors carry the RPC's code: :class:`OrgSelectionError` ``.code`` is one of
``not_platform_staff`` | ``target_not_licensed`` | ``product_not_ready``.

KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

logger = logging.getLogger(__name__)

ENDED_BY_VALUES = ("replaced", "exit", "logout", "new_session", "revoked")
ERROR_CODES = ("not_platform_staff", "target_not_licensed", "product_not_ready")
_RPC_PREFIX = "platform_org_selection:"
_IN_BATCH = 100
#: Seconds the ``org_picker_ready`` flag of a product is reused in-process.
READY_TTL_S = 30.0


class OrgSelectionError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LiveSelection:
    id: str
    target_org_id: str
    home_org_id: Optional[str]
    auth_session_id: str


class OrgSelectionStore(Protocol):
    def product_ready(self, product_slug: str) -> bool: ...

    def requires_mfa(self, product_slug: str) -> bool: ...

    def live(self, user_id: Any, product_slug: str) -> Optional[LiveSelection]: ...

    def set(
        self, user_id: Any, product_slug: str, target_org_id: Any, auth_session_id: Any
    ) -> str: ...

    def end(self, user_id: Any, product_slug: Optional[str], reason: str) -> int: ...

    def licensed_orgs(self, product_slug: str) -> list[dict]: ...


def _batched(values: list, size: int = _IN_BATCH):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _code_from(exc: Exception) -> Optional[str]:
    text = str(exc)
    if _RPC_PREFIX not in text:
        return None
    tail = text.split(_RPC_PREFIX, 1)[1]
    for code in ERROR_CODES:
        if tail.startswith(code):
            return code
    return None


class RealOrgSelectionStore:
    def __init__(self, get_core_client: Callable[[], Any]) -> None:
        self._core = get_core_client
        self._ready: dict[str, tuple[float, bool, bool]] = {}
        self._ids: dict[str, str] = {}
        self._lock = threading.Lock()

    def _product(self, slug: str) -> Optional[dict]:
        rows = (
            self._core().table("products")
            .select("id, org_picker_ready, org_picker_requires_mfa, db_schema")
            .eq("slug", slug).limit(1).execute().data or []
        )
        return rows[0] if rows else None

    def _flags(self, product_slug: str) -> tuple[bool, bool]:
        """``(ready, requires_mfa)`` of the product row, reused for ``READY_TTL_S``."""
        now = time.monotonic()
        with self._lock:
            hit = self._ready.get(product_slug)
            if hit and hit[0] > now:
                return hit[1], hit[2]
        row = self._product(product_slug)
        ready = bool(row and row.get("org_picker_ready") and row.get("db_schema"))
        # Fail closed: a row without the column (pre core 073) or NULL still requires aal2.
        requires_mfa = not (row and row.get("org_picker_requires_mfa") is False)
        with self._lock:
            self._ready[product_slug] = (now + READY_TTL_S, ready, requires_mfa)
            if row:
                self._ids[product_slug] = row["id"]
        return ready, requires_mfa

    def product_ready(self, product_slug: str) -> bool:
        return self._flags(product_slug)[0]

    def requires_mfa(self, product_slug: str) -> bool:
        """Whether acting in this product needs an aal2 session (``products.org_picker_requires_mfa``)."""
        return self._flags(product_slug)[1]

    def _product_id(self, slug: str) -> Optional[str]:
        with self._lock:
            pid = self._ids.get(slug)
        if pid:
            return pid
        row = self._product(slug)
        if row:
            with self._lock:
                self._ids[slug] = row["id"]
            return row["id"]
        return None

    def live(self, user_id: Any, product_slug: str) -> Optional[LiveSelection]:
        pid = self._product_id(product_slug)
        if not pid:
            return None
        rows = (
            self._core().table("platform_org_selections")
            .select("id, target_org_id, home_org_id, auth_session_id")
            .eq("user_id", str(user_id)).eq("product_id", pid)
            .is_("ended_at", "null").limit(1).execute().data or []
        )
        if not rows:
            return None
        r = rows[0]
        return LiveSelection(
            id=str(r["id"]), target_org_id=str(r["target_org_id"]),
            home_org_id=str(r["home_org_id"]) if r.get("home_org_id") else None,
            auth_session_id=str(r["auth_session_id"]),
        )

    def set(self, user_id: Any, product_slug: str, target_org_id: Any, auth_session_id: Any) -> str:
        try:
            res = self._core().rpc("platform_org_selection_set", {
                "p_user_id": str(user_id), "p_product_slug": product_slug,
                "p_target_org_id": str(target_org_id), "p_auth_session_id": str(auth_session_id),
            }).execute()
        except Exception as exc:
            code = _code_from(exc)
            if code:
                raise OrgSelectionError(code) from exc
            logger.error("org_selection_set_error user=%s product=%s", user_id, product_slug, exc_info=True)
            raise
        data = res.data
        return str(data[0] if isinstance(data, list) and data else data)

    def end(self, user_id: Any, product_slug: Optional[str], reason: str) -> int:
        params: dict[str, Any] = {"p_user_id": str(user_id), "p_reason": reason}
        if product_slug:
            params["p_product_slug"] = product_slug
        res = self._core().rpc("platform_org_selection_end", params).execute()
        data = res.data
        if isinstance(data, list):
            data = data[0] if data else 0
        return int(data or 0)

    def licensed_orgs(self, product_slug: str) -> list[dict]:
        from noctusai_lib.domain.licensing import license_rows_valid

        pid = self._product_id(product_slug)
        if not pid:
            return []
        core = self._core()

        def page(start: int, end: int):
            return (
                core.table("licenses").select("id, org_id, fim")
                .eq("product_id", pid).eq("status", "active")
                .order("id").range(start, end).execute().data
            )

        org_ids = sorted({
            str(lic["org_id"]) for lic in iter_paged_rows(page, label="licenses")
            if license_rows_valid([lic])
        })
        out: list[dict] = []
        for chunk in _batched(org_ids):
            for o in core.table("organizations").select("id, nome").in_("id", chunk).execute().data or []:
                out.append({"id": str(o["id"]), "nome": o.get("nome")})
        return out


@dataclass
class FakeOrgSelectionStore:
    """In-memory store. ``ready`` slugs may be picked; ``staff`` user ids may pick;
    ``licensed`` is ``{(org_id, slug)}``; ``orgs`` names them. Mirrors the RPC errors."""

    ready: set[str] = field(default_factory=set)
    staff: set[str] = field(default_factory=set)
    licensed: set[tuple[str, str]] = field(default_factory=set)
    orgs: dict[str, str] = field(default_factory=dict)
    home_orgs: dict[str, str] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    unavailable: bool = False
    #: Slugs whose picker does NOT require aal2 (``org_picker_requires_mfa = false``).
    mfa_optional: set[str] = field(default_factory=set)

    def product_ready(self, product_slug: str) -> bool:
        return product_slug in self.ready

    def requires_mfa(self, product_slug: str) -> bool:
        return product_slug not in self.mfa_optional

    def live(self, user_id: Any, product_slug: str) -> Optional[LiveSelection]:
        if self.unavailable:
            raise RuntimeError("fake selection store outage")
        for r in self.rows:
            if r["user_id"] == str(user_id) and r["slug"] == product_slug and r["ended_by"] is None:
                return LiveSelection(r["id"], r["target"], r["home"], r["session"])
        return None

    def set(self, user_id: Any, product_slug: str, target_org_id: Any, auth_session_id: Any) -> str:
        uid = str(user_id)
        if uid not in self.staff:
            raise OrgSelectionError("not_platform_staff")
        if product_slug not in self.ready:
            raise OrgSelectionError("product_not_ready")
        if (str(target_org_id), product_slug) not in self.licensed:
            raise OrgSelectionError("target_not_licensed")
        for r in self.rows:
            if r["user_id"] == uid and r["slug"] == product_slug and r["ended_by"] is None:
                r["ended_by"] = "new_session" if r["session"] != str(auth_session_id) else "replaced"
        sid = str(uuid.uuid4())
        self.rows.append({
            "id": sid, "user_id": uid, "slug": product_slug, "target": str(target_org_id),
            "home": self.home_orgs.get(uid), "session": str(auth_session_id), "ended_by": None,
        })
        return sid

    def end(self, user_id: Any, product_slug: Optional[str], reason: str) -> int:
        if reason not in ENDED_BY_VALUES:
            raise ValueError(reason)
        n = 0
        for r in self.rows:
            if r["user_id"] == str(user_id) and r["ended_by"] is None and product_slug in (None, r["slug"]):
                r["ended_by"] = reason
                n += 1
        return n

    def licensed_orgs(self, product_slug: str) -> list[dict]:
        return [
            {"id": org, "nome": self.orgs.get(org)}
            for (org, slug) in sorted(self.licensed) if slug == product_slug
        ]


def make_org_selection_store(
    get_core_client: Optional[Callable[[], Any]] = None, *, force_real: bool = False
) -> OrgSelectionStore:
    """Real store normally; empty Fake (nobody ready, nobody staff) under pytest unless
    ``force_real`` or no ``get_core_client``."""
    if not force_real and "pytest" in sys.modules:
        return FakeOrgSelectionStore()
    if get_core_client is None:
        return FakeOrgSelectionStore()
    return RealOrgSelectionStore(get_core_client)


__all__ = [
    "ENDED_BY_VALUES", "ERROR_CODES", "FakeOrgSelectionStore", "LiveSelection",
    "OrgSelectionError", "OrgSelectionStore", "RealOrgSelectionStore",
    "make_org_selection_store",
]
