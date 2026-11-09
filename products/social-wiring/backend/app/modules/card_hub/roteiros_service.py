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

🔴 THE LIFECYCLE (migration 338, CONTRACT roteiro-ciclo)
--------------------------------------------------------
A roteiro is born a `rascunho` and every edit is saved; it becomes `gerado` only through `gerar` (the atomic
`roteiro_gerar` RPC: status flip + lead link in ONE transaction; the funnel move follows and is reported, never
raised). A gerado roteiro keeps its imóveis fixed (no add / remove / reorder) but its date, time, observations and the
visit outcomes stay editable. Outcomes only exist on a gerado roteiro, which is also the only kind the counts see:
`consolidadas = realizada`, `perdidas = cancelada + nao_compareceu`, `neutras = reagendada + pendente`. A reagendada
visita is neutral — its new date lives in a NEW roteiro (`reagendar`).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub import negociacao_service
from app.modules.card_hub import roteiro_erros as erros
from app.modules.card_hub.roteiros_papeis import SEM_ATOR, Ator
from app.modules.card_hub.services import (
    _atendimentos_do_cliente,
    _t,
    ensure_cliente,
    resolve_atendimento_id,
)
from app.modules.imovel_hub.busca_service import canonical, enriquecer
from app.modules.imovel_hub.dados_service import ensure_imovel
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "roteiros"
VISITAS_TABLE = "visitas"

#: Mirrors the DB CHECK in `082`. Both exist on purpose: the schema protects the
#: API surface, the CHECK protects every other writer (a migration, a script, a
#: future job). Neither is redundant with the other.
STATUS_VALIDOS = ("pendente", "realizada", "cancelada", "nao_compareceu", "reagendada")
CANCELADA_POR = ("cliente", "proprietario", "corretor")
CANCELADA_MOTIVOS = ("cliente_desistiu", "imovel_indisponivel", "outro")

STATUS_RASCUNHO = "rascunho"
STATUS_GERADO = "gerado"

_ROTEIRO_FIELDS = (
    "id", "atendimento_id", "titulo", "data_visita", "created_at",
    # Migration 219 — the "visita aconteceu?" axis.
    "hora_visita", "feedback_status", "feedback_em",
    # Migration 338 — the lifecycle.
    "status", "gerado_em", "gerado_por", "reaberto_em", "reaberto_por", "criado_por", "updated_at",
)

#: Same sentence the request schema (`roteiro_schemas`) raises, so the 422 from
#: the body and the typed error from a direct service call read identically.
MSG_DATA_OBRIGATORIA = "Informe a data da visita."
_VISITA_FIELDS = (
    "id", "roteiro_id", "codigo", "ordem", "status",
    "observacao", "feedback_em", "created_at", "horario",
    # Migration 219. `nao_realizada_motivo` is VESTIGIAL since 338 (legacy, read-only): not returned.
    "realizada_em",
    # Migration 338 — the outcome vocabulary.
    "cancelada_por", "cancelada_motivo", "reagendada_para_visita_id", "resultado_em", "resultado_por",
    # Migration 104 — the proposta axis. Deliberately NOT folded into
    # `status`: see that migration's header and `registrar_proposta` below.
    "proposta_em", "proposta_por", "proposta_aceita_em", "proposta_aceita_por",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── reads ──────────────────────────────────────────────────────────────────

def listar(
    client: Any, org_id: UUID, cliente_id: UUID, *, ator: Optional[Ator] = None
) -> dict:
    """Every live roteiro across this person's atendimentos, newest first — DRAFTS INCLUDED (R1)."""
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
    items = _montar(client, org_id, roteiros, ator)
    return {"items": items, "total": len(items)}


def obter(
    client: Any, org_id: UUID, cliente_id: UUID, roteiro_id: UUID, *, ator: Optional[Ator] = None
) -> dict:
    return _montar(
        client, org_id, [_obter(client, org_id, cliente_id, roteiro_id)], ator
    )[0]


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


def _visitas_de(
    client: Any,
    org_id: UUID,
    roteiro_ids: list[str],
    *,
    incluir_removidos: bool = False,
) -> list[dict]:
    """Live visitas of these roteiros; `incluir_removidos` keeps the dead ones.

    The display path wants the live set. The one-accepted-proposta guard wants
    EVERYTHING — see `_recusar_segundo_aceite`.
    """
    return [
        v
        for v in table_reads.in_batched_rows(
            client, VISITAS_TABLE, org_id, "roteiro_id", roteiro_ids
        )
        if incluir_removidos or v.get("deleted_at") is None
    ]


def _montar(
    client: Any, org_id: UUID, roteiros: list[dict], ator: Optional[Ator] = None
) -> list[dict]:
    """Roteiros + their visitas + the imóvel behind each one (+ what THIS caller may do: `permissoes`).

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

    nomes = _nomes_de_usuarios(
        (ator or SEM_ATOR).core_client,
        {str(r[k]) for r in roteiros for k in ("gerado_por", "reaberto_por") if r.get(k)},
    )
    saida = []
    for r in roteiros:
        linhas = por_roteiro.get(str(r["id"]), [])
        linhas.sort(key=lambda v: (v.get("ordem") or 0, v.get("created_at") or ""))
        saida.append(
            {
                **{k: r.get(k) for k in _ROTEIRO_FIELDS},
                "hora_visita": _hhmm(r.get("hora_visita")),
                "gerado_por_nome": nomes.get(str(r.get("gerado_por"))),
                "reaberto_por_nome": nomes.get(str(r.get("reaberto_por"))),
                "visitas": [_visita_out(v, imoveis) for v in linhas],
                "contagem": _contagem(linhas),
                "permissoes": _permissoes(r, linhas, ator or SEM_ATOR),
            }
        )
    return saida


def _hhmm(valor: Any) -> Optional[str]:
    """A TIME column (`HH:MM:SS`) as the contract's `HH:MM`; `None` stays `None`."""
    return str(valor)[:5] if valor else None


def _nomes_de_usuarios(core_client: Any, ids: set[str]) -> dict[str, str]:
    """`{user_id: nome}` from `public.noctus_users` (the trusted row), one batched read; no client or no ids = `{}`
    (the roteiro then says `null`, it never invents a name)."""
    if core_client is None or not ids:
        return {}
    rows = core_client.table("noctus_users").select("id, nome").in_("id", sorted(ids)).execute().data or []
    return {str(r["id"]): r.get("nome") for r in rows if r.get("nome")}


def _contagem(visitas: list[dict]) -> dict:
    """The contabilização — ONE derivation (the imóvel view in migration 338 and `metricas_service` mirror it):
    `consolidadas = realizada`, `perdidas = cancelada + nao_compareceu`, `neutras = reagendada + pendente`.
    Five statuses, never a boolean: "hasn't happened yet" and "didn't happen" are different facts, and a
    REAGENDADA visita is neutral (its new date lives in a new roteiro)."""
    n = {st: sum(1 for v in visitas if v.get("status") == st) for st in STATUS_VALIDOS}
    return {
        "total": len(visitas),
        "pendentes": n["pendente"],
        "realizadas": n["realizada"],
        "canceladas": n["cancelada"],
        "nao_compareceu": n["nao_compareceu"],
        "reagendadas": n["reagendada"],
        "consolidadas": n["realizada"],
        "perdidas": n["cancelada"] + n["nao_compareceu"],
        "neutras": n["reagendada"] + n["pendente"],
    }


def _com_resultado(visitas: list[dict]) -> int:
    """Visitas that carry an outcome (anything but pendente) — what blocks a reopen and a delete."""
    return sum(1 for v in visitas if v.get("status") != "pendente")


def _msg_resultados(n: int) -> str:
    return f"Já tem {n} resultado{'s' if n != 1 else ''} registrado{'s' if n != 1 else ''}."


def _permissoes(roteiro: dict, visitas: list[dict], ator: Ator) -> dict:
    """What the CALLER may do on this roteiro. Computed by the server; the FE renders from it and never re-derives
    the rules (CONTRACT §2)."""
    gerado = roteiro.get("status") == STATUS_GERADO
    rascunho = roteiro.get("status") == STATUS_RASCUNHO
    motivo_gerar: Optional[str] = None
    if rascunho:
        if not visitas:
            motivo_gerar = erros.MSG_SEM_IMOVEIS
        elif not roteiro.get("data_visita"):
            motivo_gerar = erros.MSG_SEM_DATA
    resultados = _com_resultado(visitas)
    reabrir = False
    motivo_reabrir: Optional[str] = None
    if gerado:
        if not ator.pode_supervisionar:
            motivo_reabrir = erros.MSG_SEM_PERMISSAO_REABRIR
        elif resultados:
            motivo_reabrir = _msg_resultados(resultados)
        else:
            reabrir = True
    return {
        "editar_imoveis": rascunho,
        "gerar": rascunho and motivo_gerar is None,
        "motivo_gerar": motivo_gerar,
        "baixar_pdf": gerado,
        "reabrir": reabrir,
        "motivo_reabrir": motivo_reabrir,
    }


def _visita_out(row: dict, imoveis: dict[str, dict]) -> dict:
    out = {k: row.get(k) for k in _VISITA_FIELDS}
    out["horario"] = _hhmm(row.get("horario"))
    out["imovel"] = imoveis.get(canonical(str(row.get("codigo") or "")))
    return out


# ── writes ─────────────────────────────────────────────────────────────────

def criar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    imoveis: Optional[list[str]] = None,
    data_visita: Optional[date] = None,
    titulo: Optional[str] = None,
    atendimento_id: Optional[UUID] = None,
    usuario_id: Optional[Any] = None,
    hora_visita: Optional[time] = None,
    ator: Optional[Ator] = None,
) -> dict:
    """R2 — a DRAFT route and one visita per property, in the order given.

    Born `rascunho`: nothing is linked to the lead and the funil does NOT move here (it moves on `gerar`).
    `imoveis` may be empty and `data_visita` absent — the editor creates the draft on its first meaningful edit.
    Past dates are allowed (CONTRACT §11). `criado_por` = the caller.
    """
    ensure_cliente(client, org_id, cliente_id)
    alvo = resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)
    codigos = _validar_codigos(client, org_id, imoveis or [])

    roteiro_id = str(uuid4())
    agora = _now()
    _t(client, TABLE).insert(
        {
            "id": roteiro_id,
            "org_id": str(org_id),
            "atendimento_id": alvo,
            "titulo": (titulo or "").strip() or None,
            "data_visita": _data_iso(data_visita),
            "status": STATUS_RASCUNHO,
            "criado_por": str(usuario_id) if usuario_id else None,
            "atualizado_por": str(usuario_id) if usuario_id else None,
            "feedback_status": "pendente",
            "hora_visita": _hora(hora_visita),
            "created_at": agora,
            "updated_at": agora,
        }
    ).execute()

    if codigos:
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
                    "atualizado_por": str(usuario_id) if usuario_id else None,
                }
                for i, codigo in enumerate(codigos)
            ]
        ).execute()

    return obter(client, org_id, cliente_id, UUID(roteiro_id), ator=ator)


def _mover_funil(client: Any, org_id: UUID, atendimento_id: str, usuario_id: Any) -> dict:
    """`roteiro_criado` -> stage `visitas`, run by `gerar`. The roteiro is already generated, so a funnel failure is
    REPORTED (`motivo`), never raised over a good write."""
    from app.modules.pipeline.funil_eventos import mover_por_evento

    try:
        return mover_por_evento(client, org_id, atendimento_id, "roteiro_criado", usuario_id)
    except Exception:  # noqa: BLE001 - reported in the result, logged with trace
        logger.exception("funil: roteiro_criado failed for atendimento %s", atendimento_id)
        return {"moveu": False, "de": None, "para": None, "motivo": "erro_funil"}


def _hora(valor: Any) -> Optional[str]:
    """`time` (or its ISO string — the route hands over `model_dump(mode="json")`) -> `HH:MM:SS` for the TIME
    column; `None` clears it."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, str):
        valor = time.fromisoformat(valor)
    return valor.strftime("%H:%M:%S")


def _data_iso(valor: Any) -> Optional[str]:
    """ISO `YYYY-MM-DD` for the column, or `None` (a draft may have no date yet). Accepts a `date` or an ISO string;
    garbage is the typed 422."""
    if valor is None or valor == "":
        return None
    return _exigir_data(valor)


def _exigir_data(valor: Any) -> str:
    """ISO `YYYY-MM-DD` for the column, or the typed refusal. Accepts a `date`
    or an ISO string; anything else (None, '', garbage) is the same 422."""
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, str) and valor.strip():
        try:
            return date.fromisoformat(valor.strip()[:10]).isoformat()
        except ValueError:
            pass
    raise erros.roteiro_sem_data()


def _por(ator: Optional[Ator], usuario_id: Any = None) -> Optional[str]:
    """Who is acting, as the `atualizado_por` the event triggers (migration 338, `roteiro_eventos`) read."""
    quem = usuario_id or (ator.usuario_id if ator else None)
    return str(quem) if quem else None


def _tocar(client: Any, org_id: UUID, roteiro_id: Any, por: Optional[str] = None) -> None:
    """Every autosaved edit bumps `roteiros.updated_at` (the trigger covers a direct UPDATE of the row; an edit of a
    VISITA does not touch it, so it is written explicitly)."""
    _t(client, TABLE).update({"updated_at": _now(), "atualizado_por": por}).eq(
        "org_id", str(org_id)
    ).eq("id", str(roteiro_id)).execute()


def _exigir_rascunho(roteiro: dict) -> None:
    """The imóveis of a gerado roteiro are fixed: add / remove / reorder are 409 `roteiro_gerado`."""
    if roteiro.get("status") != STATUS_RASCUNHO:
        raise erros.roteiro_gerado()


def _exigir_gerado(roteiro: dict, acao: str = "registrar o resultado da visita") -> None:
    """Outcomes, proposta and PDF only exist on a gerado roteiro: 409 `roteiro_rascunho`."""
    if roteiro.get("status") != STATUS_GERADO:
        raise erros.roteiro_rascunho(acao)


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
    data_visita: Optional[date] = ...,
    hora_visita: Optional[time] = ...,
    ator: Optional[Ator] = None,
) -> dict:
    """R3 — `...` sentinels an unset field; only what the PATCH carried is written. Allowed in BOTH statuses (a gerado
    roteiro keeps its date, time and title editable). An explicit `data_visita=None` clears the date of a DRAFT; on a
    gerado roteiro it is 422 `roteiro_sem_data` — a generated route never loses its date."""
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)
    updates: dict = {}
    if titulo is not ...:
        updates["titulo"] = (titulo or "").strip() or None
    if data_visita is not ...:
        if data_visita in (None, "") and roteiro.get("status") == STATUS_GERADO:
            raise erros.roteiro_sem_data()
        updates["data_visita"] = _data_iso(data_visita)
    if hora_visita is not ...:
        updates["hora_visita"] = _hora(hora_visita)
    updates["updated_at"] = _now()
    updates["atualizado_por"] = _por(ator)
    _t(client, TABLE).update(updates).eq("org_id", str(org_id)).eq("id", str(roteiro_id)).execute()
    return obter(client, org_id, cliente_id, roteiro_id, ator=ator)


def remover(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    *,
    usuario_id: Optional[UUID] = None,
) -> None:
    """R4 — soft delete, per D3's reversibility bar. The visitas' own rows are left
    alone — undoing this is one UPDATE rather than a resurrection — and both
    the card read and `vw_imovel_visita_contagem` exclude them via the
    roteiro's `deleted_at`.

    A GERADO roteiro with any outcome is not deletable (409 `roteiro_gerado_com_resultados`): the outcomes are the
    data the counts are built from. Without outcomes it is (today's behaviour).

    An ACCEPTANCE on one of those visitas is the exception: it is withdrawn
    here rather than left dangling, because the deal it drives lives on
    another table that this delete would otherwise not touch. See
    `_desfazer_aceite_removido`.
    """
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)
    visitas = _visitas_de(client, org_id, [str(roteiro_id)])
    resultados = _com_resultado(visitas)
    if roteiro.get("status") == STATUS_GERADO and resultados:
        raise erros.RoteiroConflito(
            "roteiro_gerado_com_resultados",
            "Este roteiro já tem resultados registrados e não pode ser excluído.",
            {"quantidade": resultados},
        )
    atendimento_id = UUID(str(roteiro["atendimento_id"]))
    _desfazer_aceite_removido(client, org_id, atendimento_id, visitas, usuario_id)
    _t(client, TABLE).update({"deleted_at": _now(), "atualizado_por": _por(None, usuario_id)}).eq(
        "id", str(roteiro_id)
    ).execute()


def reordenar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_ids: list[UUID],
    *,
    ator: Optional[Ator] = None,
) -> dict:
    """R5 — rewrite `ordem` to the position of each id in `visita_ids` (409 `roteiro_gerado` on a gerado roteiro).

    The list must be the COMPLETE live set. A partial reorder that silently
    succeeded would leave two visitas sharing a position and the route in an
    order nobody chose — so a mismatch is a 400 naming both sides.
    """
    _exigir_rascunho(_obter(client, org_id, cliente_id, roteiro_id))
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
        _t(client, VISITAS_TABLE).update({"ordem": i, "atualizado_por": _por(ator)}).eq(
            "id", visita_id
        ).execute()
    _tocar(client, org_id, roteiro_id, _por(ator))
    return obter(client, org_id, cliente_id, roteiro_id, ator=ator)


def adicionar_visita(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    codigo: str,
    *,
    ator: Optional[Ator] = None,
) -> dict:
    """R6 — append one property to the end of an existing DRAFT route (409 `roteiro_gerado` otherwise); returns the
    full ROTEIRO (every autosave answers with it)."""
    _exigir_rascunho(_obter(client, org_id, cliente_id, roteiro_id))
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
        "atualizado_por": _por(ator),
    }
    _t(client, VISITAS_TABLE).insert(row).execute()
    _tocar(client, org_id, roteiro_id, _por(ator))
    return obter(client, org_id, cliente_id, roteiro_id, ator=ator)


# ── the lifecycle: gerar / reabrir / reagendar ─────────────────────────────

#: `roteiro_gerar` refusal codes -> the typed error.
_RECUSAS_GERAR = {
    "roteiro_ja_gerado": lambda: erros.RoteiroConflito("roteiro_ja_gerado", "Este roteiro já foi gerado."),
    "roteiro_sem_imoveis": lambda: erros.RoteiroInvalido("roteiro_sem_imoveis", erros.MSG_SEM_IMOVEIS),
    "roteiro_sem_data": erros.roteiro_sem_data,
}


def gerar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    *,
    usuario_id: Optional[Any] = None,
    ator: Optional[Ator] = None,
) -> dict:
    """R8 — draft -> gerado.

    ONE database transaction (`roteiro_gerar`, migration 338): the row lock, the guards, `status='gerado'` +
    `gerado_em/por`, and the lead link (`cliente_imovel_interesses`, origem `roteiro`, fills empty only) commit
    together or not at all. A refusal comes back as a code and is raised here as its typed error.

    The funil move (`roteiro_criado` -> `visitas`) follows the commit and is REPORTED under `funil`, never raised:
    it runs the stage gate and the pipeline movement, which are not SQL (a refusal is a return value by the
    funnel's own contract). The roteiro enters the feedback flow because `pendentes-feedback` lists gerado only.
    """
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)
    resp = client.rpc(
        "roteiro_gerar",
        {
            "p_org_id": str(org_id),
            "p_roteiro_id": str(roteiro_id),
            "p_user_id": str(usuario_id) if usuario_id else None,
        },
    ).execute()
    resultado = resp.data
    if isinstance(resultado, list):
        resultado = resultado[0] if resultado else None
    if not isinstance(resultado, dict):
        raise RuntimeError(f"roteiro_gerar devolveu um resultado inesperado: {resultado!r}")
    if resultado.get("status") != "ok":
        codigo = resultado.get("code")
        if codigo == "nao_encontrado":
            raise NotFoundError(TABLE, str(roteiro_id))
        fabrica = _RECUSAS_GERAR.get(codigo)
        if fabrica is None:
            raise RuntimeError(f"roteiro_gerar recusou com um código desconhecido: {codigo!r}")
        raise fabrica()

    saida = obter(client, org_id, cliente_id, roteiro_id, ator=ator)
    saida["funil"] = _mover_funil(client, org_id, str(roteiro["atendimento_id"]), usuario_id)
    return saida


def reabrir(
    client: Any,
    core_client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    *,
    ator: Optional[Ator] = None,
) -> dict:
    """R9 — gerado -> rascunho. Supervisors, owners and admins only, and only while NO visita has an outcome.

    Kept: the interesses `gerar` created (a lead link is not undone) and the funil stage. The user who generated it is
    told in-app (core's `public.notifications`, the platform's one in-app writer) unless they reopened it themselves.
    """
    ator = ator or SEM_ATOR
    if not ator.pode_supervisionar:
        raise erros.RoteiroSemPermissao("sem_permissao_reabrir", erros.MSG_SEM_PERMISSAO_REABRIR)
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)
    if roteiro.get("status") != STATUS_GERADO:
        raise erros.RoteiroConflito("roteiro_nao_gerado", "Este roteiro não está gerado.")
    resultados = _com_resultado(_visitas_de(client, org_id, [str(roteiro_id)]))
    if resultados:
        raise erros.RoteiroConflito(
            "roteiro_com_resultados", _msg_resultados(resultados), {"quantidade": resultados}
        )

    agora = _now()
    # Compare-and-set on the status: two concurrent reopens write once.
    _t(client, TABLE).update(
        {
            "status": STATUS_RASCUNHO,
            "reaberto_em": agora,
            "reaberto_por": ator.usuario_id,
            "atualizado_por": ator.usuario_id,
            "updated_at": agora,
        }
    ).eq("org_id", str(org_id)).eq("id", str(roteiro_id)).eq("status", STATUS_GERADO).execute()

    _avisar_reabertura(core_client, org_id, cliente_id, roteiro, ator)
    return obter(client, org_id, cliente_id, roteiro_id, ator=ator)


def _avisar_reabertura(
    core_client: Any, org_id: UUID, cliente_id: UUID, roteiro: dict, ator: Ator
) -> None:
    """In-app notice to whoever generated the roteiro, when that is somebody else. NEVER raises over a good reopen —
    the failure is logged at ERROR with its trace (the platform's `notify_org_admins` posture)."""
    gerado_por = roteiro.get("gerado_por")
    if not gerado_por or str(gerado_por) == str(ator.usuario_id):
        return
    try:
        from noctusai_lib.domain.notifications import operational_metadata, write_in_app

        titulo = (roteiro.get("titulo") or "").strip() or "Roteiro de visitas"
        write_in_app(
            core_client,
            user_ids=[gerado_por],
            kind="roteiro_reaberto",
            title="Roteiro reaberto como rascunho",
            message=f"{titulo} foi reaberto e voltou a ser um rascunho."[:160],
            metadata=operational_metadata(
                produto="social-wiring",
                link=f"/clientes/{cliente_id}",
                entidade={"tipo": "roteiro", "id": str(roteiro["id"])},
            ),
            org_id=org_id,
        )
    except Exception:  # noqa: BLE001 - a notice never fails the reopen
        logger.exception("roteiro %s reaberto, mas o aviso a %s falhou", roteiro.get("id"), gerado_por)


def reagendar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
    *,
    data_visita: Optional[date] = None,
    hora_visita: Optional[time] = None,
    usuario_id: Optional[Any] = None,
    ator: Optional[Ator] = None,
) -> dict:
    """R12 — the visita becomes `reagendada` (NEUTRAL in every count) and a NEW rascunho roteiro of the same
    atendimento is created with that one código (+ the date/time if given); `reagendada_para_visita_id` points at the
    new visita. Returns `{visita, novo_roteiro}`.

    Only a pendente visita of a gerado roteiro can be rescheduled. The new roteiro is written first: if the update of
    the old visita then fails the caller sees the error and an ordinary draft remains — never a reagendada visita that
    points at nothing.
    """
    atual = _obter_visita(client, org_id, cliente_id, roteiro_id, visita_id)
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)
    _exigir_gerado(roteiro, "reagendar uma visita")
    if atual.get("status") != "pendente":
        raise erros.RoteiroConflito(
            "visita_ja_tem_resultado", "Esta visita já tem um resultado registrado."
        )

    agora = _now()
    novo_id = str(uuid4())
    nova_visita_id = str(uuid4())
    _t(client, TABLE).insert(
        {
            "id": novo_id,
            "org_id": str(org_id),
            "atendimento_id": str(roteiro["atendimento_id"]),
            "titulo": None,
            "data_visita": _data_iso(data_visita),
            "status": STATUS_RASCUNHO,
            "criado_por": str(usuario_id) if usuario_id else None,
            "atualizado_por": str(usuario_id) if usuario_id else None,
            "feedback_status": "pendente",
            "hora_visita": _hora(hora_visita),
            "created_at": agora,
            "updated_at": agora,
        }
    ).execute()
    _t(client, VISITAS_TABLE).insert(
        {
            "id": nova_visita_id,
            "org_id": str(org_id),
            "roteiro_id": novo_id,
            "codigo": atual["codigo"],
            "ordem": 0,
            "status": "pendente",
            "created_at": agora,
            "atualizado_por": str(usuario_id) if usuario_id else None,
        }
    ).execute()

    updates = {
        "atualizado_por": str(usuario_id) if usuario_id else None,
        "status": "reagendada",
        "reagendada_para_visita_id": nova_visita_id,
        "resultado_em": agora,
        "resultado_por": str(usuario_id) if usuario_id else None,
        "realizada_em": None,
        "cancelada_por": None,
        "cancelada_motivo": None,
    }
    if not atual.get("feedback_em"):
        updates["feedback_em"] = agora
    _t(client, VISITAS_TABLE).update(updates).eq("org_id", str(org_id)).eq(
        "id", str(visita_id)
    ).eq("status", "pendente").execute()
    _tocar(client, org_id, roteiro_id, _por(ator, usuario_id))

    return {
        "visita": _visita_out({**atual, **updates}, enriquecer(client, org_id, [str(atual["codigo"])])),
        "novo_roteiro": obter(client, org_id, cliente_id, UUID(novo_id), ator=ator),
    }


# ── visita outcome (R11) ────────────────────────────────────────────────────

def atualizar_visita(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    visita_id: UUID,
    *,
    status: Optional[str] = ...,
    observacao: Optional[str] = ...,
    cancelada_por: Optional[str] = ...,
    cancelada_motivo: Optional[str] = ...,
    horario: Optional[time] = ...,
    usuario_id: Optional[Any] = None,
    ator: Optional[Ator] = None,
) -> dict:
    """R11 — the corretor's feedback on ONE visita; returns the full ROTEIRO. `...` sentinels an unset field.

    * `horario` (the visit's own time) is editable in BOTH statuses, like the roteiro's date and time;
    * an observation is allowed on a draft; any status other than `pendente` needs a GERADO roteiro (409
      `roteiro_rascunho`);
    * `cancelada` needs `cancelada_por` + `cancelada_motivo` (422 `cancelada_incompleta`) — a legacy cancelada with no
      `cancelada_por` must be completed by whatever edit touches it, exactly as the NOT VALID CHECK says;
    * `reagendada` is not set here (422): rescheduling creates the new roteiro (R12);
    * recording an outcome stamps `resultado_em/por` (`realizada` also `realizada_em`); setting it back to `pendente`
      clears the stamps. After ANY outcome the roteiro cannot be reopened.
    """
    atual = _obter_visita(client, org_id, cliente_id, roteiro_id, visita_id)
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)

    updates: dict = {}
    if observacao is not ...:
        updates["observacao"] = (observacao or "").strip() or None
    if horario is not ...:
        updates["horario"] = _hora(horario)

    novo_status = atual.get("status") if status is ... else status
    if status is not ...:
        if status not in STATUS_VALIDOS:
            raise ValidationError_(
                f"status must be one of {list(STATUS_VALIDOS)}, got {status!r}",
                field="status",
            )
        if status == "reagendada":
            raise erros.RoteiroInvalido(
                "reagendada_use_reagendar",
                "Para reagendar, use a ação de reagendar visita: ela cria o novo roteiro.",
            )
        if status != "pendente":
            _exigir_gerado(roteiro)

    por = atual.get("cancelada_por") if cancelada_por is ... else cancelada_por
    motivo = atual.get("cancelada_motivo") if cancelada_motivo is ... else cancelada_motivo
    if novo_status == "cancelada":
        if not por or not motivo:
            raise erros.cancelada_incompleta()
    elif cancelada_por not in (..., None) or cancelada_motivo not in (..., None):
        raise erros.RoteiroInvalido(
            "cancelada_sem_cancelamento",
            "Quem cancelou e o motivo só valem para uma visita cancelada.",
        )

    if status is not ... and status != atual.get("status"):
        agora = _now()
        updates["status"] = status
        # Stamped when the visit FIRST leaves 'pendente', never re-stamped: it is the honest "when did this happen"
        # the timeline derives its entry from, and a second stamp would move a past event forward in the sort.
        if status != "pendente" and not atual.get("feedback_em"):
            updates["feedback_em"] = agora
        if status == "pendente":
            updates["resultado_em"] = None
            updates["resultado_por"] = None
            updates["realizada_em"] = None
        else:
            updates["resultado_em"] = agora
            updates["resultado_por"] = str(usuario_id) if usuario_id else None
            updates["realizada_em"] = (
                (atual.get("realizada_em") or agora) if status == "realizada" else None
            )
        if atual.get("status") == "reagendada":
            updates["reagendada_para_visita_id"] = None
    if novo_status == "cancelada":
        updates["cancelada_por"] = por
        updates["cancelada_motivo"] = motivo
    elif atual.get("cancelada_por") or atual.get("cancelada_motivo"):
        updates["cancelada_por"] = None
        updates["cancelada_motivo"] = None

    if updates:
        updates["atualizado_por"] = _por(ator, usuario_id)
        _t(client, VISITAS_TABLE).update(updates).eq("org_id", str(org_id)).eq(
            "id", str(visita_id)
        ).execute()
        _tocar(client, org_id, roteiro_id, updates["atualizado_por"])
    return obter(client, org_id, cliente_id, roteiro_id, ator=ator)


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
    # R13: a proposta needs a visited, GERADO roteiro.
    _exigir_gerado(roteiro, "registrar uma proposta")
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
        # 🔴 EVERY REFUSAL HAPPENS BEFORE THE WRITE, AND THAT ORDERING IS THE
        # WHOLE GUARANTEE. `card_hub` has no transaction: each `.execute()` is
        # its own PostgREST request, so a guard that raises AFTER the visita
        # UPDATE cannot roll it back. Until this moved up, refusing a second
        # acceptance still recorded it — the operator saw a red toast while the
        # row said accepted, and the card rendered "este é o imóvel da
        # negociação" on a property the deal does not name. Two answers to
        # "what is being sold", which is exactly what migration 104's header
        # says this rule exists to prevent.
        #
        # So: decide first, write once. Anything that can refuse belongs above
        # this line.
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
        updates["proposta_aceita_em"] = _now()
        updates["proposta_aceita_por"] = str(usuario_id) if usuario_id else None

    if quer_desaceitar:
        updates["proposta_aceita_em"] = None
        updates["proposta_aceita_por"] = None

    if updates:
        _t(client, VISITAS_TABLE).update(updates).eq("id", str(visita_id)).execute()

    # 🔴 THE DEAL FOLLOWS THE ACCEPTANCE, in both directions, and says so.
    # Nothing here can refuse — every guard ran above, before the write. This
    # block only propagates a decision already taken.
    if updates.get("proposta_aceita_em"):
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


def _desfazer_aceite_removido(
    client: Any,
    org_id: UUID,
    atendimento_id: UUID,
    visitas: list[dict],
    usuario_id: Optional[UUID],
) -> None:
    """Deleting an accepted visita withdraws the acceptance WITH it.

    🔴 THE DEAL MUST NOT OUTLIVE ITS EVIDENCE. `registrar_proposta`'s explicit
    un-accept path already clears `atendimento_negociacao.imovel_codigo` when
    the deal still names this visita's imóvel. Deleting used to skip that, so
    the two paths disagreed and the silent one was delete: the contract would
    have named a property whose acceptance no longer existed anywhere — a
    stale answer with nothing left to check it against.

    Clearing is conditional on the deal STILL naming this código, exactly as
    the un-accept path is: if the operator has since pointed the negotiation
    somewhere else by hand, this removal has nothing to say about it.
    """
    aceitas = [v for v in visitas if v.get("proposta_aceita_em")]
    if not aceitas:
        return
    _t(client, VISITAS_TABLE).update(
        {"proposta_aceita_em": None, "proposta_aceita_por": None}
    ).in_("id", [str(v["id"]) for v in aceitas]).execute()

    atual_deal = negociacao_service.imovel_do_atendimento(
        client, org_id, atendimento_id
    )
    if not atual_deal:
        return
    if canonical(str(atual_deal)) in {canonical(str(v["codigo"])) for v in aceitas}:
        negociacao_service.definir_imovel_do_atendimento(
            client, org_id, atendimento_id, None, usuario_id=usuario_id
        )


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

    🔴 SOFT-DELETED ROTEIROS AND VISITAS COUNT HERE, AND THAT IS THE POINT.
    This guard used to skip them, so the rule was defeated by an ordinary
    sequence with no concurrency at all: accept on roteiro A, delete roteiro A
    (a stale route — routine), accept on roteiro B. Both acceptances stood,
    HTTP 200, no error, and the partial index this migration ships returned
    two rows for one atendimento. Whoever reads the accepted proposta to build
    the contract would get the wrong property half the time.

    `remover` / `remover_visita` now unwind an acceptance as they delete, so in
    normal operation a dead row carries none and this filter never fires. It
    stays as the backstop for rows deleted BEFORE that unwind existed: a
    lingering acceptance should refuse loudly, not be silently ignored.

    Read-then-write, so two concurrent accepts could in principle both pass.
    That is accepted deliberately: this is a single operator clicking a button
    on one card, the losing write is recoverable by un-accepting, and the
    alternative — an advisory lock or a trigger — would be machinery for a
    race nobody can produce. The FK'd `imovel_codigo` still holds the deal to
    exactly one property regardless.
    """
    roteiros = list(
        table_reads.in_batched_rows(
            client, TABLE, org_id, "atendimento_id", [str(atendimento_id)]
        )
    )
    if not roteiros:
        return
    for v in _visitas_de(
        client,
        org_id,
        [str(r["id"]) for r in roteiros],
        incluir_removidos=True,
    ):
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
    *,
    usuario_id: Optional[UUID] = None,
    ator: Optional[Ator] = None,
) -> dict:
    """R7 — soft-delete one visita of a DRAFT (409 `roteiro_gerado` otherwise) — withdrawing its acceptance if it
    carried one.

    See `_desfazer_aceite_removido`: the deal lives on another table, so a
    delete that ignored it would leave the negotiation naming a property whose
    acceptance no longer exists.
    """
    atual = _obter_visita(client, org_id, cliente_id, roteiro_id, visita_id)
    # `_obter_visita` already proved the roteiro belongs to this cliente; this
    # re-read is for its `atendimento_id`, which the visita row does not carry.
    roteiro = _obter(client, org_id, cliente_id, roteiro_id)
    _exigir_rascunho(roteiro)
    atendimento_id = UUID(str(roteiro["atendimento_id"]))
    _desfazer_aceite_removido(client, org_id, atendimento_id, [atual], usuario_id)
    _t(client, VISITAS_TABLE).update({"deleted_at": _now(), "atualizado_por": _por(ator, usuario_id)}).eq(
        "id", str(visita_id)
    ).execute()
    _tocar(client, org_id, roteiro_id, _por(ator, usuario_id))
    return obter(client, org_id, cliente_id, roteiro_id, ator=ator)


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
