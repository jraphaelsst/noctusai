"""Planos públicos service — contract amendment A17 (PUBLIC tier listing).

Read-only projection of `planos` joined with `plano_gateway_refs`,
deliberately NARROWER than module 1's authenticated `Plano` shape. Uses
the service-role client (bypasses RLS) — same convention as every other
public route in this product; no anon policy or anon grant is added to
either table (that is precisely the migration 006→007 mistake this
amendment's own text calls out).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

_PLANOS_TABLE = "planos"
_GATEWAY_REFS_TABLE = "plano_gateway_refs"

_BENEFICIO_KEYS = ("feed", "forum", "chat", "eventos")


class PlanosPublicosService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    async def list(self) -> dict:
        rows = (
            self._client.table(_PLANOS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("ativo", True)
            .execute()
            .data
            or []
        )
        # Sort in Python — same rationale `planos_service.py` documents:
        # the in-repo MockSupabaseClient treats `.order()` as a no-op.
        rows.sort(key=lambda r: (r.get("ordem") or 0, r.get("nome") or ""))
        plano_ids = [str(r["id"]) for r in rows]
        metodos_by_plano = self._metodos_disponiveis_by_plano(plano_ids)
        items = [
            self._to_out(row, metodos_by_plano.get(str(row["id"]), []))
            for row in rows
        ]
        return {"items": items, "total": len(items)}

    def _metodos_disponiveis_by_plano(self, plano_ids: list[str]) -> dict[str, list[str]]:
        if not plano_ids:
            return {}
        rows = (
            self._client.table(_GATEWAY_REFS_TABLE)
            .select("plano_id,gateway")
            .eq("org_id", self._org_id)
            .in_("plano_id", plano_ids)
            .execute()
            .data
            or []
        )
        out: dict[str, list[str]] = {}
        for row in rows:
            plano_id = str(row.get("plano_id"))
            if plano_id not in plano_ids:
                # Defensive against the mock's `.in_()` degrading to
                # match-all in some paths — see `planos_service.py`'s
                # own `_membros_ativos_counts` comment for the same guard.
                continue
            gateway = row.get("gateway")
            metodos = out.setdefault(plano_id, [])
            if gateway == "stripe" and "cartao" not in metodos:
                metodos.append("cartao")
            elif gateway == "asaas":
                for metodo in ("pix", "boleto"):
                    if metodo not in metodos:
                        metodos.append(metodo)
        return out

    @staticmethod
    def _to_out(row: dict, metodos_disponiveis: list[str]) -> dict:
        entitlements = row.get("entitlements") or {}
        beneficios = {key: bool(entitlements.get(key, False)) for key in _BENEFICIO_KEYS}
        return {
            "id": row["id"],
            "nome": row["nome"],
            "descricao": row.get("descricao"),
            "preco_centavos": row["preco_centavos"],
            "ciclo": row["ciclo"],
            "beneficios": beneficios,
            "metodos_disponiveis": metodos_disponiveis,
        }
