"""Internal notes on an imóvel (migration 315) — OWNED data, full CRUD.

The imóvel page is a mirror of Vista PLUS what we add (`KB § PATTERNS/
frontend/mirror-owned-overlay.md`). A note is ours by definition: Vista has no
such field, and the sync (`ImovelSyncService`) never reads or writes this
table. Keyed to `imovel_registry` (not the `imoveis` mirror — migration 076),
so a sold imóvel that left the Vista catalog keeps its notes.

Every write is org-scoped and stamps the actor (`created_by` / `updated_by`):
that is this module's audit trail, same posture as the other authored tables
(`confirmado_por`). Deleting what does not exist is a 404, never a silent 200.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.imovel_hub import dados_service
from app.services import table_reads
from app.services.documento_store import now_iso

TABLE = "imovel_notas"
MAX_LEN = 4000


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _texto(valor: Optional[str]) -> str:
    texto = (valor or "").strip()
    if not texto:
        raise ValidationError_("Escreva a nota.", field="texto")
    if len(texto) > MAX_LEN:
        raise ValidationError_(f"A nota tem no máximo {MAX_LEN} caracteres.", field="texto")
    return texto


def _saida(row: dict, atores: dict) -> dict:
    def ator(k: str):
        v = row.get(k)
        return atores.get(str(v)) if v else None

    return {
        "id": str(row["id"]),
        "codigo": row["codigo"],
        "texto": row["texto"],
        "created_at": row.get("created_at"),
        "created_by": ator("created_by"),
        "updated_at": row.get("updated_at"),
        "updated_by": ator("updated_by"),
    }


def _saidas(rows: list[dict]) -> list[dict]:
    ids = {r.get(k) for r in rows for k in ("created_by", "updated_by")}
    atores = table_reads.resolve_actors(ids)
    return [_saida(r, atores) for r in rows]


def listar(client: Any, org_id: UUID, codigo: str) -> dict:
    """`{items, total}`, newest first. Unknown imóvel → 404."""
    dados_service.ensure_imovel(client, org_id, codigo)
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    items = _saidas(rows)
    return {"items": items, "total": len(items)}


def criar(client: Any, org_id: UUID, codigo: str, *, texto: str, usuario_id: Optional[UUID]) -> dict:
    dados_service.ensure_imovel(client, org_id, codigo)
    agora = now_iso()
    ator = str(usuario_id) if usuario_id else None
    rows = (
        _t(client, TABLE)
        .insert(
            {
                "org_id": str(org_id),
                "codigo": codigo,
                "texto": _texto(texto),
                "created_by": ator,
                "created_at": agora,
                "updated_by": ator,
                "updated_at": agora,
            }
        )
        .execute()
    ).data or []
    return _saidas(rows)[0]


def _existente(client: Any, org_id: UUID, codigo: str, nota_id: UUID) -> dict:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("id", str(nota_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(TABLE, str(nota_id))
    return rows[0]


def atualizar(
    client: Any, org_id: UUID, codigo: str, nota_id: UUID, *, texto: str, usuario_id: Optional[UUID]
) -> dict:
    dados_service.ensure_imovel(client, org_id, codigo)
    _existente(client, org_id, codigo, nota_id)
    patch = {
        "texto": _texto(texto),
        "updated_by": str(usuario_id) if usuario_id else None,
        "updated_at": now_iso(),
    }
    rows = (
        _t(client, TABLE)
        .update(patch)
        .eq("org_id", str(org_id))
        .eq("id", str(nota_id))
        .execute()
    ).data or []
    return _saidas(rows or [{**_existente(client, org_id, codigo, nota_id)}])[0]


def remover(client: Any, org_id: UUID, codigo: str, nota_id: UUID) -> dict:
    dados_service.ensure_imovel(client, org_id, codigo)
    _existente(client, org_id, codigo, nota_id)
    _t(client, TABLE).delete().eq("org_id", str(org_id)).eq("id", str(nota_id)).execute()
    return {"id": str(nota_id), "removida": True}
