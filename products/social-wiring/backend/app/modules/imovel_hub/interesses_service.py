"""Interesses of a cliente — `cliente_imovel_interesses` (migration 182).

Contract `atendimento-partes-imoveis` §4.1. The table is the single source of
two surfaces: the person page's "Interesses" list and the imóvel page's
"Interessados" (`relacionamentos_service`/`imovel_relacionamentos_router`).

WRITE RULES
-----------
* One LIVE row per (cliente, código) — the partial unique index
  `uq_sw_cliente_imovel_interesses_vivo` is the backstop, this module is the
  message. A soft-deleted (cliente, código) is REVIVED by a manual add instead
  of inserting a second row.
* `origem` is a closed vocabulary. `lead` and `roteiro` are SYSTEM values: the
  HTTP surface refuses them (`ORIGENS_USUARIO`), `registrar_de_lead` is the one
  writer of `lead`, and `roteiro` is reserved (no writer in v1).
* Removing an interesse is a soft delete and never touches the lead rows or
  `atendimento_imoveis` (§4.1).

🔴 THE LEAD WRITER NEVER RESURRECTS A REMOVAL
`registrar_de_lead` is called by every ingest path AND by the 6-hourly clientes
sweep (`reconcile`). If it revived a row an operator had deliberately removed,
the removal would silently undo itself every six hours. So it skips a
(cliente, código) that has ANY row, live or soft-deleted — a removed interesse
stays removed until a human re-adds it.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import ConflictError, NotFoundError

from app.modules.card_hub.services import ensure_cliente
from app.modules.imovel_hub import _relacionamentos as rel
from app.modules.imovel_hub import busca_service
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "cliente_imovel_interesses"

ORIGENS = ("lead", "manual", "campanha", "roteiro", "permuta")
#: What a person may type through the API (§4.1) — `lead`/`roteiro` are system-only.
ORIGENS_USUARIO = ("manual", "campanha", "permuta")


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _vivas(query):
    return query.is_("deleted_at", "null")


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """`{items, total}` — live rows, `created_at DESC`, imóvel enriched in ONE
    batched read per source (never N+1)."""
    ensure_cliente(client, org_id, cliente_id)
    rows = table_reads.paged_rows(
        client,
        TABLE,
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        refine=_vivas,
    )
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    imoveis = busca_service.enriquecer(client, org_id, [r["codigo"] for r in rows])
    itens = [_saida(r, imoveis.get(str(r["codigo"]))) for r in rows]
    return {"items": itens, "total": len(itens)}


def _saida(row: dict, imovel: Optional[dict]) -> dict:
    return rel.linha_pessoa(
        row,
        imovel,
        lead_id=str(row["lead_id"]) if row.get("lead_id") else None,
        meta_ads_lead_id=(
            str(row["meta_ads_lead_id"]) if row.get("meta_ads_lead_id") else None
        ),
    )


def _linhas_do_par(client: Any, org_id: UUID, cliente_id: UUID, codigo: str) -> list[dict]:
    return list(
        (
            _t(client, TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("cliente_id", str(cliente_id))
            .eq("codigo", codigo)
            .execute()
        ).data
        or []
    )


def adicionar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    codigo: str,
    origem: str = "manual",
    usuario_id: Optional[Any] = None,
) -> dict:
    """Add (or revive) an interesse. 404 unknown imóvel / 409 already listed."""
    if origem not in ORIGENS_USUARIO:
        # The router's Literal already 422s this; the service refuses too so a
        # second caller cannot write a system-only value through it.
        raise ValueError(f"origem inválida para interesse manual: {origem!r}")
    ensure_cliente(client, org_id, cliente_id)
    canonico = rel.exigir_imovel_cadastrado(client, org_id, codigo)

    existentes = _linhas_do_par(client, org_id, cliente_id, canonico)
    if any(r.get("deleted_at") is None for r in existentes):
        raise ConflictError("Este imóvel já está na lista de interesses.", resource=TABLE)

    por_usuario = str(usuario_id) if usuario_id else None
    if existentes:
        # Revive the soft-deleted row: it keeps its id (and any lead link) so
        # the history of "this person once asked about this imóvel" survives.
        alvo = max(existentes, key=lambda r: str(r.get("created_at") or ""))
        patch = {"deleted_at": None, "origem": origem, "created_by": por_usuario}
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "id", str(alvo["id"])
        ).execute()
        row = {**alvo, **patch}
    else:
        row = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "codigo": canonico,
            "origem": origem,
            "lead_id": None,
            "meta_ads_lead_id": None,
            "created_by": por_usuario,
            "created_at": rel.agora(),
            "deleted_at": None,
        }
        _t(client, TABLE).insert(row).execute()

    imovel = busca_service.enriquecer(client, org_id, [canonico]).get(canonico)
    return _saida(row, imovel)


def remover(client: Any, org_id: UUID, cliente_id: UUID, interesse_id: UUID) -> None:
    """Soft delete. 404 when it is not THIS cliente's live row."""
    ensure_cliente(client, org_id, cliente_id)
    rows = (
        _vivas(
            _t(client, TABLE)
            .select("id")
            .eq("org_id", str(org_id))
            .eq("cliente_id", str(cliente_id))
            .eq("id", str(interesse_id))
        )
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("interesse", str(interesse_id))
    _t(client, TABLE).update({"deleted_at": rel.agora()}).eq(
        "org_id", str(org_id)
    ).eq("id", str(interesse_id)).execute()


def registrar_de_lead(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    codigo: str,
    *,
    lead_id: Optional[str] = None,
    meta_ads_lead_id: Optional[str] = None,
    criado_em: Optional[str] = None,
) -> bool:
    """The `origem="lead"` writer (§3.5 `vincular_lead`). Idempotent; returns
    whether a row was written. See the module docstring for why a removed
    interesse is never resurrected. The código MUST already be in the registry
    (`vincular_lead` registers it first) — no FK-violation 500 is acceptable."""
    canonico = busca_service.canonical(codigo or "")
    if not canonico:
        return False
    if _linhas_do_par(client, org_id, cliente_id, canonico):
        return False
    _t(client, TABLE).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "codigo": canonico,
            "origem": "lead",
            "lead_id": str(lead_id) if lead_id else None,
            "meta_ads_lead_id": str(meta_ads_lead_id) if meta_ads_lead_id else None,
            "created_by": None,
            "created_at": criado_em or rel.agora(),
            "deleted_at": None,
        }
    ).execute()
    return True


# ── imóvel side: "Interessados" (§4.3) ─────────────────────────────────


def _telefone(cliente: dict) -> Optional[str]:
    """`celular` else the phone behind `chave_canonica` (E.164 as stored)."""
    if cliente.get("celular"):
        return cliente["celular"]
    chave = cliente.get("chave_canonica") or ""
    return chave if chave and "@" not in chave else None


def _chaves_pagina(rows: list[dict], coluna: str) -> list[str]:
    return [str(r[coluna]) for r in rows if r.get(coluna)]


def interessados(
    client: Any, org_id: UUID, codigo: str, *, limite: int = 50, offset: int = 0
) -> dict:
    """§4.3 — every cliente ever interested in `codigo`, with contact, origem,
    last interaction and whether they have an open atendimento.

    `total` is the full live-interesse count; the page is cut AFTER sorting by
    `ultima_interacao_em DESC NULLS LAST, interesse_created_at DESC` (the sort
    key needs every row's last touch, so the read is not DB-paged). Every
    lookup is one batched read (clientes, touches, leads, Meta leads,
    atendimentos, partes) — never per-row.
    """
    canonico = rel.exigir_imovel_cadastrado(client, org_id, codigo)
    rows = table_reads.paged_rows(
        client, TABLE, org_id, eq_filters={"codigo": canonico}, refine=_vivas
    )
    total = len(rows)
    if not rows:
        return {"items": [], "total": 0}

    cliente_ids = sorted({str(r["cliente_id"]) for r in rows})
    clientes = {
        str(c["id"]): c
        for c in table_reads.in_batched_rows(
            client, "clientes", org_id, "id", cliente_ids,
            select="id,nome,nome_oficial,celular,email,chave_canonica",
        )
    }
    ultima: dict[str, str] = {}
    for t in table_reads.in_batched_rows(
        client, "cliente_touches", org_id, "cliente_id", cliente_ids,
        select="id,cliente_id,ocorreu_em",
    ):
        quando = str(t.get("ocorreu_em") or "")
        if quando and quando > ultima.get(str(t["cliente_id"]), ""):
            ultima[str(t["cliente_id"])] = quando

    leads = {
        str(l["id"]): l
        for l in table_reads.in_batched_rows(
            client, "leads", org_id, "id", _chaves_pagina(rows, "lead_id"),
            select="id,created_at",
        )
    }
    metas = {
        str(m["id"]): m
        for m in table_reads.in_batched_rows(
            client, "meta_ads_leads", org_id, "id", _chaves_pagina(rows, "meta_ads_lead_id"),
            select="id,created_time,created_at",
        )
    }

    abertos = _atendimento_aberto_por_cliente(client, org_id, cliente_ids)

    itens = []
    for r in rows:
        cid = str(r["cliente_id"])
        c = clientes.get(cid) or {}
        if r.get("lead_id"):
            lead_criado = (leads.get(str(r["lead_id"])) or {}).get("created_at")
        elif r.get("meta_ads_lead_id"):
            meta = metas.get(str(r["meta_ads_lead_id"])) or {}
            lead_criado = meta.get("created_time") or meta.get("created_at")
        else:
            lead_criado = None
        aberto = abertos.get(cid)
        itens.append(
            {
                "interesse_id": str(r["id"]),
                "cliente_id": cid,
                "nome": c.get("nome_oficial") or c.get("nome") or "",
                "telefone": _telefone(c),
                "email": c.get("email"),
                "origem": r.get("origem"),
                "interesse_created_at": r.get("created_at"),
                "lead_created_at": lead_criado,
                "ultima_interacao_em": ultima.get(cid),
                "tem_atendimento_aberto": aberto is not None,
                "atendimento_aberto_id": aberto,
            }
        )

    # DESC on both keys with NULLS LAST for the first: stable-sort twice
    # (secondary key first), then push the nulls of the primary to the end.
    itens.sort(key=lambda i: str(i["interesse_created_at"] or ""), reverse=True)
    itens.sort(key=lambda i: str(i["ultima_interacao_em"] or ""), reverse=True)
    itens.sort(key=lambda i: i["ultima_interacao_em"] is None)
    offset = max(0, int(offset))
    limite = max(1, min(int(limite), 200))
    return {"items": itens[offset : offset + limite], "total": total}


def _atendimento_aberto_por_cliente(
    client: Any, org_id: UUID, cliente_ids: list[str]
) -> dict[str, str]:
    """`{cliente_id: atendimento_id}` of an atendimento the cliente is on
    (titular OR parte) that is not archived and not collapsed (§4.3). The
    newest wins when there are several."""
    por_cliente: dict[str, list[str]] = {cid: [] for cid in cliente_ids}
    for p in table_reads.in_batched_rows(
        client, "atendimento_partes", org_id, "cliente_id", cliente_ids,
        select="id,atendimento_id,cliente_id",
    ):
        por_cliente[str(p["cliente_id"])].append(str(p["atendimento_id"]))
    titulares = table_reads.in_batched_rows(
        client, "atendimentos", org_id, "cliente_id", cliente_ids,
        select="id,cliente_id,arquivado,substituida_por,created_at",
    )
    for a in titulares:
        por_cliente[str(a["cliente_id"])].append(str(a["id"]))

    todos = sorted({aid for lista in por_cliente.values() for aid in lista})
    estado = {
        str(a["id"]): a
        for a in table_reads.in_batched_rows(
            client, "atendimentos", org_id, "id", todos,
            select="id,arquivado,substituida_por,created_at",
        )
    }
    saida: dict[str, str] = {}
    for cid, ids in por_cliente.items():
        abertos = [
            estado[i]
            for i in set(ids)
            if i in estado
            and not estado[i].get("arquivado")
            and estado[i].get("substituida_por") is None
        ]
        if abertos:
            saida[cid] = str(
                max(abertos, key=lambda a: str(a.get("created_at") or ""))["id"]
            )
    return saida


__all__ = [
    "interessados",
    "ORIGENS",
    "ORIGENS_USUARIO",
    "TABLE",
    "adicionar",
    "listar",
    "registrar_de_lead",
    "remover",
]
