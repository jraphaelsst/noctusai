"""`contrato_testemunhas` (migration 168) — which of the org's registered
testemunhas (`org_testemunhas`) sign THIS contract, and in what order.

Sibling of `matriculas.estrutura_service`'s act selection
(`obter_selecao`/`definir_selecao`) — same "operator picks a subset from a
registry, scoped to one contract" shape, simplified (no papel/permuta
grouping): a contract just has an ORDERED LIST of witnesses.

`definir` REPLACES the whole selection (delete-then-insert), never a partial
PATCH — same posture `estrutura_service.definir_selecao` takes, and for the
same reason: a stale client re-sending its last-known list must never merge
with what another tab already saved.

🔴 CPF-REQUIRED IS ENFORCED HERE TOO (defense in depth, migration 168 header)
-------------------------------------------------------------------------
`TestemunhasSection.tsx` only offers CPF-complete witnesses as selectable —
but `definir` re-validates against `org_testemunhas` directly rather than
trusting the request body: a `testemunha_id` that does not resolve to this
org, or resolves to one with no CPF ("CPF pendente"), is refused with a
NAMED 400, never silently accepted.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.contrato_gerador.politica import MAX_TESTEMUNHAS
from app.services import table_reads

TABLE = "contrato_testemunhas"
REGISTRO_TABLE = "org_testemunhas"


class TestemunhaSelecionadaInvalida(AppException):
    def __init__(self, motivo: str) -> None:
        super().__init__(
            code="TESTEMUNHA_SELECIONADA_INVALIDA",
            message=motivo,
            status_code=400,
        )


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _registro_por_id(client: Any, org_id: UUID) -> dict[str, dict]:
    # The registry is open-ended since migration 168 (and soft-deleted rows
    # stay in it), so it is paged past PostgREST's silent 1 000-row cap.
    rows = table_reads.paged_rows(client, REGISTRO_TABLE, org_id)
    return {str(r["id"]): r for r in rows}


def _testemunha_saida(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "nome": row.get("nome"),
        "cpf": row.get("cpf"),
        "email": row.get("email"),
        "celular": row.get("celular"),
        "excluida": bool(row.get("excluida_em")),
    }


def listar(client: Any, org_id: UUID, atendimento_id: UUID, contrato_id: UUID) -> dict:
    """The contract's selected witnesses, in print order — each resolved
    against the CURRENT registry row (a nome/e-mail edit made after
    selection is reflected here immediately, same live-join posture the
    generator's own loader takes reading `org_testemunhas`).

    A soft-deleted witness (`excluida_em`) is STILL listed — deleting it from
    the registry must not remove it from contracts that already selected it
    (owner directive, 2026-09-24) — and carries `excluida: true` so the UI can
    say so. A registry row can no longer vanish (the FK is `ON DELETE
    RESTRICT`, migration 168); the `None` guard below only covers a row
    outside this org, which `exigir_contrato` already makes unreachable."""
    contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    registro = _registro_por_id(client, org_id)
    linhas = sorted(
        (
            # postgrest-unbounded-ok: ONE contract's selection — at most
            # MAX_TESTEMUNHAS (5) rows, refused above that at write time.
            _t(client, TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("contrato_id", str(contrato_id))
            .execute()
        ).data
        or [],
        key=lambda r: r.get("ordem") or 0,
    )
    items = []
    for linha in linhas:
        testemunha = registro.get(str(linha["testemunha_id"]))
        if testemunha is None:
            continue
        items.append(
            {"id": linha["id"], "ordem": linha["ordem"], "testemunha": _testemunha_saida(testemunha)}
        )
    return {"items": items, "total": len(items)}


def definir(
    client: Any,
    org_id: UUID,
    atendimento_id: UUID,
    contrato_id: UUID,
    *,
    testemunha_ids: Sequence[UUID],
    usuario_id: Optional[Any],
) -> dict:
    """Replace this contract's witness selection wholesale. `[]` clears it —
    a contract can go back to "no witnesses chosen yet", the same readiness-
    incomplete state a freshly-generated one starts in."""
    contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)

    ids = [str(i) for i in testemunha_ids]
    if len(ids) != len(set(ids)):
        raise TestemunhaSelecionadaInvalida("A mesma testemunha foi selecionada mais de uma vez.")
    if len(ids) > MAX_TESTEMUNHAS:
        raise TestemunhaSelecionadaInvalida(
            f"Um contrato tem no máximo {MAX_TESTEMUNHAS} testemunhas."
        )

    registro = _registro_por_id(client, org_id)
    # A soft-deleted witness (settings DELETE → `excluida_em`) stays on every
    # contract that ALREADY selected it — re-saving that contract must keep
    # it — but it cannot be newly added to one.
    ja_selecionadas = {
        str(r["testemunha_id"])
        for r in (
            # postgrest-unbounded-ok: ONE contract's selection — at most
            # MAX_TESTEMUNHAS (5) rows.
            _t(client, TABLE)
            .select("testemunha_id")
            .eq("org_id", str(org_id))
            .eq("contrato_id", str(contrato_id))
            .execute()
        ).data
        or []
    }
    for tid in ids:
        testemunha = registro.get(tid)
        if testemunha is None:
            raise NotFoundError(REGISTRO_TABLE, tid)
        if testemunha.get("excluida_em") and tid not in ja_selecionadas:
            raise TestemunhaSelecionadaInvalida(
                f"{testemunha.get('nome') or 'Testemunha'} foi removida do cadastro "
                "e não pode ser adicionada a um novo contrato."
            )
        if not testemunha.get("cpf"):
            raise TestemunhaSelecionadaInvalida(
                f"{testemunha.get('nome') or 'Testemunha'}: CPF pendente — cadastre "
                "o CPF antes de selecioná-la para um contrato."
            )

    _t(client, TABLE).delete().eq("org_id", str(org_id)).eq(
        "contrato_id", str(contrato_id)
    ).execute()

    if ids:
        linhas = [
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "contrato_id": str(contrato_id),
                "testemunha_id": tid,
                "ordem": ordem,
                "created_por": str(usuario_id) if usuario_id else None,
            }
            for ordem, tid in enumerate(ids, start=1)
        ]
        _t(client, TABLE).insert(linhas).execute()

    return listar(client, org_id, atendimento_id, contrato_id)
