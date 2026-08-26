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

Existence is checked through `imovel_hub.dados_service.ensure_imovel` rather
than re-derived here — it is the canonical registry check and it raises a 404
the caller can act on, where a raw FK violation would surface as a 500.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub.services import (
    _atendimentos_do_cliente,
    _t,
    ensure_cliente,
    resolve_atendimento_id,
)
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
)

#: Display fields read off the mirror when it still holds the imóvel.
_MIRROR_FIELDS = (
    "titulo", "empreendimento", "logradouro", "numero", "complemento",
    "bairro", "cidade", "uf", "cep", "foto_destaque",
)

#: The registry's delist-time snapshot. It is deliberately NARROWER than the
#: mirror — 063 snapshots what a history row needs to stay legible, not the
#: whole listing — so `logradouro`/`numero`/`cep`/`empreendimento` are simply
#: absent for a delisted imóvel and come back null. That is the honest answer,
#: not a gap to paper over.
_SNAP_MAP = {
    "titulo": "snap_titulo",
    "bairro": "snap_bairro",
    "cidade": "snap_cidade",
    "uf": "snap_uf",
    "foto_destaque": "snap_foto_destaque",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(codigo: str) -> str:
    """Migration 062's one expression for this schema, in Python.

    `imovel_dados` normalises the same way for the same FK, and 076 verified on
    prod that `imovel_registry.codigo_canonical` and `imoveis.codigo` are both
    already uppercase everywhere (0 exceptions).
    """
    return codigo.strip().upper()


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
    imoveis = _enriquecer(client, org_id, [v["codigo"] for v in visitas])

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


def _enriquecer(client: Any, org_id: UUID, codigos: list[str]) -> dict[str, dict]:
    """`codigo -> imóvel`, one batched read per source.

    Registry first because the FK guarantees it exists — so `imovel` is never
    null and `ativo_no_vista` is always answerable. The mirror is PREFERRED for
    display fields when it still holds the imóvel; otherwise the registry's
    delist-time snapshot answers. There is deliberately NO live Vista call:
    roadmap `social-wiring-imoveis-vista-2026-08` P2.5 rules that a clean miss
    is a real, actionable fact, never a fallback.
    """
    unicos = sorted({canonical(c) for c in codigos if c})
    if not unicos:
        return {}

    registry = {
        str(r["codigo_canonical"]): r
        for r in table_reads.in_batched_rows(
            client, "imovel_registry", org_id, "codigo_canonical", unicos,
            order_col="codigo_canonical",
        )
    }
    mirror = {
        str(r["codigo"]): r
        for r in table_reads.in_batched_rows(
            client, "imoveis", org_id, "codigo_norm", unicos, order_col="codigo",
        )
    }
    dados = {
        str(r["codigo"]): r
        for r in table_reads.in_batched_rows(
            client, "imovel_dados", org_id, "codigo", unicos, order_col="codigo",
        )
    }
    atores = table_reads.resolve_actors(
        {d["captador_user_id"] for d in dados.values() if d.get("captador_user_id")}
    )

    return {
        codigo: _imovel_out(
            codigo, registry.get(codigo), mirror.get(codigo), dados.get(codigo), atores
        )
        for codigo in unicos
    }


def _imovel_out(
    codigo: str,
    reg: Optional[dict],
    esp: Optional[dict],
    dad: Optional[dict],
    atores: dict,
) -> dict:
    if esp is not None:
        campos = {k: esp.get(k) for k in _MIRROR_FIELDS}
        campos["corretores"] = esp.get("corretores") or []
        fonte = "imoveis"
    else:
        campos = {k: None for k in _MIRROR_FIELDS}
        campos["corretores"] = []
        if reg is not None:
            campos.update({k: reg.get(snap) for k, snap in _SNAP_MAP.items()})
        fonte = "registry"

    return {
        "codigo": codigo,
        **campos,
        # 🔴 The canonical model for "corretor responsável pela captação"
        # (migration 075): a USER, not a name. The commission slice is
        # attributed to it, and two spellings of a free-text name become two
        # people. NULL is the honest state for an imóvel with no recorded
        # captador — never silently reassigned to the agency.
        "captacao": table_reads.actor(atores, (dad or {}).get("captador_user_id")),
        # Real information, not bookkeeping: a corretor routing a visit to a
        # property that has left the catalog needs to know before driving there.
        "ativo_no_vista": bool((reg or {}).get("ativo_no_vista")),
        "fonte": fonte,
    }


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
    return _visita_out(row, _enriquecer(client, org_id, [alvo]))


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
    return _visita_out(atualizado, _enriquecer(client, org_id, [str(atual["codigo"])]))


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
