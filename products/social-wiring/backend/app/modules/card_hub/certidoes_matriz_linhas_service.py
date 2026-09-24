"""`POST/PATCH/DELETE /api/clientes/{cliente_id}/certidoes/matriz/linhas` —
the "+ Adicionar certidão" action on the Certidões matriz tab: per-card
CUSTOM rows, beyond the fixed 13 (5.1-5.13), an operator adds/renames/
removes (owner directive, 2026-09-24 follow-up; migration 170).

`criar` fans out a `pendente` placeholder resultado for the new row across
every consulta ALREADY linked to this card's columns (`certidoes_matriz_
service.resolver_colunas` — the SAME column resolution `montar_matriz`
reads, never a second "who is on this card" answer), so the row is
immediately recordable through the EXISTING audited manual-record path
(`POST /api/certidoes/resultados/{id}/upload`, `PATCH /api/certidoes/
resultados/{id}`) with no extra step. `scoped-improvement:` a consulta
linked to this card AFTER a custom row already exists does not retroactively
get that row's placeholder — same gap the three fixed manual types (Serasa/
TJSP e-SAJ/e-PROC) DON'T have, since those fan out again at every
`vincular_parte`/`vincular_cliente`/`vincular_empresa` call; wiring custom
rows into that same hook is a reasonable follow-up, deferred here to avoid
a `certidoes` <-> `card_hub` import-direction coupling this pass does not
need to take on.

`remover` is a soft-delete of the ROW DEFINITION ONLY — its
`certidao_resultados` rows are never touched (owner directive: "must NOT
delete any recorded result").
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import (
    InternalError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub.certidoes_matriz_service import (
    LINHAS_CUSTOMIZADAS_TABLE,
    resolver_colunas,
)
from app.modules.card_hub.services import ensure_cliente
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.registry import CUSTOM_ROW_TIPO
from app.services import table_reads

#: The checklist-order base for every custom-row resultado (`ordem` on
#: `certidao_resultados` — the EMISSION checklist's own display order,
#: unrelated to the matriz's "5.{ordem}" row label). The fixed catalogue
#: tops out at 14 (`fgts_regularidade`); 100+ keeps every custom row's
#: resultados safely disjoint without needing to track the fixed set's own
#: ceiling here.
_RESULTADO_ORDEM_BASE = 100

#: Row-definition `ordem` before any custom row exists — matriz rows 5.1-
#: 5.13 are fixed, so the first custom row is 5.14.
_ORDEM_INICIAL = 13


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _linha_ou_404(client: Any, org_id: UUID, cliente_id: UUID, linha_id: UUID) -> dict:
    rows = (
        _t(client, LINHAS_CUSTOMIZADAS_TABLE)
        .select("id, nome, ordem, excluida_em")
        .eq("id", str(linha_id))
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(LINHAS_CUSTOMIZADAS_TABLE, str(linha_id))
    return rows[0]


def _validar_nome(nome: str) -> str:
    nome = (nome or "").strip()
    if not nome:
        raise ValidationError_("O nome da certidão não pode ficar em branco.", field="nome")
    return nome


def _proximo_ordem(client: Any, org_id: UUID, cliente_id: UUID) -> int:
    """MAX `ordem` ever assigned for this card (including soft-deleted) + 1
    — a removed row's label is never reused by the next one created."""
    rows = (
        _t(client, LINHAS_CUSTOMIZADAS_TABLE)
        .select("ordem")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []
    maior = max((r["ordem"] for r in rows), default=_ORDEM_INICIAL)
    return maior + 1


def _fan_out_para_colunas(client: Any, org_id: UUID, cliente_id: UUID, linha: dict) -> int:
    """One `pendente` placeholder resultado per (consulta, this new row) —
    every consulta already linked to a column of THIS card, so the row is
    immediately recordable through the existing manual-record path. Returns
    the number of placeholders written."""
    _atendimento_id, colunas = resolver_colunas(client, org_id, cliente_id)
    if not colunas:
        return 0

    novos: list[dict] = []
    for coluna in colunas:
        if coluna["kind"] == "pessoa":
            consultas = (
                _t(client, certidoes_svc.CONSULTAS)
                .select("id")
                .eq("org_id", str(org_id))
                .eq("cliente_id", coluna["id"])
                .eq("tipo_documento", "cpf")
                .is_("excluida_em", "null")
                .execute()
            ).data or []
        else:
            consultas = (
                _t(client, certidoes_svc.CONSULTAS)
                .select("id")
                .eq("org_id", str(org_id))
                .eq("empresa_id", coluna["id"])
                .eq("tipo_documento", "cnpj")
                .is_("excluida_em", "null")
                .execute()
            ).data or []
        for consulta in consultas:
            novos.append({
                "consulta_id": consulta["id"],
                "org_id": str(org_id),
                "tipo": CUSTOM_ROW_TIPO,
                "linha_customizada_id": str(linha["id"]),
                "nome_display": f"Outras: {linha['nome']}",
                "ordem": _RESULTADO_ORDEM_BASE + linha["ordem"],
                "status": "pendente",
            })
    if novos:
        _t(client, certidoes_svc.RESULTADOS).insert(novos).execute()
    return len(novos)


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """Every active custom row for this card, oldest first — mirrors
    `certidoes_matriz_service.linhas_customizadas_ativas`, exposed here too
    for a caller that only wants the rows, not the whole matriz."""
    ensure_cliente(client, org_id, cliente_id)
    return (
        _t(client, LINHAS_CUSTOMIZADAS_TABLE)
        .select("id, nome, ordem, created_at")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .is_("excluida_em", "null")
        .order("ordem")
        .execute()
    ).data or []


def criar(
    client: Any, org_id: UUID, cliente_id: UUID, *, nome: str, created_by: Optional[Any] = None,
) -> dict:
    """`POST .../matriz/linhas` — "+ Adicionar certidão". Creates the row,
    computes its `ordem` (its matriz label, "5.{ordem}"), and fans out a
    placeholder resultado across every column already on this card."""
    ensure_cliente(client, org_id, cliente_id)
    nome = _validar_nome(nome)
    ordem = _proximo_ordem(client, org_id, cliente_id)

    inserted = (
        _t(client, LINHAS_CUSTOMIZADAS_TABLE)
        .insert({
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "nome": nome,
            "ordem": ordem,
            "created_by": str(created_by) if created_by else None,
        })
        .execute()
    ).data
    if not inserted:
        raise InternalError("Erro ao criar a linha de certidão customizada.")
    linha = inserted[0]

    _fan_out_para_colunas(client, org_id, cliente_id, linha)
    return linha


def renomear(client: Any, org_id: UUID, cliente_id: UUID, linha_id: UUID, *, nome: str) -> dict:
    """`PATCH .../matriz/linhas/{linha_id}` — rename. The row's already-
    fanned-out resultados keep their OLD `nome_display` (a historical label
    on an existing record, never silently rewritten) — only the row
    definition's own name, read live by `montar_matriz`, changes."""
    _linha_ou_404(client, org_id, cliente_id, linha_id)
    nome = _validar_nome(nome)
    updated = (
        _t(client, LINHAS_CUSTOMIZADAS_TABLE)
        .update({"nome": nome, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", str(linha_id))
        .eq("org_id", str(org_id))
        .execute()
    ).data
    return updated[0] if updated else _linha_ou_404(client, org_id, cliente_id, linha_id)


def remover(client: Any, org_id: UUID, cliente_id: UUID, linha_id: UUID) -> None:
    """`DELETE .../matriz/linhas/{linha_id}` — soft-delete the ROW
    DEFINITION only. Its `certidao_resultados` rows are NEVER touched (owner
    directive) — they simply stop being reachable from the matriz's row
    list once `excluida_em` is set, same posture `soft_delete_consulta`
    (migration 161) already takes for a whole consulta."""
    _linha_ou_404(client, org_id, cliente_id, linha_id)
    (
        _t(client, LINHAS_CUSTOMIZADAS_TABLE)
        .update({"excluida_em": datetime.now(timezone.utc).isoformat()})
        .eq("id", str(linha_id))
        .eq("org_id", str(org_id))
        .execute()
    )


__all__ = ["criar", "listar", "remover", "renomear"]
