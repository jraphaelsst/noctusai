"""Supabase (Real) implementations of the store Protocols.

Table names are BARE (`"pedidos"`): the admin client is already pinned to the
`store` schema — a qualified name would resolve as `store.store.pedidos`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.stores.protocols import VersionConflict

logger = logging.getLogger(__name__)

_MAX_CAS_ATTEMPTS = 5


def _is_unique_violation(exc: Exception) -> bool:
    return getattr(exc, "code", None) == "23505"


def _first(result: Any) -> Optional[dict[str, Any]]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data or None


class SupabaseSettingsStore:
    def __init__(self, client_fn: Callable[[], Any]) -> None:
        self._client_fn = client_fn

    def current(self) -> Optional[dict[str, Any]]:
        result = (
            self._client_fn()
            .table("landing_settings")
            .select("version, data, created_by, created_at")
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        return _first(result)

    def append(self, *, version: int, data: dict[str, Any], created_by: Optional[str]) -> dict[str, Any]:
        try:
            result = (
                self._client_fn()
                .table("landing_settings")
                .insert({"version": version, "data": data, "created_by": created_by})
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 - narrowed immediately
            if _is_unique_violation(exc):
                raise VersionConflict(f"version {version} already exists") from exc
            raise
        row = _first(result)
        if row is None:
            raise RuntimeError("landing_settings insert returned no row")
        return row


class SupabasePedidoStore:
    def __init__(self, client_fn: Callable[[], Any]) -> None:
        self._client_fn = client_fn

    def _t(self) -> Any:
        return self._client_fn().table("pedidos")

    def create(self, row: dict[str, Any]) -> dict[str, Any]:
        created = _first(self._t().insert(row).execute())
        if created is None:
            raise RuntimeError("pedidos insert returned no row")
        return created

    def _by(self, column: str, value: str) -> Optional[dict[str, Any]]:
        return _first(self._t().select("*").eq(column, value).limit(1).execute())

    def get_by_token(self, token: str) -> Optional[dict[str, Any]]:
        return self._by("token", token)

    def get_by_id(self, pedido_id: str) -> Optional[dict[str, Any]]:
        return self._by("id", pedido_id)

    def get_by_charge_id(self, charge_id: str) -> Optional[dict[str, Any]]:
        return self._by("gateway_charge_id", charge_id)

    def update(self, pedido_id: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
        return _first(self._t().update(fields).eq("id", pedido_id).execute())

    def list(self, *, status: Optional[str], limit: int, offset: int) -> list[dict[str, Any]]:
        query = self._t().select("*")
        if status:
            query = query.eq("status", status)
        result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return list(result.data or [])

    def claim_email(self, pedido_id: str, *, at_iso: str) -> bool:
        # `is_("email_enviado_em", "null")` makes the UPDATE conditional in the
        # DB: exactly one concurrent caller sees a returned row.
        result = (
            self._t()
            .update({"email_enviado_em": at_iso, "email_erro": None})
            .eq("id", pedido_id)
            .is_("email_enviado_em", "null")
            .execute()
        )
        return bool(result.data)

    def release_email(self, pedido_id: str, *, error: Optional[str]) -> None:
        self._t().update({"email_enviado_em": None, "email_erro": error}).eq("id", pedido_id).execute()

    def take_download(self, token: str, *, max_downloads: int) -> bool:
        # PostgREST cannot express `downloads = downloads + 1`; compare-and-set
        # on the value we read instead, retrying a lost race a few times.
        for _ in range(_MAX_CAS_ATTEMPTS):
            row = self.get_by_token(token)
            if row is None:
                return False
            current = int(row.get("downloads") or 0)
            if current >= max_downloads:
                return False
            result = (
                self._t()
                .update({"downloads": current + 1})
                .eq("token", token)
                .eq("downloads", current)
                .execute()
            )
            if result.data:
                return True
        logger.warning("take_download: lost the CAS race %d times for a pedido", _MAX_CAS_ATTEMPTS)
        return False
