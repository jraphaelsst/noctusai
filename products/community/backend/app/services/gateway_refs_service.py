"""Gateway refs service — contract §Gateway refs (admin).

Extends `planos` with a per-gateway external reference (Stripe Price id,
or the value a manager keeps for their Asaas configuration) WITHOUT
touching `planos.py` / `planos_service.py` — a separate table
(`plano_gateway_refs`, migration 008), a separate service.

Upsert is implemented as select-then-insert-or-update rather than a
`.upsert()` call: the in-repo `MockSupabaseClient.upsert()` documents
upsert propagation as a follow-up (it returns the CURRENT data, not the
mutated row — see `noctusai_lib/testing/mocks.py`), so relying on it
would make this service's behavior untestable and silently different
from real Postgrest. Same rationale the sibling module-1 services give
for sorting/pagination in Python.
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
        existing = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("plano_id", plano_id)
            .eq("gateway", gateway)
            .maybe_single()
            .execute()
        ).data
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            result = (
                self._client.table(_TABLE)
                .update({"ref_externo": ref_externo})
                .eq("org_id", self._org_id)
                .eq("id", str(existing["id"]))
                .execute()
            )
            if result.data:
                return result.data[0]
            return {**existing, "ref_externo": ref_externo, "updated_at": now}
        row = {
            "id": str(uuid4()),
            "org_id": self._org_id,
            "plano_id": plano_id,
            "gateway": gateway,
            "ref_externo": ref_externo,
            "created_at": now,
            "updated_at": now,
        }
        result = self._client.table(_TABLE).insert(row).execute()
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
