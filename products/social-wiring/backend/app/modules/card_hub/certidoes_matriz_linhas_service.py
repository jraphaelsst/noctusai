"""`POST/PATCH/DELETE /api/clientes/{cliente_id}/certidoes/matriz/linhas` —
the "+ Adicionar certidão" action on the Certidões matriz tab: per-card
CUSTOM rows, beyond the fixed 13 (5.1-5.13), an operator adds/renames/
removes (owner directive, 2026-09-24 follow-up; migration 170).

`criar` fans out a `pendente` placeholder resultado for the new row across
every consulta ALREADY linked to this card's columns (`certidoes_matriz_
service.resolver_colunas` — the SAME column resolution `montar_matriz`
reads, never a second "who is on this card" answer) via `certidoes.matriz_
custom_rows.fan_out_linhas_customizadas`, so the row is immediately
recordable through the EXISTING audited manual-record path (`POST /api/
certidoes/resultados/{id}/upload`, `PATCH /api/certidoes/resultados/{id}`)
with no extra step. The MIRROR gap — a consulta linked to this card AFTER a
custom row already exists — is closed on the `certidoes` side:
`routers.certidoes.vincular_parte`/`vincular_cliente`/`vincular_empresa`
call that SAME `fan_out_linhas_customizadas` function (owner directive,
2026-09-24 follow-up round 2) — one shared fan-out, two trigger points,
idempotent either way (never duplicates a placeholder for the same
consulta+linha).

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

from app.modules.card_hub.certidoes_matriz_service import resolver_colunas
from app.modules.card_hub.services import ensure_cliente
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.matriz_custom_rows import (
    LINHAS_CUSTOMIZADAS_TABLE,
    fan_out_linhas_customizadas,
    linhas_customizadas_ativas,
)
from app.services import table_reads

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
    """Every consulta already linked to a column of THIS card gets a
    `pendente` placeholder for EVERY active custom row (not just `linha` —
    `fan_out_linhas_customizadas` is naturally idempotent, so re-running it
    per consulta here is a harmless belt-and-suspenders backfill of any
    other row this consulta might be missing too). Returns the number of
    NEW placeholders written for `linha` specifically."""
    _atendimento_id, colunas = resolver_colunas(client, org_id, cliente_id)
    if not colunas:
        return 0

    escritos = 0
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
            escritos += fan_out_linhas_customizadas(client, org_id, consulta["id"], str(cliente_id))
    return escritos


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """Every active custom row for this card, oldest first — a thin
    `ensure_cliente`-gated wrapper over `certidoes.matriz_custom_rows.
    linhas_customizadas_ativas`, exposed here too for a caller that only
    wants the rows, not the whole matriz."""
    ensure_cliente(client, org_id, cliente_id)
    return linhas_customizadas_ativas(client, org_id, cliente_id)


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
