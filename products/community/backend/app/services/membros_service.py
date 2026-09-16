"""Membros service — contract §Membros.

`busca` (nome/email, case-insensitive, partial) and ordering are applied
in Python after a scoped fetch — same rationale as `planos_service`: the
in-repo `MockSupabaseClient` evaluates `.or_()` as match-all and
`.order()` as a no-op, so relying on the client for either would make
this service's behavior untestable. `status`, `plano_id` and `tag` DO
have real predicate evaluators (`in_` / `eq` / `contains`) and are
applied server-side.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.schemas.membros import MEMBRO_STATUSES

_TABLE = "membros"
_PLANOS_TABLE = "planos"


class MembrosServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class MembrosService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── reads ────────────────────────────────────────────────────────

    async def list(
        self,
        *,
        status: str | None = None,
        plano_id: str | None = None,
        tag: str | None = None,
        busca: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        rows = self._fetch_filtered(plano_id=plano_id, tag=tag, busca=busca)
        resumo = self._compute_resumo(rows)
        if status:
            wanted = {s.strip() for s in status.split(",") if s.strip()}
            rows = [r for r in rows if r.get("status") in wanted]
        rows.sort(key=lambda r: (r.get("nome") or "").lower())
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        plano_nomes = self._plano_nomes([r.get("plano_id") for r in page_rows])
        items = [self._to_out(r, plano_nomes) for r in page_rows]
        return {"items": items, "total": total, "resumo": resumo}

    def _fetch_filtered(self, *, plano_id: str | None, tag: str | None, busca: str | None) -> list[dict]:
        query = self._client.table(_TABLE).select("*").eq("org_id", self._org_id)
        if plano_id:
            query = query.eq("plano_id", str(plano_id))
        if tag:
            query = query.contains("tags", [tag])
        rows = query.execute().data or []
        if busca:
            needle = busca.lower()
            rows = [
                r for r in rows
                if needle in (r.get("nome") or "").lower()
                or needle in (r.get("email") or "").lower()
            ]
        return rows

    @staticmethod
    def _compute_resumo(rows: list[dict]) -> dict[str, int]:
        resumo = {s: 0 for s in MEMBRO_STATUSES}
        for row in rows:
            st = row.get("status")
            if st in resumo:
                resumo[st] += 1
        return resumo

    def _plano_nomes(self, plano_ids: list) -> dict[str, str]:
        ids = sorted({str(i) for i in plano_ids if i})
        if not ids:
            return {}
        rows = (
            self._client.table(_PLANOS_TABLE)
            .select("id,nome")
            .eq("org_id", self._org_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        return {str(r["id"]): r["nome"] for r in rows}

    @staticmethod
    def _to_out(row: dict, plano_nomes: dict[str, str]) -> dict:
        plano_id = row.get("plano_id")
        plano_nome = plano_nomes.get(str(plano_id)) if plano_id else None
        return {**row, "plano_nome": plano_nome}

    async def get(self, *, membro_id: str) -> dict | None:
        result = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .maybe_single()
            .execute()
        )
        row = result.data
        if not row:
            return None
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, plano_nomes)

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, *, payload: dict) -> dict:
        email = payload["email"]
        existing = (
            self._client.table(_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("email", email)
            .execute()
            .data
        )
        if existing:
            raise MembrosServiceError(
                "Já existe um membro com esse e-mail.", status_code=409,
            )
        row = {
            **payload,
            "org_id": self._org_id,
            "entrou_em": datetime.now(timezone.utc).isoformat(),
        }
        if row.get("plano_id") is not None:
            row["plano_id"] = str(row["plano_id"])
        result = self._client.table(_TABLE).insert(row).execute()
        if not result.data:
            raise MembrosServiceError("Falha ao criar membro.")
        created = result.data[0]
        plano_nomes = self._plano_nomes([created.get("plano_id")])
        return self._to_out(created, plano_nomes)

    async def update(self, *, membro_id: str, payload: dict) -> dict | None:
        if "email" in payload:
            existing = (
                self._client.table(_TABLE)
                .select("id")
                .eq("org_id", self._org_id)
                .eq("email", payload["email"])
                .execute()
                .data
                or []
            )
            if any(str(r["id"]) != str(membro_id) for r in existing):
                raise MembrosServiceError(
                    "Já existe um membro com esse e-mail.", status_code=409,
                )
        if payload.get("plano_id") is not None:
            payload = {**payload, "plano_id": str(payload["plano_id"])}
        result = (
            self._client.table(_TABLE)
            .update(payload)
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, plano_nomes)

    async def set_status(self, *, membro_id: str, novo_status: str, motivo: str | None = None) -> dict | None:
        """Set status — an event, module 2 hangs payment-driven transitions
        off this same function. Idempotent: same status → 200, unchanged.

        `motivo` is accepted (contract shape) but module 1 has no
        status-history table to persist it into yet — a later module
        owns audit trail.
        # NOC-REMEDIATE[status-history]: persist `motivo` once a status-change
        # audit trail exists (module 2+). — 2026-09-16
        """
        current = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .maybe_single()
            .execute()
        ).data
        if not current:
            return None
        if current.get("status") == novo_status:
            plano_nomes = self._plano_nomes([current.get("plano_id")])
            return self._to_out(current, plano_nomes)
        if novo_status == "ativo" and not current.get("plano_id"):
            raise MembrosServiceError(
                "Defina um plano antes de ativar o membro.", status_code=409,
            )
        result = (
            self._client.table(_TABLE)
            .update({"status": novo_status})
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, plano_nomes)

    async def soft_delete(self, *, membro_id: str) -> bool:
        """Sets `status='cancelado'`. NEVER hard-deletes (LGPD erasure is
        a separate, later flow)."""
        result = (
            self._client.table(_TABLE)
            .update({"status": "cancelado"})
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .execute()
        )
        return bool(result.data)
