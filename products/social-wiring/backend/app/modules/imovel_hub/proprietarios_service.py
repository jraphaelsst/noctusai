"""Registered owners of an imóvel — `imovel_proprietarios` (migration 183).

Contract `atendimento-partes-imoveis` §4.2. Feeds the person page "Imóveis que
possui", the roteiro PDF's "proprietário" (`por_codigos`) and permuta intros.
An owner is a PF (`cliente_id`) XOR a PJ (`empresa_id`); one LIVE row per
(imóvel, owner); `origem` ∈ manual | matricula | atendimento.

WHO WRITES WHAT
---------------
* `manual`        — a human, through the HTTP surface. The ONLY origem a human
                    may remove (§4.2: derived rows ⇒ 409 `PROPRIEDADE_DERIVADA`).
* `atendimento`   — migration 183 backfilled historical vendedor partes ×
                    negociação imóvel; `reconcile_de_atendimentos` keeps that
                    true going forward (called from the clientes sweep).
* `matricula`     — `backfill_matricula` below: the CURRENT owners of an
                    imóvel as its matrícula says, matched to `clientes` /
                    `empresas` by CPF/CNPJ. Python, not SQL (migration 183's
                    header): the CPF normalisation is the matrícula service's
                    own and re-implementing it in SQL would fork it.

MATRÍCULA BACKFILL — how "current owner" is derived
---------------------------------------------------
For each imóvel with a CONCLUDED matrícula extraction (newest per código), the
adquirentes of the LAST ownership-transferring act (highest `ordem`, natureza ∈
the seed's `NATUREZAS_TRANSFERENCIA` — deliberately the WIDE set, not
`titulo_service`'s narrower "sold for consideration" one: an heir who acquired
by partilha IS the owner). Each adquirente's CPF/CNPJ is resolved to ONE cliente
or empresa:

1. the extraction's own `matricula_qualificacoes` row when it is `vinculado`
   (that pipeline already did the imóvel-scoped tie-break for 2+ clientes that
   share a CPF — never re-decided here);
2. else the org's cliente carrying that normalised CPF, only when EXACTLY one
   does (`qualificacao_service._clientes_por_cpf`, the same normalisation);
3. a 14-digit document → the org's empresa with that CNPJ.

Ambiguous or unmatched owners are COUNTED in the report, never guessed. A pair
that already has ANY row — live or soft-deleted — is left alone, so the backfill
is idempotent AND never resurrects a human's removal. The report carries counts
only: no name, CPF or CNPJ leaves this module (LGPD).

RUNNING IT (the tech-lead's one-liner)
--------------------------------------
    cd products/social-wiring/backend
    python -m app.modules.imovel_hub.proprietarios_service backfill-matricula \\
        --org <ORG_UUID> --dry-run          # counts only, writes nothing
    python -m app.modules.imovel_hub.proprietarios_service backfill-matricula \\
        --org <ORG_UUID>                    # applies; safe to re-run

`run_backfill_matricula` is the same entry for an in-process caller.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.documents import NATUREZAS_TRANSFERENCIA
from noctusai_lib.primitives.exceptions import AppException, ConflictError, NotFoundError

from app.modules.card_hub.services import ensure_cliente
from app.modules.imovel_hub import _relacionamentos as rel
from app.modules.imovel_hub import busca_service, vinculo_legal
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "imovel_proprietarios"
EMPRESAS_TABLE = "empresas"
CLIENTES_TABLE = "clientes"

ORIGEM_MANUAL = "manual"
ORIGEM_MATRICULA = "matricula"
ORIGEM_ATENDIMENTO = "atendimento"


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _vivas(query):
    return query.is_("deleted_at", "null")


def _digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _cnpj_chave(valor: Any) -> str:
    """CNPJs may be alphanumeric (migration 167) — keep letters, uppercase."""
    return re.sub(r"[^0-9A-Za-z]", "", str(valor or "")).upper()


# ── owner lookup ───────────────────────────────────────────────────────


def _exigir_empresa(client: Any, org_id: UUID, empresa_id: UUID) -> dict:
    rows = (
        _t(client, EMPRESAS_TABLE)
        .select("id,razao_social,nome_fantasia,cnpj")
        .eq("org_id", str(org_id))
        .eq("id", str(empresa_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("empresas", str(empresa_id))
    return rows[0]


def _coluna_dono(cliente_id: Optional[UUID], empresa_id: Optional[UUID]) -> tuple[str, str]:
    if (cliente_id is None) == (empresa_id is None):
        raise ValueError("informe exatamente um de cliente_id / empresa_id")
    return ("cliente_id", str(cliente_id)) if cliente_id else ("empresa_id", str(empresa_id))


# ── person-side reads / writes ─────────────────────────────────────────


def listar_da_pessoa(
    client: Any,
    org_id: UUID,
    *,
    cliente_id: Optional[UUID] = None,
    empresa_id: Optional[UUID] = None,
) -> dict:
    """§4.2 `GET …/propriedades` — `{items: [ImovelLinhaPessoa], total}`."""
    coluna, valor = _coluna_dono(cliente_id, empresa_id)
    if cliente_id:
        ensure_cliente(client, org_id, cliente_id)
    else:
        _exigir_empresa(client, org_id, empresa_id)  # type: ignore[arg-type]
    rows = table_reads.paged_rows(
        client, TABLE, org_id, eq_filters={coluna: valor}, refine=_vivas
    )
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    imoveis = busca_service.enriquecer(client, org_id, [r["codigo"] for r in rows])
    itens = [rel.linha_pessoa(r, imoveis.get(str(r["codigo"]))) for r in rows]
    return {"items": itens, "total": len(itens)}


def _linhas_do_par(client: Any, org_id: UUID, codigo: str, coluna: str, valor: str) -> list[dict]:
    return list(
        (
            _t(client, TABLE)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("codigo", codigo)
            .eq(coluna, valor)
            .execute()
        ).data
        or []
    )


def adicionar(
    client: Any,
    org_id: UUID,
    *,
    codigo: str,
    cliente_id: Optional[UUID] = None,
    empresa_id: Optional[UUID] = None,
    usuario_id: Optional[Any] = None,
) -> dict:
    """§4.2 `POST` — origem `manual`; revives a soft-deleted pair."""
    coluna, valor = _coluna_dono(cliente_id, empresa_id)
    if cliente_id:
        ensure_cliente(client, org_id, cliente_id)
    else:
        _exigir_empresa(client, org_id, empresa_id)  # type: ignore[arg-type]
    canonico = rel.exigir_imovel_cadastrado(client, org_id, codigo)

    existentes = _linhas_do_par(client, org_id, canonico, coluna, valor)
    if any(r.get("deleted_at") is None for r in existentes):
        raise ConflictError("Este imóvel já consta como propriedade.", resource=TABLE)

    por_usuario = str(usuario_id) if usuario_id else None
    if existentes:
        alvo = max(existentes, key=lambda r: str(r.get("created_at") or ""))
        patch = {"deleted_at": None, "origem": ORIGEM_MANUAL, "created_by": por_usuario}
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "id", str(alvo["id"])
        ).execute()
        row = {**alvo, **patch}
    else:
        row = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "codigo": canonico,
            "cliente_id": str(cliente_id) if cliente_id else None,
            "empresa_id": str(empresa_id) if empresa_id else None,
            "origem": ORIGEM_MANUAL,
            "created_by": por_usuario,
            "created_at": rel.agora(),
            "deleted_at": None,
        }
        _t(client, TABLE).insert(row).execute()
    imovel = busca_service.enriquecer(client, org_id, [canonico]).get(canonico)
    return rel.linha_pessoa(row, imovel)


def remover(
    client: Any,
    org_id: UUID,
    *,
    propriedade_id: UUID,
    cliente_id: Optional[UUID] = None,
    empresa_id: Optional[UUID] = None,
) -> None:
    """§4.2 `DELETE` — soft; only `origem="manual"` (derived ⇒ 409)."""
    coluna, valor = _coluna_dono(cliente_id, empresa_id)
    rows = (
        _vivas(
            _t(client, TABLE)
            .select("id,origem")
            .eq("org_id", str(org_id))
            .eq(coluna, valor)
            .eq("id", str(propriedade_id))
        )
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("propriedade", str(propriedade_id))
    if rows[0].get("origem") != ORIGEM_MANUAL:
        raise AppException(
            code="PROPRIEDADE_DERIVADA",
            message=(
                "Esta propriedade foi registrada automaticamente. "
                "Corrija a matrícula/negociação de origem."
            ),
            status_code=409,
        )
    _t(client, TABLE).update({"deleted_at": rel.agora()}).eq(
        "org_id", str(org_id)
    ).eq("id", str(propriedade_id)).execute()


# ── imóvel-side reads ──────────────────────────────────────────────────


def _donos_resolvidos(client: Any, org_id: UUID, rows: list[dict]) -> tuple[dict, dict]:
    clientes = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(
            client,
            CLIENTES_TABLE,
            org_id,
            "id",
            [str(r["cliente_id"]) for r in rows if r.get("cliente_id")],
            select="id,nome,nome_oficial,cpf,celular,email",
        )
    }
    empresas = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(
            client,
            EMPRESAS_TABLE,
            org_id,
            "id",
            [str(r["empresa_id"]) for r in rows if r.get("empresa_id")],
            select="id,razao_social,nome_fantasia,cnpj",
        )
    }
    return clientes, empresas


def _nome_dono(row: dict, clientes: dict, empresas: dict) -> tuple[str, str, Optional[str]]:
    """`(tipo_pessoa, nome, documento_digits)` of one proprietário row."""
    if row.get("cliente_id"):
        c = clientes.get(str(row["cliente_id"])) or {}
        return "PF", (c.get("nome_oficial") or c.get("nome") or ""), _digitos(c.get("cpf")) or None
    e = empresas.get(str(row.get("empresa_id"))) or {}
    return (
        "PJ",
        (e.get("razao_social") or e.get("nome_fantasia") or ""),
        _cnpj_chave(e.get("cnpj")) or None,
    )


def _chave_dono(r: dict) -> str:
    return f"c:{r['cliente_id']}" if r.get("cliente_id") else f"e:{r.get('empresa_id')}"


def _donos_do_imovel(client: Any, org_id: UUID, canonico: str) -> list[dict]:
    """Live owner rows of the PROPERTY `canonico` names: its own, plus — for a
    Vista código linked to a manual imóvel — the manual one's, deduped by
    person (own row wins) and labelled `fonte_codigo` (`vinculo_legal`)."""
    vistos: set[str] = set()
    saida: list[dict] = []
    for fonte in vinculo_legal.codigos_leitura(client, org_id, canonico):
        rows = table_reads.paged_rows(
            client, TABLE, org_id, eq_filters={"codigo": fonte}, refine=_vivas
        )
        rows.sort(key=lambda r: str(r.get("created_at") or ""))
        for r in rows:
            chave = _chave_dono(r)
            if chave in vistos:
                continue
            vistos.add(chave)
            saida.append({**r, "fonte_codigo": fonte})
    return saida


def do_imovel(client: Any, org_id: UUID, codigo: str) -> dict:
    """§4.2 `GET /api/imoveis/{codigo}/proprietarios`."""
    canonico = rel.exigir_imovel_cadastrado(client, org_id, codigo)
    rows = _donos_do_imovel(client, org_id, canonico)
    clientes, empresas = _donos_resolvidos(client, org_id, rows)
    itens = []
    for r in rows:
        tipo, nome, documento = _nome_dono(r, clientes, empresas)
        c = clientes.get(str(r.get("cliente_id"))) or {}
        itens.append(
            {
                "id": str(r["id"]),
                "tipo_pessoa": tipo,
                "cliente_id": str(r["cliente_id"]) if r.get("cliente_id") else None,
                "empresa_id": str(r["empresa_id"]) if r.get("empresa_id") else None,
                "nome": nome,
                "documento": documento,
                "celular": c.get("celular") if r.get("cliente_id") else None,
                "email": c.get("email") if r.get("cliente_id") else None,
                "origem": r.get("origem"),
                "fonte_codigo": r.get("fonte_codigo", canonico),
                "created_at": r.get("created_at"),
            }
        )
    return {"items": itens, "total": len(itens)}


def por_codigos(
    client: Any, org_id: UUID, codigos: list[str]
) -> dict[str, list[dict]]:
    """`{codigo_canonical: [{nome, documento, tipo_pessoa}]}` — the roteiro
    PDF's proprietário source (§4.2). Batched (one read per source), canonical
    keys; a código with no owner is simply absent from the map."""
    unicos = sorted({busca_service.canonical(c) for c in codigos if c})
    if not unicos:
        return {}
    manuais = vinculo_legal.manuais_por_vista(client, org_id, unicos)
    buscar = sorted(set(unicos) | set(manuais.values()))
    rows = [
        r
        for r in table_reads.in_batched_rows(
            client, TABLE, org_id, "codigo", buscar, order_col="id"
        )
        if r.get("deleted_at") is None
    ]
    rows.sort(key=lambda r: str(r.get("created_at") or ""))
    clientes, empresas = _donos_resolvidos(client, org_id, rows)
    saida: dict[str, list[dict]] = {}
    for r in rows:
        tipo, nome, documento = _nome_dono(r, clientes, empresas)
        saida.setdefault(str(r["codigo"]), []).append(
            {"nome": nome, "documento": documento, "tipo_pessoa": tipo}
        )
    # A linked Vista código also lists the manual record's owners (deduped
    # by person, own first); the manual código keeps its own list untouched.
    for vista, manual in manuais.items():
        ja = {_chave_dono(r) for r in rows if str(r["codigo"]) == vista}
        extras = [
            {"nome": n, "documento": d, "tipo_pessoa": t}
            for r in rows
            if str(r["codigo"]) == manual and _chave_dono(r) not in ja
            for t, n, d in [_nome_dono(r, clientes, empresas)]
        ]
        if extras:
            saida[vista] = saida.get(vista, []) + extras
    return saida


# ── derived writers ────────────────────────────────────────────────────


def _inserir_derivado(
    client: Any,
    org_id: UUID,
    *,
    codigo: str,
    coluna: str,
    valor: str,
    origem: str,
    existentes: set[tuple[str, str, str]],
    criado_em: Any = None,
) -> bool:
    chave = (codigo, coluna, valor)
    if chave in existentes:
        return False
    _t(client, TABLE).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "codigo": codigo,
            "cliente_id": valor if coluna == "cliente_id" else None,
            "empresa_id": valor if coluna == "empresa_id" else None,
            "origem": origem,
            "created_by": None,
            "created_at": criado_em or rel.agora(),
            "deleted_at": None,
        }
    ).execute()
    existentes.add(chave)
    return True


def _pares_existentes(client: Any, org_id: UUID) -> set[tuple[str, str, str]]:
    """Every (código, coluna, dono) with ANY row, live or soft-deleted."""
    pares: set[tuple[str, str, str]] = set()
    for r in table_reads.paged_rows(
        client, TABLE, org_id, select="id,codigo,cliente_id,empresa_id"
    ):
        if r.get("cliente_id"):
            pares.add((str(r["codigo"]), "cliente_id", str(r["cliente_id"])))
        if r.get("empresa_id"):
            pares.add((str(r["codigo"]), "empresa_id", str(r["empresa_id"])))
    return pares


def reconcile_de_atendimentos(client: Any, org_id: UUID) -> dict:
    """`origem="atendimento"` going forward: every VENDEDOR parte (PF) of an
    atendimento × that atendimento's negociação imóvel. Mirrors migration 183's
    backfill so it stays true after the migration ran. Idempotent; a pair that
    has any row (a human removal included) is left alone. Called by the
    clientes sweep."""
    negociacoes = {
        str(r["atendimento_id"]): busca_service.canonical(r["imovel_codigo"])
        for r in table_reads.paged_rows(
            client,
            "atendimento_negociacao",
            org_id,
            select="atendimento_id,imovel_codigo",
            order_col="atendimento_id",
            id_key="atendimento_id",
            refine=lambda q: q.not_.is_("imovel_codigo", "null"),
        )
        if (r.get("imovel_codigo") or "").strip()
    }
    relatorio = {"criados": 0}
    if not negociacoes:
        return relatorio
    partes = [
        p
        for p in table_reads.paged_rows(
            client,
            "atendimento_partes",
            org_id,
            select="id,atendimento_id,cliente_id,empresa_id,lado,created_at",
            eq_filters={"lado": "vendedor"},
        )
        if str(p["atendimento_id"]) in negociacoes
    ]
    if not partes:
        return relatorio
    registrados = {
        str(r["codigo_canonical"])
        for r in table_reads.in_batched_rows(
            client,
            busca_service.REGISTRY_TABLE,
            org_id,
            "codigo_canonical",
            sorted(set(negociacoes.values())),
            select="codigo_canonical",
            order_col="codigo_canonical",
        )
    }
    existentes = _pares_existentes(client, org_id)
    for p in sorted(partes, key=lambda x: str(x.get("created_at") or "")):
        codigo = negociacoes[str(p["atendimento_id"])]
        if codigo not in registrados:
            continue
        for coluna in ("cliente_id", "empresa_id"):
            if p.get(coluna):
                if _inserir_derivado(
                    client,
                    org_id,
                    codigo=codigo,
                    coluna=coluna,
                    valor=str(p[coluna]),
                    origem=ORIGEM_ATENDIMENTO,
                    existentes=existentes,
                    criado_em=p.get("created_at"),
                ):
                    relatorio["criados"] += 1
    return relatorio


# ── matrícula backfill ─────────────────────────────────────────────────


def _clientes_por_cpf(
    client: Any, org_id: UUID, chaves: list[str]
) -> dict[str, list[str]]:
    # The matrícula service's own normalisation + lookup (contract §4.2: "same
    # normalization the matrícula service owns"). Imported lazily: that module
    # imports card_hub, and this one must stay import-light for the routers.
    from app.modules.matriculas.qualificacao_service import _clientes_por_cpf as _impl

    return _impl(client, org_id, chaves)


def run_backfill_matricula(
    client: Any, org_id: UUID, *, dry_run: bool = False
) -> dict:
    """Backfill `origem="matricula"` owners. Idempotent; counts only.

    Returns `{extracoes, imoveis_com_transferencia, sem_transferencia,
    adquirentes, vinculados_cliente, vinculados_empresa, sem_correspondencia,
    ambiguos, sem_registry, ja_existentes, criados, dry_run}`.
    """
    relatorio = {
        "extracoes": 0,
        "imoveis_com_transferencia": 0,
        "sem_transferencia": 0,
        "adquirentes": 0,
        "vinculados_cliente": 0,
        "vinculados_empresa": 0,
        "sem_correspondencia": 0,
        "ambiguos": 0,
        "sem_registry": 0,
        "ja_existentes": 0,
        "criados": 0,
        "dry_run": dry_run,
    }

    # Newest concluded extraction per código.
    por_codigo: dict[str, dict] = {}
    for e in table_reads.paged_rows(
        client,
        "matricula_extracoes",
        org_id,
        select="id,codigo,created_at,status",
        eq_filters={"status": "concluida"},
        refine=lambda q: q.not_.is_("codigo", "null"),
    ):
        codigo = busca_service.canonical(e["codigo"] or "")
        if not codigo:
            continue
        atual = por_codigo.get(codigo)
        if atual is None or str(e.get("created_at") or "") > str(atual.get("created_at") or ""):
            por_codigo[codigo] = e
    relatorio["extracoes"] = len(por_codigo)
    if not por_codigo:
        return relatorio

    extracao_ids = [str(e["id"]) for e in por_codigo.values()]
    ordem_do_ato = {
        str(a["id"]): (a.get("ordem") or 0, a.get("kind"))
        for a in table_reads.in_batched_rows(
            client, "matricula_atos", org_id, "extracao_id", extracao_ids,
            select="id,extracao_id,ordem,kind",
        )
    }
    detalhes_por_extracao: dict[str, list[dict]] = {}
    for d in table_reads.in_batched_rows(
        client, "matricula_ato_detalhes", org_id, "extracao_id", extracao_ids,
        select="id,extracao_id,ato_id,natureza,adquirentes",
    ):
        detalhes_por_extracao.setdefault(str(d["extracao_id"]), []).append(d)

    vinculadas: dict[tuple[str, str], str] = {}
    for q in table_reads.in_batched_rows(
        client, "matricula_qualificacoes", org_id, "extracao_id", extracao_ids,
        select="id,extracao_id,cpf_cnpj_normalizado,cliente_id,vinculo_status",
    ):
        if q.get("vinculo_status") == "vinculado" and q.get("cliente_id"):
            vinculadas[(str(q["extracao_id"]), str(q["cpf_cnpj_normalizado"]))] = str(
                q["cliente_id"]
            )

    por_cpf = _clientes_por_cpf(
        client,
        org_id,
        [
            (adq or {}).get("cpf_cnpj")
            for detalhes in detalhes_por_extracao.values()
            for d in detalhes
            for adq in (d.get("adquirentes") or [])
        ],
    )
    empresas_por_cnpj: dict[str, list[str]] = {}
    for e in table_reads.paged_rows(client, EMPRESAS_TABLE, org_id, select="id,cnpj"):
        chave = _cnpj_chave(e.get("cnpj"))
        if chave:
            empresas_por_cnpj.setdefault(chave, []).append(str(e["id"]))

    registrados = {
        str(r["codigo_canonical"])
        for r in table_reads.in_batched_rows(
            client,
            busca_service.REGISTRY_TABLE,
            org_id,
            "codigo_canonical",
            sorted(por_codigo),
            select="codigo_canonical",
            order_col="codigo_canonical",
        )
    }
    existentes = _pares_existentes(client, org_id)

    for codigo, extracao in sorted(por_codigo.items()):
        eid = str(extracao["id"])
        transferencias = [
            d
            for d in detalhes_por_extracao.get(eid, [])
            if d.get("natureza") in NATUREZAS_TRANSFERENCIA
            and ordem_do_ato.get(str(d["ato_id"]), (0, "abertura"))[1] != "abertura"
        ]
        if not transferencias:
            relatorio["sem_transferencia"] += 1
            continue
        ultima = max(transferencias, key=lambda d: ordem_do_ato[str(d["ato_id"])][0])
        relatorio["imoveis_com_transferencia"] += 1
        if codigo not in registrados:
            relatorio["sem_registry"] += 1
            continue

        for adq in ultima.get("adquirentes") or []:
            documento = (adq or {}).get("cpf_cnpj")
            digitos = _digitos(documento)
            chave_cnpj = _cnpj_chave(documento)
            if not digitos and not chave_cnpj:
                continue
            relatorio["adquirentes"] += 1

            coluna = dono = None
            if len(digitos) == 11:
                dono = vinculadas.get((eid, digitos))
                if dono is None:
                    candidatos = por_cpf.get(digitos) or []
                    if len(candidatos) == 1:
                        dono = str(candidatos[0])
                    elif len(candidatos) > 1:
                        relatorio["ambiguos"] += 1
                        continue
                coluna = "cliente_id"
            elif len(chave_cnpj) == 14:
                candidatos = empresas_por_cnpj.get(chave_cnpj) or []
                if len(candidatos) == 1:
                    dono, coluna = candidatos[0], "empresa_id"
                elif len(candidatos) > 1:
                    relatorio["ambiguos"] += 1
                    continue
            if dono is None or coluna is None:
                relatorio["sem_correspondencia"] += 1
                continue

            if (codigo, coluna, dono) in existentes:
                relatorio["ja_existentes"] += 1
                continue
            relatorio["vinculados_cliente" if coluna == "cliente_id" else "vinculados_empresa"] += 1
            relatorio["criados"] += 1
            if dry_run:
                existentes.add((codigo, coluna, dono))
                continue
            _inserir_derivado(
                client,
                org_id,
                codigo=codigo,
                coluna=coluna,
                valor=dono,
                origem=ORIGEM_MATRICULA,
                existentes=existentes,
            )
    logger.info("proprietarios.backfill_matricula org=%s %s", org_id, relatorio)
    return relatorio


# ── CLI ────────────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.modules.imovel_hub.proprietarios_service",
        description="Backfill imovel_proprietarios (contract atendimento-partes-imoveis §4.2).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    mat = sub.add_parser(
        "backfill-matricula",
        help="origem='matricula': current owners per matrícula, matched by CPF/CNPJ",
    )
    mat.add_argument("--org", required=True, help="org UUID")
    mat.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    args = parser.parse_args(argv)

    from app.dependencies import get_scoped_admin_client

    org_id = UUID(args.org)
    resultado = run_backfill_matricula(
        get_scoped_admin_client(), org_id, dry_run=args.dry_run
    )
    print(json.dumps(resultado, indent=2, sort_keys=True))
    return 0


__all__ = [
    "TABLE",
    "adicionar",
    "do_imovel",
    "listar_da_pessoa",
    "main",
    "por_codigos",
    "reconcile_de_atendimentos",
    "remover",
    "run_backfill_matricula",
]

if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
