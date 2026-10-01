"""The person page payload — `GET /api/clientes/{id}/resumo` (contract §4.5).

ONE payload for BOTH `/clientes/:id` and `/vendedores/:id` (owner D3): roles
overlap (a comprador can be a vendedor and vice versa), so the FE orders its
sections by `papeis` and the BE answers the same question for both routes.

Everything is derived in a fixed number of batched reads — the person's
atendimentos (titular + partes), their etapas, the junction códigos, the
roteiros count — never per atendimento.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.card_hub.compradores_service import _CLIENTE_RESUMO
from app.modules.card_hub.services import ensure_cliente
from app.modules.imovel_hub import atendimento_imoveis_service, interesses_service
from app.modules.imovel_hub import proprietarios_service
from app.services import table_reads

PAPEIS_ORDEM = ("lead", "comprador", "vendedor", "proprietario")


def _contar_vivas(client: Any, org_id: UUID, tabela: str, coluna: str, valor: str) -> int:
    return len(
        table_reads.paged_rows(
            client,
            tabela,
            org_id,
            eq_filters={coluna: valor},
            refine=lambda q: q.is_("deleted_at", "null"),
            select="id",
        )
    )


def resumo(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """§4.5. 404 `NOT_FOUND` for an unknown cliente (via `ensure_cliente`)."""
    ensure_cliente(client, org_id, cliente_id)
    cid = str(cliente_id)

    clientes = (
        table_reads.table(client, "clientes")
        .select(",".join(sorted({*_CLIENTE_RESUMO, "chave_canonica"})))
        .eq("org_id", str(org_id))
        .eq("id", cid)
        .limit(1)
        .execute()
    ).data or []
    cliente = clientes[0] if clientes else {"id": cid}

    titulares = table_reads.paged_rows(
        client,
        "atendimentos",
        org_id,
        eq_filters={"cliente_id": cid},
        select="id,titulo,status,arquivado,etapa_id,created_at",
    )
    partes = table_reads.paged_rows(
        client,
        "atendimento_partes",
        org_id,
        eq_filters={"cliente_id": cid},
        select="id,atendimento_id,lado,papel",
    )

    linhas: dict[str, dict] = {}
    for a in titulares:
        linhas[str(a["id"])] = {
            "row": a,
            "titular": True,
            "lado": "comprador",
            "papel": "comprador",
            "parte_id": None,
        }
    parte_ids = [str(p["atendimento_id"]) for p in partes if str(p["atendimento_id"]) not in linhas]
    extras = {
        str(a["id"]): a
        for a in table_reads.in_batched_rows(
            client, "atendimentos", org_id, "id", parte_ids,
            select="id,titulo,status,arquivado,etapa_id,created_at",
        )
    }
    for p in partes:
        aid = str(p["atendimento_id"])
        if aid in linhas or aid not in extras:
            continue  # the titular row wins; an orphan parte has nothing to show
        linhas[aid] = {
            "row": extras[aid],
            "titular": False,
            "lado": p.get("lado") or "comprador",
            "papel": p.get("papel") or "",
            "parte_id": str(p["id"]),
        }

    etapas = {
        str(e["id"]): e
        for e in table_reads.in_batched_rows(
            client, "pipeline_stages", org_id, "id",
            sorted({str(l["row"]["etapa_id"]) for l in linhas.values() if l["row"].get("etapa_id")}),
            select="id,label",
        )
    }
    imoveis_por_atendimento = atendimento_imoveis_service.codigos_por_atendimento(
        client, org_id, sorted(linhas)
    )

    atendimentos = []
    for aid, l in linhas.items():
        a = l["row"]
        etapa = etapas.get(str(a.get("etapa_id"))) if a.get("etapa_id") else None
        codigos = imoveis_por_atendimento.get(aid, [])
        atendimentos.append(
            {
                "id": aid,
                "titulo": a.get("titulo"),
                "etapa": {"id": str(etapa["id"]), "nome": etapa.get("label")} if etapa else None,
                "status": a.get("status"),
                "arquivado": bool(a.get("arquivado")),
                "titular": l["titular"],
                "lado": l["lado"],
                "papel": l["papel"],
                "parte_id": l["parte_id"],
                "imovel_pendente": not codigos,
                "imoveis": codigos,
                "created_at": a.get("created_at"),
            }
        )
    atendimentos.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)

    n_interesses = _contar_vivas(client, org_id, interesses_service.TABLE, "cliente_id", cid)
    n_propriedades = _contar_vivas(client, org_id, proprietarios_service.TABLE, "cliente_id", cid)
    roteiros = table_reads.in_batched_rows(
        client, "roteiros", org_id, "atendimento_id", sorted(linhas), select="id,atendimento_id"
    )
    touches = table_reads.paged_rows(
        client, "cliente_touches", org_id, eq_filters={"cliente_id": cid}, select="id"
    )

    papeis = set()
    if touches or titulares:
        papeis.add("lead")
    if titulares or any(l["lado"] == "comprador" for l in linhas.values()):
        papeis.add("comprador")
    if any(l["lado"] == "vendedor" for l in linhas.values()):
        papeis.add("vendedor")
    if n_propriedades:
        papeis.add("proprietario")

    return {
        "cliente": {k: cliente.get(k) for k in sorted({*_CLIENTE_RESUMO})},
        "papeis": [p for p in PAPEIS_ORDEM if p in papeis],
        "contatos": {
            "celular": cliente.get("celular"),
            "email": cliente.get("email"),
            "chave_canonica": cliente.get("chave_canonica"),
        },
        "atendimentos": atendimentos,
        "contagens": {
            "interesses": n_interesses,
            "propriedades": n_propriedades,
            "roteiros": len(roteiros),
            "atendimentos": len(atendimentos),
        },
    }


__all__ = ["PAPEIS_ORDEM", "resumo"]
