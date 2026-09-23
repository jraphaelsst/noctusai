"""Produtos e Serviços — the catalogue orçamento items are priced from (roadmap R6).

An org's catalogue is seeded ONCE, on its first read, with the owner's
examples — the same lazy-seed shape as the pipeline stages
(`app/pipelines.py::garantir_etapas_padrao`): no org-creation hook in another
product's schema, and idempotent under concurrent first reads (upsert
`ignore_duplicates` on the `(org_id, secao, nome)` unique index, migration
020). "Has none at all" includes inactive rows — an org that deactivated or
deleted the examples made a choice, and re-seeding would undo it.

Hours feed the orçamento's live estimated cost/margin; `formato` feeds the
pautas an accepted orçamento generates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from noctusai_lib.integrations.persistence.table_reads import paged_rows

from app.services import quadro_comum as qc
from app.services.regras import RegraViolada

logger = logging.getLogger(__name__)

__all__ = [
    "CATALOGO_PADRAO",
    "ProdutoPadrao",
    "garantir_catalogo",
    "listar",
    "criar",
    "atualizar",
    "remover",
]

_SELECT = (
    "id, secao, nome, descricao, preco_base, unidade, horas_estimadas, formato, ativo, ordem"
)


@dataclass(frozen=True)
class ProdutoPadrao:
    secao: str
    nome: str
    preco_base: float
    unidade: str
    horas_estimadas: float
    formato: str | None = None
    descricao: str | None = None


#: The owner's examples (roadmap R6) + the four everyday content formats.
#: Hours are starting points an agency refines from its own timesheets.
CATALOGO_PADRAO: tuple[ProdutoPadrao, ...] = (
    ProdutoPadrao("gestao_conta", "Gestão de conteúdo", 500.0, "mês", 8.0,
                  descricao="Planejamento editorial, calendário e publicação."),
    ProdutoPadrao("gestao_conta", "Gestão de DMs", 500.0, "mês", 10.0,
                  descricao="Atendimento e resposta às mensagens diretas."),
    ProdutoPadrao("criacao_conteudo", "Post feed", 80.0, "post", 2.0, "feed"),
    ProdutoPadrao("criacao_conteudo", "Carrossel", 150.0, "post", 3.5, "carrossel"),
    ProdutoPadrao("criacao_conteudo", "Reels", 250.0, "vídeo", 4.0, "reels"),
    ProdutoPadrao("criacao_conteudo", "Stories", 40.0, "story", 0.5, "story"),
)


def _dto(row: dict) -> dict:
    return {
        "id": row["id"],
        "secao": row.get("secao"),
        "nome": row.get("nome"),
        "descricao": row.get("descricao"),
        "preco_base": float(row.get("preco_base") or 0),
        "unidade": row.get("unidade") or "unidade",
        "horas_estimadas": float(row.get("horas_estimadas") or 0),
        "formato": row.get("formato"),
        "ativo": bool(row.get("ativo")),
        "ordem": int(row.get("ordem") or 0),
    }


def garantir_catalogo(db: Any, org_id: str) -> None:
    existentes = db.table("produto_servico").select("id").eq("org_id", org_id).limit(1).execute()
    if existentes.data:
        return
    linhas = [
        {
            "org_id": org_id,
            "secao": p.secao,
            "nome": p.nome,
            "descricao": p.descricao,
            "preco_base": p.preco_base,
            "unidade": p.unidade,
            "horas_estimadas": p.horas_estimadas,
            "formato": p.formato,
            "ativo": True,
            "ordem": ordem,
        }
        for ordem, p in enumerate(CATALOGO_PADRAO)
    ]
    db.table("produto_servico").upsert(
        linhas, on_conflict="org_id,secao,nome", ignore_duplicates=True
    ).execute()
    logger.info("catalogo padrao criado org=%s n=%d", org_id, len(linhas))


def listar(db: Any, org_id: str, *, secao: str | None = None, ativo: bool | None = None) -> list[dict]:
    garantir_catalogo(db, org_id)
    filtros: dict[str, Any] = {}
    if secao:
        filtros["secao"] = secao
    if ativo is not None:
        filtros["ativo"] = ativo
    linhas = paged_rows(db, "produto_servico", org_id, eq_filters=filtros or None, select=_SELECT)
    linhas.sort(key=lambda r: (str(r.get("secao")), int(r.get("ordem") or 0), str(r.get("nome"))))
    return [_dto(r) for r in linhas]


def _exigir_nome_livre(db: Any, org_id: str, secao: str, nome: str, *, exceto: str | None = None) -> None:
    iguais = (
        db.table("produto_servico").select("id").eq("org_id", org_id).eq("secao", secao)
        .eq("nome", nome).execute().data or []
    )
    if any(str(r["id"]) != str(exceto) for r in iguais):
        raise RegraViolada(
            409, "produto_duplicado", f"Já existe \"{nome}\" nesta seção do catálogo.",
        )


def criar(db: Any, org_id: str, dados: dict) -> dict:
    dados = {**dados, "nome": dados["nome"].strip()}
    _exigir_nome_livre(db, org_id, dados["secao"], dados["nome"])
    criado = db.table("produto_servico").insert({**dados, "org_id": org_id}).execute().data or []
    if not criado:
        raise RuntimeError("insert de produto_servico não retornou a linha criada")
    return _dto(criado[0])


def atualizar(db: Any, org_id: str, produto_id: str, dados: dict) -> dict:
    if not dados:
        raise RegraViolada(422, "sem_campos", "Nenhum campo para atualizar.")
    atual = qc.carregar(db, "produto_servico", org_id, produto_id, select=_SELECT,
                        rotulo="produto/serviço")
    if "nome" in dados and dados["nome"] is not None:
        dados["nome"] = dados["nome"].strip()
    if "nome" in dados or "secao" in dados:
        _exigir_nome_livre(
            db, org_id, dados.get("secao") or atual["secao"], dados.get("nome") or atual["nome"],
            exceto=produto_id,
        )
    linhas = (
        db.table("produto_servico").update(dados).eq("id", produto_id).eq("org_id", org_id)
        .execute().data or []
    )
    if not linhas:
        raise RuntimeError("update de produto_servico não retornou a linha")
    return _dto({**atual, **linhas[0]})


def remover(db: Any, org_id: str, produto_id: str) -> dict:
    """Hard delete — unless an orçamento item references it, then deactivate.

    A referenced product is part of proposals already sent; deleting it would
    null the link on those items (`ON DELETE SET NULL`) and lose where their
    hours came from.
    """
    qc.carregar(db, "produto_servico", org_id, produto_id, select="id", rotulo="produto/serviço")
    referenciado = (
        db.table("orcamento_item").select("id").eq("org_id", org_id)
        .eq("produto_servico_id", produto_id).limit(1).execute().data or []
    )
    if referenciado:
        db.table("produto_servico").update({"ativo": False}).eq("id", produto_id).eq(
            "org_id", org_id
        ).execute()
        return {"id": produto_id, "removido": False, "desativado": True}
    db.table("produto_servico").delete().eq("id", produto_id).eq("org_id", org_id).execute()
    return {"id": produto_id, "removido": True, "desativado": False}
