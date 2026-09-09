"""Roteiros + visitas — a planned visiting route and what happened on it.

WHY THIS MODULE EXISTS
----------------------
A visit used to be an AGENDAMENTO whose `tipo` happened to be 'visita'. That is
a calendar entry, and a calendar entry cannot be a route: it holds one property,
it has no order, it cannot be printed, and — the reason this module exists — it
cannot be COUNTED. A corretor plans "first this one, then that one, last this
one" and afterwards records which visits actually happened.

Migration `082` gives the route its own table and each property on it a
`visitas` row carrying `ordem`, `status` and `observacao`. The Agendar button
stops OFFERING 'visita' in the same commit; the DB CHECK is NOT narrowed,
because live rows already carry that value.

WHOSE ROTEIRO IS IT — the ATENDIMENTO's
---------------------------------------
Migration `061`'s ruling, unchanged: a person accumulates deals over time (D17),
so a route walked for a 2024 purchase must not pile onto a live negotiation. The
card IS the person and reads across that person's atendimentos, but each row
knows which deal it belongs to. That is also what keeps "what happened with this
cliente in 2024" answerable per deal instead of as one undifferentiated pile.

🔴 THE REGISTRY, NEVER THE MIRROR
---------------------------------
`visitas.codigo` is FK'd to `imovel_registry (org_id, codigo_canonical)` — see
migration 082's header, and 076's before it. `imoveis` is a cache of what Vista
says TODAY and 35% of registered imóveis have already left it; an imóvel leaves
the catalog because it was SOLD, i.e. exactly when its visit history matters.
Enrichment PREFERS the mirror for display fields and falls back to the
registry's `snap_*`, but membership is always the registry's answer.

That enrichment was written here and now lives in
`imovel_hub.busca_service` — the registry-backed imóvel picker needs exactly
the same "render this código" answer, and a second consumer is where a copy
stops being a judgement call. Nothing about it changed in the move; this
module imports `canonical` / `enriquecer` and is otherwise as it was.

Existence is checked through `imovel_hub.dados_service.ensure_imovel` rather
than re-derived here — it is the canonical registry check and it raises a 404
the caller can act on, where a raw FK violation would surface as a 500.

🔴 VISITA → PROPOSTA → THE DEAL (migration 104)
-----------------------------------------------
A roteiro carries N candidate imóveis; one of them generates a proposta; the
proposta that is ACCEPTED is the property the atendimento is about and the one
the contract automation consumes. `registrar_proposta` is that hinge, and it
owns the two rules a constraint cannot:

  · at most ONE accepted proposta per ATENDIMENTO (the scope is two joins away
    from these rows, so no partial unique index can reach it); and
  · accepting WRITES `atendimento_negociacao.imovel_codigo`, which is the only
    legitimate auto-write of that column — see
    `negociacao_service.definir_imovel_do_atendimento` for why it does not
    contradict the rule that a lead's origin código never lands there.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub import negociacao_service
from app.modules.card_hub.services import (
    _atendimentos_do_cliente,
    _t,
    ensure_cliente,
    resolve_atendimento_id,
)
from app.modules.imovel_hub.busca_service import canonical, enriquecer
from app.modules.imovel_hub.dados_service import ensure_imovel
from app.services import table_reads

TABLE = "roteiros"
VISITAS_TABLE = "visitas"

#: Mirrors the DB CHECK in `082`. Both exist on purpose: the schema protects the
#: API surface, the CHECK protects every other writer (a migration, a script, a
#: future job). Neither is redundant with the other.
STATUS_VALIDOS = ("pendente", "realizada", "nao_realizada")

_ROTEIRO_FIELDS = ("id", "atendimento_id", "titulo", "created_at")
_VISITA_FIELDS = (
    "id", "roteiro_id", "codigo", "ordem", "status",
    "observacao", "feedback_em", "created_at",
    # Migration 104 — the proposta axis. Deliberately NOT folded into
    # `status`: see that migration's header and `registrar_proposta` below.
    "proposta_em", "proposta_por", "proposta_aceita_em", "proposta_aceita_por",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── reads ──────────────────────────────────────────────────────────────────

def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Every live roteiro across this person's atendimentos, newest first."""
    ensure_cliente(client, org_id, cliente_id)
    atendimento_ids = [
        str(r["id"]) for r in _atendimentos_do_cliente(client, org_id, cliente_id)
    ]
    if not atendimento_ids:
        return {"items": [], "total": 0}

    roteiros = [
        r
        for r in table_reads.in_batched_rows(
            client, TABLE, org_id, "atendimento_id", atendimento_ids
        )
        if r.get("deleted_at") is None
    ]
    roteiros.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    items = _montar(client, org_id, roteiros)
    return {"items": items, "total": len(items)}


def obter(client: Any, org_id: UUID, cliente_id: UUID, roteiro_id: UUID) -> dict:
    return _montar(client, org_id, [_obter(client, org_id, cliente_id, roteiro_id)])[0]


def _obter(client: Any, org_id: UUID, cliente_id: UUID, roteiro_id: UUID) -> dict:
    """The row, proven to belong to THIS cliente. The ownership check IS the
    authorisation — an id alone must never be enough to read or edit someone
    else's route. Same shape as `agendamentos_service._obter`."""
    ensure_cliente(client, org_id, cliente_id)
    permitidos = {str(r["id"]) for r in _atendimentos_do_cliente(client, org_id, cliente_id)}
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(roteiro_id))
        .execute()
    ).data or []
    row = rows[0] if rows else None
    if row is None or row.get("deleted_at") or str(row.get("atendimento_id")) not in permitidos:
        raise NotFoundError(TABLE, str(roteiro_id))
    return row


def _visitas_de(client: Any, org_id: UUID, roteiro_ids: list[str]) -> list[dict]:
    return [
        v
        for v in table_reads.in_batched_rows(
            client, VISITAS_TABLE, org_id, "roteiro_id", roteiro_ids
        )
        if v.get("deleted_at") is None
    ]


def _montar(client: Any, org_id: UUID, roteiros: list[dict]) -> list[dict]:
    """Roteiros + their visitas + the imóvel behind each one.

    Batched per SOURCE, never per visita: a handful of reads regardless of how
    many properties sit on how many routes. The N+1 this avoids is the one
    migration 080 had to undo elsewhere in this schema.
    """
    if not roteiros:
        return []
    visitas = _visitas_de(client, org_id, [str(r["id"]) for r in roteiros])
    imoveis = enriquecer(client, org_id, [v["codigo"] for v in visitas])

    por_roteiro: dict[str, list[dict]] = {}
    for v in visitas:
        por_roteiro.setdefault(str(v["roteiro_id"]), []).append(v)

    saida = []
    for r in roteiros:
        linhas = por_roteiro.get(str(r["id"]), [])
        linhas.sort(key=lambda v: (v.get("ordem") or 0, v.get("created_at") or ""))
        saida.append(
            {
                **{k: r.get(k) for k in _ROTEIRO_FIELDS},
                "visitas": [_visita_out(v, imoveis) for v in linhas],
                "contagem": _contagem(linhas),
            }
        )
    return saida


def _contagem(visitas: list[dict]) -> dict:
    """The contabilização the user asked for. Three buckets, not two: "hasn't
    happened yet" and "didn't happen" are different facts, and merging them
    would file every future visit under "did not"."""
    return {
        "total": len(visitas),
        "realizadas": sum(1 for v in visitas if v.get("status") == "realizada"),
        "nao_realizadas": sum(1 for v in visitas if v.get("status") == "nao_realizada"),
        "pendentes": sum(1 for v in visitas if v.get("status") == "pendente"),
    }


def _visita_out(row: dict, imoveis: dict[str, dict]) -> dict:
    out = {k: row.get(k) for k in _VISITA_FIELDS}
    out["imovel"] = imoveis.get(canonical(str(row.get("codigo") or "")))
    return out


# ── writes ─────────────────────────────────────────────────────────────────

def criar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    imoveis: list[str],
    titulo: Optional[str] = None,
    atendimento_id: Optional[UUID] = None,
) -> dict:
    """A route and one visita per property, in the order given."""
    ensure_cliente(client, org_id, cliente_id)
    alvo = resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)
    codigos = _validar_codigos(client, org_id, imoveis)

    roteiro_id = str(uuid4())
    agora = _now()
    _t(client, TABLE).insert(
        {
            "id": roteiro_id,
            "org_id": str(org_id),
            "atendimento_id": alvo,
            "titulo": (titulo or "").strip() or None,
            "created_at": agora,
        }
    ).execute()

    _t(client, VISITAS_TABLE).insert(
        [
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "roteiro_id": roteiro_id,
                "codigo": codigo,
                "ordem": i,
                "status": "pendente",
                "created_at": agora,
            }
            for i, codigo in enumerate(codigos)
        ]
    ).execute()

    return obter(client, org_id, cliente_id, UUID(roteiro_id))


def _validar_codigos(client: Any, org_id: UUID, imoveis: list[str]) -> list[str]:
    """Canonicalise, refuse duplicates, and prove every código is one we know.

    Duplicates are REFUSED rather than deduped: a route that visits the same
    property twice is a mistake at the keyboard, and silently collapsing it
    would change the order the user dragged without telling them. The dialog
    already disables an added código — this is the backstop, not the UX.
    """
    codigos = [canonical(c) for c in imoveis]
    vistos: set[str] = set()
    repetidos: set[str] = set()
    for codigo in codigos:
        if codigo in vistos:
            repetidos.add(codigo)
        vistos.add(codigo)
    if repetidos:
        raise ValidationError_(
            f"imóvel repetido no roteiro: {', '.join(sorted(repetidos))}",
            field="imoveis",
        )
    for codigo in codigos:
        # 404 on an unknown código, explicitly — a raw FK violation would
        # surface as a 500 from the driver and tell the caller nothing.
        ensure_imovel(client, org_id, codigo)
    return codigos


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    *,
    titulo: Optional[str] = ...,
) -> dict:
    """`...` sentinels an unset field — only what the PATCH carried is written."""
    _obter(client, org_id, cliente_id, roteiro_id)
    if titulo is not ...:
        _t(client, TABLE).update(
            {"titulo": (titulo or "").strip() or None}
        ).eq("id", str(roteiro_id)).execute()
    return obter(client, org_id, cliente_id, roteiro_id)


def remover(client: Any, org_id: UUID, cliente_id: UUID, roteiro_id: UUID) -> None:
    """Soft delete, per D3's reversibility bar. The visitas' own rows are left
    alone — undoing this is one UPDATE rather than a resurrection — and both
    the card read and `vw_imovel_visita_contagem` exclude them via the
    roteiro's `deleted_at`."""
    _obter(client, org_id, cliente_id, roteiro_id)
    _t(client, TABLE).update({"deleted_at": _now()}).eq("id", str(roteiro_id)).execute()


def reordenar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_ids: list[UUID],
) -> dict:
    """Rewrite `ordem` to the position of each id in `visita_ids`.

    The list must be the COMPLETE live set. A partial reorder that silently
    succeeded would leave two visitas sharing a position and the route in an
    order nobody chose — so a mismatch is a 400 naming both sides.
    """
    _obter(client, org_id, cliente_id, roteiro_id)
    atuais = {str(v["id"]) for v in _visitas_de(client, org_id, [str(roteiro_id)])}
    pedidos = [str(v) for v in visita_ids]

    faltando = sorted(atuais - set(pedidos))
    desconhecidos = sorted(set(pedidos) - atuais)
    if faltando or desconhecidos or len(pedidos) != len(set(pedidos)):
        raise ValidationError_(
            "visita_ids deve conter exatamente as visitas deste roteiro, uma vez "
            f"cada — faltando: {faltando or '[]'}, desconhecidos: {desconhecidos or '[]'}",
            field="visita_ids",
        )

    for i, visita_id in enumerate(pedidos):
        _t(client, VISITAS_TABLE).update({"ordem": i}).eq("id", visita_id).execute()
    return obter(client, org_id, cliente_id, roteiro_id)


def adicionar_visita(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    codigo: str,
) -> dict:
    """Append one property to the end of an existing route."""
    _obter(client, org_id, cliente_id, roteiro_id)
    linhas = _visitas_de(client, org_id, [str(roteiro_id)])
    alvo = canonical(codigo)
    if any(canonical(str(v["codigo"])) == alvo for v in linhas):
        raise ValidationError_(f"imóvel já está no roteiro: {alvo}", field="codigo")
    ensure_imovel(client, org_id, alvo)

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "roteiro_id": str(roteiro_id),
        "codigo": alvo,
        "ordem": max((v.get("ordem") or 0) for v in linhas) + 1 if linhas else 0,
        "status": "pendente",
        "created_at": _now(),
    }
    _t(client, VISITAS_TABLE).insert(row).execute()
    return _visita_out(row, enriquecer(client, org_id, [alvo]))


def atualizar_visita(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
    *,
    status: Optional[str] = ...,
    observacao: Optional[str] = ...,
) -> dict:
    """The corretor's feedback. `...` sentinels an unset field."""
    atual = _obter_visita(client, org_id, cliente_id, roteiro_id, visita_id)

    updates: dict = {}
    if observacao is not ...:
        updates["observacao"] = (observacao or "").strip() or None
    if status is not ...:
        if status not in STATUS_VALIDOS:
            raise ValidationError_(
                f"status must be one of {list(STATUS_VALIDOS)}, got {status!r}",
                field="status",
            )
        updates["status"] = status
        # Stamped when the visit FIRST leaves 'pendente', never re-stamped: it
        # is the honest "when did this happen" the timeline derives its entry
        # from, and a second stamp would move a past event forward in the sort.
        if status != "pendente" and not atual.get("feedback_em"):
            updates["feedback_em"] = _now()

    if updates:
        _t(client, VISITAS_TABLE).update(updates).eq("id", str(visita_id)).execute()

    atualizado = {**atual, **updates}
    return _visita_out(atualizado, enriquecer(client, org_id, [str(atual["codigo"])]))


def registrar_proposta(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
    *,
    proposta: Optional[bool] = ...,
    aceita: Optional[bool] = ...,
    usuario_id: Optional[UUID] = None,
) -> dict:
    """Record that a visita produced a proposta, and that it was accepted.

    `...` sentinels an unset flag, matching `atualizar_visita`. Separate from
    that function on purpose: `status` answers "did the visit happen" and this
    answers "did it produce an offer", and migration 104's header is the long
    version of why merging the two axes destroys the contabilização 082 exists
    for.

    THE FOUR RULES, ALL OF THEM HERE RATHER THAN IN THE SCHEMA
    ----------------------------------------------------------
    1. An acceptance needs an offer. The DB CHECK says so too; this raises a
       named 400 instead of a driver-level 500, same division of labour as
       `_validar_split`.
    2. At most ONE accepted proposta per ATENDIMENTO. `atendimento_negociacao`
       is keyed on `atendimento_id` and holds exactly one `imovel_codigo`, so
       two accepted propostas would be two answers to "what is being sold".
       🔴 This is NOT enforceable by a unique index: the scope is the
       atendimento, these rows are keyed to a ROTEIRO, and the join
       `visitas → roteiros → atendimentos` is two hops a partial index cannot
       traverse. It lives here because that is the only place it can — not
       because anyone forgot.
    3. Accepting writes the deal's `imovel_codigo`. See
       `negociacao_service.definir_imovel_do_atendimento`.
    4. Nothing is silently overwritten and nothing is silently left behind —
       see the two branches below.
    """
    atual = _obter_visita(client, org_id, cliente_id, roteiro_id, visita_id)
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)
    atendimento_id = UUID(str(roteiro["atendimento_id"]))
    codigo = canonical(str(atual["codigo"]))

    updates: dict = {}
    tinha_proposta = atual.get("proposta_em") is not None
    tinha_aceite = atual.get("proposta_aceita_em") is not None

    if proposta is not ...:
        if proposta:
            if not tinha_proposta:
                updates["proposta_em"] = _now()
                updates["proposta_por"] = str(usuario_id) if usuario_id else None
        elif tinha_proposta:
            # Withdrawing the offer withdraws the acceptance with it: the CHECK
            # forbids an acceptance with no offer, so leaving `proposta_aceita_em`
            # behind would be a constraint violation surfacing as a 500. The
            # deal's imóvel is unwound below by the same rule an explicit
            # un-accept follows.
            updates["proposta_em"] = None
            updates["proposta_por"] = None
            if tinha_aceite:
                aceita = False

    quer_aceitar = aceita is True
    quer_desaceitar = aceita is False and tinha_aceite

    if quer_aceitar and not tinha_aceite:
        if not (tinha_proposta or updates.get("proposta_em")):
            raise ValidationError_(
                "não é possível aceitar uma proposta que não foi registrada — "
                "marque a proposta nesta visita primeiro",
                field="aceita",
            )
        _recusar_segundo_aceite(client, org_id, cliente_id, atendimento_id, visita_id)
        updates["proposta_aceita_em"] = _now()
        updates["proposta_aceita_por"] = str(usuario_id) if usuario_id else None

    if quer_desaceitar:
        updates["proposta_aceita_em"] = None
        updates["proposta_aceita_por"] = None

    if updates:
        _t(client, VISITAS_TABLE).update(updates).eq("id", str(visita_id)).execute()

    # 🔴 THE DEAL FOLLOWS THE ACCEPTANCE, in both directions, and says so.
    if updates.get("proposta_aceita_em"):
        atual_deal = negociacao_service.imovel_do_atendimento(
            client, org_id, atendimento_id
        )
        if atual_deal and canonical(str(atual_deal)) != codigo:
            # The operator is changing WHICH property this deal is about.
            # That is a real decision and it deserves to be a visible act
            # rather than a side effect of clicking "aceita" on a second
            # visita — so it is refused here and re-made deliberately.
            raise ValidationError_(
                f"a negociação já está no imóvel {atual_deal}; aceitar a proposta "
                f"de {codigo} mudaria o imóvel do negócio — altere o imóvel da "
                "negociação explicitamente antes de aceitar",
                field="aceita",
            )
        negociacao_service.definir_imovel_do_atendimento(
            client, org_id, atendimento_id, codigo, usuario_id=usuario_id
        )
    elif "proposta_aceita_em" in updates:
        # Un-accepting. Clearing the deal's imóvel is the honest move ONLY
        # when it is still this visita's — leaving it would keep a closed-deal
        # property on a deal nobody has agreed, which is the stale answer the
        # brief refuses. When it is somebody else's código the operator set it
        # by hand and this un-accept has nothing to say about it, so it stands.
        atual_deal = negociacao_service.imovel_do_atendimento(
            client, org_id, atendimento_id
        )
        if atual_deal and canonical(str(atual_deal)) == codigo:
            negociacao_service.definir_imovel_do_atendimento(
                client, org_id, atendimento_id, None, usuario_id=usuario_id
            )

    atualizado = {**atual, **updates}
    return _visita_out(atualizado, enriquecer(client, org_id, [codigo]))


def _recusar_segundo_aceite(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    atendimento_id: UUID,
    visita_id: UUID,
) -> None:
    """One accepted proposta per atendimento — checked across the join.

    Reads every roteiro of THIS atendimento (not of the cliente: a person
    accumulates deals over time per 061/D17, and an acceptance on a 2024
    purchase says nothing about a live negotiation) and refuses if another
    visita already carries an acceptance.

    Read-then-write, so two concurrent accepts could in principle both pass.
    That is accepted deliberately: this is a single operator clicking a button
    on one card, the losing write is recoverable by un-accepting, and the
    alternative — an advisory lock or a trigger — would be machinery for a
    race nobody can produce. The FK'd `imovel_codigo` still holds the deal to
    exactly one property regardless.
    """
    roteiros = [
        r
        for r in table_reads.in_batched_rows(
            client, TABLE, org_id, "atendimento_id", [str(atendimento_id)]
        )
        if r.get("deleted_at") is None
    ]
    if not roteiros:
        return
    for v in _visitas_de(client, org_id, [str(r["id"]) for r in roteiros]):
        if str(v["id"]) == str(visita_id):
            continue
        if v.get("proposta_aceita_em"):
            raise ValidationError_(
                f"este atendimento já tem uma proposta aceita, no imóvel "
                f"{v.get('codigo')} — desfaça aquela antes de aceitar outra",
                field="aceita",
            )


def remover_visita(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
) -> None:
    _obter_visita(client, org_id, cliente_id, roteiro_id, visita_id)
    _t(client, VISITAS_TABLE).update({"deleted_at": _now()}).eq(
        "id", str(visita_id)
    ).execute()


def _obter_visita(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
) -> dict:
    """Proven to belong to THIS roteiro, which is proven to belong to THIS
    cliente. Both legs, every time — reaching a visita through someone else's
    roteiro id must fail exactly as reaching the roteiro itself would."""
    _obter(client, org_id, cliente_id, roteiro_id)
    rows = (
        _t(client, VISITAS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(visita_id))
        .execute()
    ).data or []
    row = rows[0] if rows else None
    if row is None or row.get("deleted_at") or str(row.get("roteiro_id")) != str(roteiro_id):
        raise NotFoundError(VISITAS_TABLE, str(visita_id))
    return row
