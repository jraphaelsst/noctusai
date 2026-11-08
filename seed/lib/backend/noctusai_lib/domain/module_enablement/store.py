"""Per-org module enablement: store (Protocol + Fake + Real + factory) and the resolver.

Rule (owner 2026-11-08): modules are switched PER ORG, **ALL ON by default**. The table
(`public.org_modules`) stores explicit rows only; a missing row means ENABLED, so a new module or a new org
needs no backfill. `ModuleEnablement.enabled_modules(org_id)` = known keys minus the explicitly disabled ones.

Failure posture: a store error raises :class:`ModuleEnablementUnavailable` (callers answer 503) -- never "all on".
Reads are cached in-process for a short TTL; a write through this resolver invalidates its own cache (another
process sees it within the TTL).
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

logger = logging.getLogger(__name__)

__all__ = [
    "MODULE_DISABLED_CODE",
    "ORG_MODULES_TABLE",
    "FakeModuleEnablementStore",
    "ModuleEnablement",
    "ModuleEnablementStore",
    "ModuleEnablementUnavailable",
    "SupabaseModuleEnablementStore",
    "make_module_enablement",
    "make_module_enablement_store",
]

#: The stable machine code of the 403 a disabled module answers (FE keys off it).
MODULE_DISABLED_CODE = "module_disabled"
ORG_MODULES_TABLE = "org_modules"

#: Seconds an org's resolved set is cached in-process.
CACHE_TTL_S = 15.0


class ModuleEnablementUnavailable(RuntimeError):
    """The enablement lookup/write could not be completed (DB / transport error)."""


class ModuleEnablementStore(Protocol):
    def explicit(self, org_id: Any) -> dict[str, bool]:
        """`{module_key: enabled}` for the rows that exist for the org (absent key = default ON)."""

    def set_enabled(self, org_id: Any, module_key: str, enabled: bool, *, updated_by: Optional[Any] = None) -> None: ...


@dataclass
class FakeModuleEnablementStore:
    """In-memory store. `unavailable=True` simulates an outage."""

    rows: dict[tuple[str, str], bool] = field(default_factory=dict)
    unavailable: bool = False
    writes: list[tuple[str, str, bool, Optional[str]]] = field(default_factory=list)

    def explicit(self, org_id: Any) -> dict[str, bool]:
        if self.unavailable:
            raise ModuleEnablementUnavailable("fake outage")
        return {k: v for (o, k), v in self.rows.items() if o == str(org_id)}

    def set_enabled(self, org_id: Any, module_key: str, enabled: bool, *, updated_by: Optional[Any] = None) -> None:
        if self.unavailable:
            raise ModuleEnablementUnavailable("fake outage")
        self.rows[(str(org_id), module_key)] = bool(enabled)
        self.writes.append((str(org_id), module_key, bool(enabled), None if updated_by is None else str(updated_by)))


class SupabaseModuleEnablementStore:
    """Reads/writes `public.org_modules` through the `public`-schema service-role client (`get_core_client()`)."""

    def __init__(self, get_core_client: Callable[[], Any]) -> None:
        self._get_core_client = get_core_client

    def explicit(self, org_id: Any) -> dict[str, bool]:
        try:
            result = (
                self._get_core_client()
                .table(ORG_MODULES_TABLE)
                .select("module_key, enabled")
                .eq("org_id", str(org_id))
                .execute()
            )
        except Exception as exc:
            logger.error("module_enablement_lookup_error org=%s", org_id, exc_info=True)
            raise ModuleEnablementUnavailable(str(exc)) from exc
        return {str(r["module_key"]): bool(r["enabled"]) for r in (result.data or [])}

    def set_enabled(self, org_id: Any, module_key: str, enabled: bool, *, updated_by: Optional[Any] = None) -> None:
        row: dict[str, Any] = {"org_id": str(org_id), "module_key": module_key, "enabled": bool(enabled)}
        if updated_by is not None:
            row["updated_by"] = str(updated_by)
        try:
            self._get_core_client().table(ORG_MODULES_TABLE).upsert(row, on_conflict="org_id,module_key").execute()
        except Exception as exc:
            logger.error("module_enablement_write_error org=%s module=%s", org_id, module_key, exc_info=True)
            raise ModuleEnablementUnavailable(str(exc)) from exc


def make_module_enablement_store(
    get_core_client: Optional[Callable[[], Any]] = None, *, force_real: bool = False
) -> ModuleEnablementStore:
    """Real store normally; an (all-ON) Fake under pytest unless `force_real` -- same precedent as
    `make_license_checker`: a product's `app.main` is built at import time, before any per-test seam exists."""
    if not force_real and "pytest" in sys.modules:
        return FakeModuleEnablementStore()
    if get_core_client is None:
        return FakeModuleEnablementStore()
    return SupabaseModuleEnablementStore(get_core_client)


class ModuleEnablement:
    """The resolver. `known` = every module key this process can answer for (default-ON universe)."""

    def __init__(self, store: ModuleEnablementStore, known: Iterable[str], *, ttl_s: float = CACHE_TTL_S) -> None:
        self._store = store
        self._known = frozenset(known)
        self._ttl_s = ttl_s
        self._cache: dict[str, tuple[float, frozenset[str]]] = {}
        self._lock = threading.Lock()

    @property
    def known(self) -> frozenset[str]:
        return self._known

    def enabled_modules(self, org_id: Any) -> frozenset[str]:
        """Keys enabled for `org_id`: every known key unless an explicit `enabled=false` row exists."""
        key = str(org_id)
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and hit[0] > now:
                return hit[1]
        explicit = self._store.explicit(org_id)  # raises ModuleEnablementUnavailable: never "all on" on error
        enabled = frozenset(k for k in self._known if explicit.get(k, True))
        with self._lock:
            self._cache[key] = (now + self._ttl_s, enabled)
        return enabled

    def is_enabled(self, org_id: Any, module_key: str) -> bool:
        return module_key in self.enabled_modules(org_id)

    def set_enabled(self, org_id: Any, module_key: str, enabled: bool, *, updated_by: Optional[Any] = None) -> None:
        if module_key not in self._known:
            raise ValueError(f"unknown module key {module_key!r}")
        self._store.set_enabled(org_id, module_key, enabled, updated_by=updated_by)
        self.invalidate(org_id)

    def invalidate(self, org_id: Optional[Any] = None) -> None:
        with self._lock:
            if org_id is None:
                self._cache.clear()
            else:
                self._cache.pop(str(org_id), None)


def make_module_enablement(
    known: Iterable[str],
    get_core_client: Optional[Callable[[], Any]] = None,
    *,
    force_real: bool = False,
    store: Optional[ModuleEnablementStore] = None,
) -> ModuleEnablement:
    return ModuleEnablement(store or make_module_enablement_store(get_core_client, force_real=force_real), known)
