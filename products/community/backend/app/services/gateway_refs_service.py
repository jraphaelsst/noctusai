"""Gateway refs service — contract §Gateway refs (admin).

Extends `planos` with a per-gateway external reference (Stripe Price id,
or the value a manager keeps for their Asaas configuration) WITHOUT
touching `planos.py` / `planos_service.py` — a separate table
(`plano_gateway_refs`, migration 008), a separate service.

Upsert is a single atomic `.upsert(..., on_conflict="plano_id,gateway")`
against the `plano_gateway_refs_plano_gateway_unique` constraint
(migration 008). It was originally written as select-then-insert-or-update
because `MockSupabaseClient.upsert()` returned the CURRENT rows instead
of the written ones, which made a real upsert untestable; that gap was
fixed in the seed (c7bbf253), so the workaround is gone. The atomic form
is also the CORRECT one: two concurrent PUTs for the same
`(plano_id, gateway)` both saw "no existing row" under the old shape and
the second insert died on the unique constraint (a 500 for that caller).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

_TABLE = "plano_gateway_refs"
_PLANOS_TABLE = "planos"


class GatewayRefsServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class GatewayRefsService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    def _plano_exists(self, plano_id: str) -> bool:
        row = (
            self._client.table(_PLANOS_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("id", plano_id)
            .maybe_single()
            .execute()
        ).data
        return bool(row)

    async def list(self, *, plano_id: str) -> dict:
        if not self._plano_exists(plano_id):
            raise GatewayRefsServiceError("Plano não encontrado.", status_code=404)
        rows = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("plano_id", plano_id)
            .execute()
            .data
            or []
        )
        return {"items": rows, "total": len(rows)}

    async def upsert(self, *, plano_id: str, gateway: str, ref_externo: str) -> dict:
        if not self._plano_exists(plano_id):
            raise GatewayRefsServiceError("Plano não encontrado.", status_code=404)
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()),
            "org_id": self._org_id,
            "plano_id": plano_id,
            "gateway": gateway,
            "ref_externo": ref_externo,
            "created_at": now,
            "updated_at": now,
        }
        result = (
            self._client.table(_TABLE)
            .upsert(row, on_conflict="plano_id,gateway")
            .execute()
        )
        if not result.data:
            raise GatewayRefsServiceError("Falha ao salvar referência de gateway.")
        return result.data[0]

    async def delete(self, *, plano_id: str, gateway: str) -> bool:
        result = (
            self._client.table(_TABLE)
            .delete()
            .eq("org_id", self._org_id)
            .eq("plano_id", plano_id)
            .eq("gateway", gateway)
            .execute()
        )
        return bool(result.data)
