"""Ground-truth closing prices (migration 266) -- list + confirm / reject the
proposed imóvel link.

The importer (`noctus.dev.drive_census action=transacoes`) only PROPOSES a link:
rows land `pendente` with `vinculo_candidatos`. A human admin confirms (chooses a
candidate, or types a code) or rejects. Owner rule: every match is confirmed by
a person; nothing here auto-links.

`confirmar` accepts any code that exists in `imovel_registry` -- a candidate the
importer proposed OR a typed one -- and reports which (`origem_codigo`). The
audit trail is the acting-audit trigger (migration 214) plus `confirmado_por` /
`confirmado_em` (set for a rejection too: it is the decider).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.imovel_hub import busca_service
from app.services import table_reads

TABLE = "imovel_transacoes"
REGISTRY_TABLE = "imovel_registry"
STATUS_VALIDOS = ("pendente", "confirmado", "rejeitado")
_MAX_LIMIT = 200


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def listar(
    client: Any, org_id: UUID, *, vinculo_status: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> dict:
    if vinculo_status is not None and vinculo_status not in STATUS_VALIDOS:
        raise AppException(
            code="vinculo_status_invalido",
            message=f"vinculo_status deve ser um de {', '.join(STATUS_VALIDOS)}.",
            status_code=422,
        )
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))
    q = _t(client, TABLE).select("*", count="exact").eq("org_id", str(org_id))
    if vinculo_status:
        q = q.eq("vinculo_status", vinculo_status)
    res = q.order("data_transacao", desc=True).range(offset, offset + limit - 1).execute()
    rows = res.data or []
    total = getattr(res, "count", None)
    return {"items": rows, "total": total if total is not None else len(rows)}


def _obter(client: Any, org_id: UUID, transacao_id: Any) -> dict:
    rows = (
        _t(client, TABLE).select("*")
        .eq("org_id", str(org_id)).eq("id", str(transacao_id)).limit(1).execute()
    ).data or []
    if not rows:
        raise NotFoundError("Transação", str(transacao_id))
    return rows[0]


def _ja_resolvida(transacao_id: Any, status: str) -> AppException:
    return AppException(
        code="transacao_ja_resolvida",
        message=f"Esta transação já foi resolvida ({status}).",
        status_code=409,
        details={"id": str(transacao_id), "status": status},
    )


def _resolver(client: Any, org_id: UUID, transacao_id: Any, patch: dict) -> dict:
    # `vinculo_status = 'pendente'` in the UPDATE filter closes the read-then-write
    # race: two admins resolving at once cannot both win.
    rows = (
        _t(client, TABLE).update(patch)
        .eq("org_id", str(org_id)).eq("id", str(transacao_id)).eq("vinculo_status", "pendente")
        .execute()
    ).data or []
    if not rows:
        atual = _obter(client, org_id, transacao_id)
        raise _ja_resolvida(transacao_id, atual["vinculo_status"])
    return rows[0]


def confirmar(
    client: Any, org_id: UUID, transacao_id: Any, codigo: str, actor_id: Optional[UUID],
) -> dict:
    """Link the transaction to `codigo` (must exist in `imovel_registry`)."""
    linha = _obter(client, org_id, transacao_id)
    if linha["vinculo_status"] != "pendente":
        raise _ja_resolvida(transacao_id, linha["vinculo_status"])
    canonico = busca_service.canonical(codigo)
    existe = (
        _t(client, REGISTRY_TABLE).select("codigo_canonical")
        .eq("org_id", str(org_id)).eq("codigo_canonical", canonico).limit(1).execute()
    ).data or []
    if not existe:
        raise NotFoundError("Imóvel", canonico)
    candidatos = {
        busca_service.canonical(str(c.get("codigo")))
        for c in (linha.get("vinculo_candidatos") or []) if c.get("codigo")
    }
    row = _resolver(client, org_id, transacao_id, {
        "codigo_canonical": canonico,
        "vinculo_status": "confirmado",
        "confirmado_por": str(actor_id) if actor_id else None,
        "confirmado_em": datetime.now(timezone.utc).isoformat(),
    })
    return {**row, "origem_codigo": "candidato" if canonico in candidatos else "digitado"}


def rejeitar(client: Any, org_id: UUID, transacao_id: Any, actor_id: Optional[UUID]) -> dict:
    """None of the candidates is right (or the deal must not be used)."""
    linha = _obter(client, org_id, transacao_id)
    if linha["vinculo_status"] != "pendente":
        raise _ja_resolvida(transacao_id, linha["vinculo_status"])
    return _resolver(client, org_id, transacao_id, {
        "codigo_canonical": None,
        "vinculo_status": "rejeitado",
        "confirmado_por": str(actor_id) if actor_id else None,
        "confirmado_em": datetime.now(timezone.utc).isoformat(),
    })
