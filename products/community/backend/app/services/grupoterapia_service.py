"""Grupoterapia (group therapy sessions) service — contract §Grupoterapia,
staff side (slice BE-D).

Staff CRUD over `community.grupoterapia_sessoes` / `_reservas`, both RLS
gated to `community.eh_equipe()` (migration 013 §5) — this module always
receives the CALLER'S own user-scoped client, never the service-role one.
The member-portal side (tier gate first, service-role reads, the
`reservar_vaga_fala` RPC) lives in `portal_grupoterapia_service.py` — see
that module's docstring for the security rationale.

Sort/aggregate-in-Python for the same reason `planos_service.py` does:
the in-repo `MockSupabaseClient` has no real SQL planner behind `.order()`,
and this product's scale (one community's sessions/reservations) makes the
Python pass the correct trade-off.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.services.eventos_service import registrar_evento

_SESSOES_TABLE = "grupoterapia_sessoes"
_RESERVAS_TABLE = "grupoterapia_reservas"
_MEMBROS_TABLE = "membros"

_STATUS_CONFIRMADA = "confirmada"
_STATUS_CANCELADA = "cancelada"


class GrupoterapiaServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class GrupoterapiaService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── reads ────────────────────────────────────────────────────────

    async def list(
        self,
        *,
        de: str | None = None,
        ate: str | None = None,
        status: str | None = None,
    ) -> dict:
        query = self._client.table(_SESSOES_TABLE).select("*").eq("org_id", self._org_id)
        if de:
            query = query.gte("inicio", de)
        if ate:
            query = query.lte("inicio", ate)
        if status:
            query = query.eq("status", status)
        rows = query.execute().data or []
        rows.sort(key=lambda r: r.get("inicio") or "")
        counts = self._reservas_confirmadas_counts([r["id"] for r in rows])
        items = [self._to_out(r, counts.get(str(r["id"]), 0)) for r in rows]
        return {"items": items, "total": len(items)}

    async def get(self, *, sessao_id: str) -> dict | None:
        result = (
            self._client.table(_SESSOES_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(sessao_id))
            .maybe_single()
            .execute()
        )
        row = result.data
        if not row:
            return None
        counts = self._reservas_confirmadas_counts([row["id"]])
        return self._to_out(row, counts.get(str(row["id"]), 0))

    async def get_reservas(self, *, sessao_id: str) -> dict:
        rows = (
            self._client.table(_RESERVAS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("sessao_id", str(sessao_id))
            .execute()
            .data
            or []
        )
        rows.sort(key=lambda r: r.get("created_at") or "")
        membro_nomes = self._membro_nomes([r.get("membro_id") for r in rows])
        items = [
            {**r, "membro_nome": membro_nomes.get(str(r.get("membro_id")))}
            for r in rows
        ]
        return {"items": items, "total": len(items)}

    def _reservas_confirmadas_counts(self, sessao_ids: list) -> dict[str, int]:
        ids = [str(i) for i in sessao_ids if i]
        if not ids:
            return {}
        rows = (
            self._client.table(_RESERVAS_TABLE)
            .select("sessao_id")
            .eq("org_id", self._org_id)
            .eq("status", _STATUS_CONFIRMADA)
            .in_("sessao_id", ids)
            .execute()
            .data
            or []
        )
        counts: dict[str, int] = {}
        for row in rows:
            sid = row.get("sessao_id")
            if sid is None:
                continue
            sid = str(sid)
            if sid not in ids:
                # Mirrors `planos_service._membros_ativos_counts`'s defensive
                # guard — the mock's `.in_()` predicate degrades to
                # match-all along some code paths.
                continue
            counts[sid] = counts.get(sid, 0) + 1
        return counts

    def _membro_nomes(self, membro_ids: list) -> dict[str, str]:
        ids = [str(i) for i in membro_ids if i]
        if not ids:
            return {}
        rows = (
            self._client.table(_MEMBROS_TABLE)
            .select("id, nome")
            .eq("org_id", self._org_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        return {str(r["id"]): r.get("nome") for r in rows}

    @staticmethod
    def _to_out(row: dict, reservas: int) -> dict:
        return {**row, "reservas": reservas}

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, *, payload: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()), **payload, "org_id": self._org_id,
            "status": "agendada",
            "created_at": now, "updated_at": now,
        }
        result = self._client.table(_SESSOES_TABLE).insert(row).execute()
        if not result.data:
            raise GrupoterapiaServiceError("Falha ao criar sessão.")
        return self._to_out(result.data[0], 0)

    async def update(
        self, *, sessao_id: str, payload: dict, autor_id: UUID | None,
    ) -> dict | None:
        """Partial update. Contract: "Cancelling a session writes an evento
        `grupoterapia` for each confirmed reservation" — fired here when
        `status` transitions INTO `cancelada` (not on a no-op re-PATCH of an
        already-cancelled session, so a repeated cancel never double-writes
        the timeline).
        """
        cancelling = False
        titulo = None
        if payload.get("status") == _STATUS_CANCELADA:
            current = (
                self._client.table(_SESSOES_TABLE)
                .select("status, titulo")
                .eq("org_id", self._org_id)
                .eq("id", str(sessao_id))
                .maybe_single()
                .execute()
            ).data
            cancelling = bool(current) and current.get("status") != _STATUS_CANCELADA
            titulo = (current or {}).get("titulo")

        result = (
            self._client.table(_SESSOES_TABLE)
            .update(payload)
            .eq("org_id", self._org_id)
            .eq("id", str(sessao_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]

        if cancelling:
            reservas = (
                self._client.table(_RESERVAS_TABLE)
                .select("membro_id")
                .eq("org_id", self._org_id)
                .eq("sessao_id", str(sessao_id))
                .eq("status", _STATUS_CONFIRMADA)
                .execute()
                .data
                or []
            )
            for reserva in reservas:
                registrar_evento(
                    self._client,
                    org_id=self._org_id,
                    membro_id=reserva["membro_id"],
                    tipo="grupoterapia",
                    descricao=(
                        f"Sessão de grupoterapia cancelada: "
                        f"{row.get('titulo') or titulo or ''}."
                    ),
                    autor_id=autor_id,
                )

        counts = self._reservas_confirmadas_counts([row["id"]])
        return self._to_out(row, counts.get(str(row["id"]), 0))

    async def delete(self, *, sessao_id: str) -> bool:
        """Hard-delete the session. Refuses (409) when ANY reservation row
        exists for it — including an already-cancelled one, since that row
        is itself audit history the `ON DELETE CASCADE` would destroy.
        Contract text is literal: "delete-only-when-no-reservations 409".
        """
        existing = (
            self._client.table(_RESERVAS_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("sessao_id", str(sessao_id))
            .execute()
            .data
            or []
        )
        if existing:
            raise GrupoterapiaServiceError(
                "Sessão com reservas — cancele em vez de excluir.", status_code=409,
            )
        result = (
            self._client.table(_SESSOES_TABLE)
            .delete()
            .eq("org_id", self._org_id)
            .eq("id", str(sessao_id))
            .execute()
        )
        return bool(result.data)
