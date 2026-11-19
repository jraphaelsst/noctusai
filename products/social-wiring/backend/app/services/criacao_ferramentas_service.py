"""Diretor de Criacao read tools (`criacao-pipeline-contract.md` section 4/6, slice S7).

`POST /api/criacao/ferramentas/{nome}` -- the agents product calls these back during a creation turn. READ-ONLY
over the org's CoreStudio data. Every tool takes `(client, org_id, args)`; the org is the TOKEN's (never a payload
field), every org-owned read is `.eq("org_id", ...)`, and a `marca_id` that is not the org's is a 404.

What a tool does not have it says so: an empty brain is REPORTED (`vazio`), a missing source returns an empty list
plus a `motivo`, performance with no per-post store says `disponivel: false` -- nothing is fabricated.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.agent_tools import AgentTool
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.primitives.accents import fold_accents
from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)

CRIACAO_TOOLS_SCOPE = "social-wiring:criacao-tools"
CRIACAO_TOOLS_ISSUER = "agents"

MAX_LIMITE = 20
_PAGE = 500
_STOP = frozenset({"de", "da", "do", "das", "dos", "a", "o", "e", "em", "um", "uma", "para", "com", "que", "no", "na"})

Formato = Literal["reels", "carrossel", "stories", "post"]
Objetivo = Literal["alcance", "autoridade", "conexao", "venda"]


# ── args (strict) ─────────────────────────────────────────────────────────────────────────────────────────

class MarcaArgs(StrictHttpModel):
    marca_id: UUID


class CerebrosArgs(MarcaArgs):
    tipos: Optional[list[str]] = Field(default=None, max_length=20)


class EstruturasBuscarArgs(MarcaArgs):
    formato: Formato
    objetivo: Optional[Objetivo] = None
    texto: Optional[str] = Field(default=None, max_length=500)
    limite: int = Field(default=10, ge=1, le=MAX_LIMITE)


class EstruturaDetalheArgs(StrictHttpModel):
    codigo: int = Field(ge=1)


class PesquisasArgs(MarcaArgs):
    tema: Optional[str] = Field(default=None, max_length=200)
    limite: int = Field(default=20, ge=1, le=50)


class ViraisArgs(MarcaArgs):
    limite: int = Field(default=10, ge=1, le=MAX_LIMITE)


class DesempenhoArgs(MarcaArgs):
    janela_dias: int = Field(default=30, ge=1, le=365)


class VozAmostrasArgs(MarcaArgs):
    n: int = Field(default=5, ge=1, le=MAX_LIMITE)


class TreinamentosArgs(MarcaArgs):
    pass


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────────────

def _marca(client: Any, org_id: Any, marca_id: Any) -> str:
    """The marca's id when it belongs to the token's org; 404 otherwise (never leaks another org's marca)."""
    mid = str(marca_id)
    rows = client.table("marcas").select("id").eq("id", mid).eq("org_id", str(org_id)).execute().data
    if not rows:
        raise AppException("marca_nao_encontrada", "Marca não encontrada.", status_code=404)
    return mid


def _tokens(texto: Optional[str]) -> list[str]:
    base = re.sub(r"[^a-z0-9 ]", " ", fold_accents(texto or "").casefold())
    return [t for t in base.split() if len(t) > 2 and t not in _STOP]


def _pontos(tokens: list[str], alvo: str) -> int:
    palco = re.sub(r"[^a-z0-9 ]", " ", fold_accents(alvo or "").casefold())
    return sum(1 for t in tokens if t in palco)


def _paginar(consulta) -> list[dict[str, Any]]:
    return list(iter_paged_rows(lambda a, b: consulta().range(a, b).execute().data, page_size=_PAGE, label="criacao tool"))


def _bloco(b: dict[str, Any], tipos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tipo = tipos.get(str(b.get("tipo_id"))) or {}
    nome_tipo = tipo.get("nome") or ""
    return {
        "ordem": b.get("ordem"), "tipo": nome_tipo, "eh_cta": nome_tipo.casefold().startswith("cta"),
        "nome": b.get("nome"), "tempo": b.get("tempo"),
        # a block with no instruction of its own shows its type's reference instruction
        "instrucao": b.get("instrucao") or tipo.get("instrucao_referencia"),
        "nota": b.get("nota"), "repeticoes": b.get("repeticoes") or 1,
    }


def _estruturas_completas(client: Any, estruturas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach typed blocks + the profile handle to `estruturas` (a platform-wide library: no org column)."""
    ids = [str(e["id"]) for e in estruturas]
    blocos: dict[str, list[dict[str, Any]]] = {}
    for lote in batched(ids):
        for b in client.table("cs_estrutura_blocos").select(
            "estrutura_id,ordem,tipo_id,nome,tempo,instrucao,nota,repeticoes").in_("estrutura_id", lote).execute().data or []:
            blocos.setdefault(str(b["estrutura_id"]), []).append(b)
    tipo_ids = sorted({str(b["tipo_id"]) for bs in blocos.values() for b in bs if b.get("tipo_id")})
    tipos: dict[str, dict[str, Any]] = {}
    for lote in batched(tipo_ids):
        for t in client.table("cs_estrutura_tipos_bloco").select("id,nome,instrucao_referencia").in_("id", lote).execute().data or []:
            tipos[str(t["id"])] = t
    perfil_ids = sorted({str(e["perfil_id"]) for e in estruturas if e.get("perfil_id")})
    handles: dict[str, str] = {}
    for lote in batched(perfil_ids):
        for p in client.table("cs_perfis_monitorados").select("id,handle").in_("id", lote).execute().data or []:
            handles[str(p["id"])] = p.get("handle") or ""
    out = []
    for e in estruturas:
        bs = sorted(blocos.get(str(e["id"]), []), key=lambda x: x.get("ordem") or 0)
        out.append({
            "codigo": e["codigo"], "formato": e.get("formato"), "objetivos": list(e.get("objetivos") or []),
            "formula_headline": e.get("formula_headline"), "perfil": handles.get(str(e.get("perfil_id")) or "") or None,
            "blocos": [_bloco(b, tipos) for b in bs],
        })
    return out


# ── tools ─────────────────────────────────────────────────────────────────────────────────────────────────

def contexto_marca(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _marca(client, org_id, args["marca_id"])
    org = str(org_id)
    perfil = (client.table("cs_marca_perfil").select("bio,nichos,profissoes,apresentacao_magnetica,ctas")
              .eq("marca_id", mid).eq("org_id", org).execute().data or [{}])[0]
    kit = (client.table("mc_brand_kits").select("name,persona,design_system,brand_book,tokens,default_lang")
           .eq("marca_id", mid).eq("org_id", org).order("created_at", desc=True).limit(1).execute().data or [None])[0]
    memorias = (client.table("cs_memorias").select("texto,created_at").eq("marca_id", mid).eq("org_id", org)
                .order("created_at").execute().data or [])
    return {
        "marca_id": mid,
        "perfil": {
            "bio": perfil.get("bio") or "", "apresentacao_magnetica": perfil.get("apresentacao_magnetica") or "",
            "ctas": perfil.get("ctas") or "", "nichos": list(perfil.get("nichos") or []),
            "profissoes": list(perfil.get("profissoes") or []),
        },
        "brand_kit": kit,
        "memorias": [m["texto"] for m in memorias],
    }


def cerebros(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _marca(client, org_id, args["marca_id"])
    rows = (client.table("cs_brains")
            .select("id,name,kind,template_slug,content,content_version,synthesis_status,synthesized_at")
            .eq("marca_id", mid).eq("org_id", str(org_id)).execute().data or [])
    tipos = args.get("tipos")
    if tipos:
        quer = {t.casefold() for t in tipos}
        rows = [r for r in rows if (r.get("template_slug") or "").casefold() in quer or (r.get("kind") or "").casefold() in quer]
    itens = [{
        "id": str(r["id"]), "nome": r["name"], "tipo": r.get("template_slug") or r.get("kind"),
        "conteudo": r.get("content") or "", "vazio": not (r.get("content") or "").strip(),
        "versao": r.get("content_version"), "sintetizado_em": r.get("synthesized_at"),
        "status_sintese": r.get("synthesis_status"),
    } for r in rows]
    return {"cerebros": itens, "vazios": [i["nome"] for i in itens if i["vazio"]]}


def estruturas_buscar(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _marca(client, org_id, args["marca_id"])
    formato, objetivo, limite = args["formato"], args.get("objetivo"), args["limite"]
    candidatas = _paginar(lambda: client.table("cs_estruturas")
                          .select("id,codigo,perfil_id,formato,objetivos,formula_headline")
                          .eq("status", "ativa").eq("formato", formato).order("id"))
    if objetivo:
        candidatas = [e for e in candidatas if objetivo in (e.get("objetivos") or [])]
    # the brand's selected profiles first (same org-scoped allow-list the chat pool uses)
    refs = (client.table("cs_biblioteca_referencias").select("modo,perfil_id").eq("marca_id", mid)
            .eq("org_id", str(org_id)).execute().data or [])
    preferidos = {str(r["perfil_id"]) for r in refs if r.get("modo") == "perfil" and r.get("perfil_id")}
    tokens = _tokens(args.get("texto"))
    # NOC-REMEDIATE[retrieval-ranking]: ranked by plain text match on the headline formula + brand-profile boost;
    # S10 replaces this with integrations/retrieval top-k over the typed blocks -- 2026-11-19
    ordenadas = sorted(
        candidatas,
        key=lambda e: (-_pontos(tokens, e.get("formula_headline") or ""),
                       0 if str(e.get("perfil_id")) in preferidos else 1, int(e["codigo"])),
    )[:limite]
    return {"estruturas": _estruturas_completas(client, ordenadas), "total_candidatas": len(candidatas),
            "ranking": "texto_simples"}


def estrutura_detalhe(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    rows = (client.table("cs_estruturas").select("id,codigo,perfil_id,formato,objetivos,formula_headline")
            .eq("codigo", args["codigo"]).eq("status", "ativa").execute().data or [])
    if not rows:
        raise AppException("estrutura_nao_encontrada", "Estrutura não encontrada.", status_code=404)
    return _estruturas_completas(client, rows[:1])[0]


def pesquisas(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _marca(client, org_id, args["marca_id"])
    rows = (client.table("cs_research_items").select("variable_slug,content,source_ref,plays,created_at")
            .eq("marca_id", mid).eq("org_id", str(org_id)).eq("status", "approved")
            .order("created_at", desc=True).limit(500).execute().data or [])
    tokens = _tokens(args.get("tema"))
    if tokens:
        rows = [r for r in rows if _pontos(tokens, f"{r.get('variable_slug') or ''} {r.get('content') or ''}")]
    itens = [{
        "variavel": r["variable_slug"], "conteudo": r["content"],
        "url": (r.get("source_ref") or {}).get("url") if isinstance(r.get("source_ref"), dict) else None,
        "plays": r.get("plays"),
    } for r in rows[: args["limite"]]]
    return {"pesquisas": itens}


def virais(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _marca(client, org_id, args["marca_id"])
    org = str(org_id)
    refs = (client.table("cs_biblioteca_referencias").select("modo,perfil_id,viral_id").eq("marca_id", mid)
            .eq("org_id", org).execute().data or [])
    perfis = [str(r["perfil_id"]) for r in refs if r.get("modo") == "perfil" and r.get("perfil_id")]
    videos = [str(r["viral_id"]) for r in refs if r.get("modo") == "video" and r.get("viral_id")]
    cols = "id,codigo,perfil_id,permalink,media_product_type,publicado_em,likes,comments,views,duracao_s,score_viral,e_viral,gancho,blueprint,gatilho"
    achados: dict[str, dict[str, Any]] = {}
    for lote in batched(perfis):
        for v in client.table("cs_virais").select(cols).eq("org_id", org).eq("e_viral", True).in_("perfil_id", lote).execute().data or []:
            achados[str(v["id"])] = v
    for lote in batched(videos):
        for v in client.table("cs_virais").select(cols).eq("org_id", org).in_("id", lote).execute().data or []:
            achados[str(v["id"])] = v
    ordenados = sorted(achados.values(), key=lambda v: -(float(v.get("score_viral") or 0)))[: args["limite"]]
    return {"virais": [{
        "codigo": v["codigo"], "permalink": v.get("permalink"), "tipo": v.get("media_product_type"),
        "publicado_em": v.get("publicado_em"), "gancho": v.get("gancho"), "blueprint": v.get("blueprint"),
        "gatilho": v.get("gatilho"), "score_viral": v.get("score_viral"),
        "metricas": {"likes": v.get("likes"), "comments": v.get("comments"), "views": v.get("views"),
                     "duracao_s": v.get("duracao_s")},
    } for v in ordenados]}


def desempenho(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _marca(client, org_id, args["marca_id"])
    org = str(org_id)
    desde = (datetime.now(timezone.utc) - timedelta(days=args["janela_dias"])).isoformat()
    posts = (client.table("cs_posts").select("titulo,formato,postado_em,permalink")
             .eq("marca_id", mid).eq("org_id", org).gte("postado_em", desde).order("postado_em", desc=True)
             .limit(100).execute().data or [])
    snaps = (client.table("ig_metric_snapshots").select("captured_at,followers_count,reach,profile_views")
             .eq("org_id", org).gte("captured_at", desde).order("captured_at").limit(500).execute().data or [])
    conta = None
    if snaps:
        a, z = snaps[0], snaps[-1]
        conta = {"inicio": a.get("captured_at"), "fim": z.get("captured_at"), "seguidores_inicio": a.get("followers_count"),
                 "seguidores_fim": z.get("followers_count"),
                 "alcance_total": sum(s.get("reach") or 0 for s in snaps), "amostras": len(snaps)}
    return {
        "janela_dias": args["janela_dias"],
        "posts_publicados": [{"titulo": p["titulo"], "formato": p.get("formato"), "postado_em": p.get("postado_em"),
                              "permalink": p.get("permalink")} for p in posts],
        "conta": conta,
        # no per-post metric store exists today: said, never invented
        "metricas_por_post": {"disponivel": False, "motivo": "sem_tabela_de_metricas_por_post"},
        "avisos": [] if snaps else ["sem_snapshots_da_conta_na_janela"],
    }


def voz_amostras(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _marca(client, org_id, args["marca_id"])
    # the creator's own voice = completed transcriptions bound to the marca (contexto_tipo 'marca')
    rows = (client.table("transcricoes").select("texto,duracao_s,concluido_em").eq("org_id", str(org_id))
            .eq("contexto_tipo", "marca").eq("contexto_ref", mid).eq("status", "concluida")
            .order("concluido_em", desc=True).limit(args["n"]).execute().data or [])
    amostras = []
    for r in rows:
        texto = (r.get("texto") or "").strip()
        if not texto:
            continue
        dur = float(r.get("duracao_s") or 0)
        palavras = len(texto.split())
        amostras.append({"trecho": texto[:1500], "palavras": palavras,
                         "wpm": round(palavras / (dur / 60), 1) if dur > 0 else None})
    if not amostras:
        return {"amostras": [], "motivo": "sem_transcricoes_da_marca"}
    return {"amostras": amostras}


def treinamentos(client: Any, org_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    _marca(client, org_id, args["marca_id"])
    rows = (client.table("cs_treinamentos").select("ordem,titulo,descricao,video_url").eq("ativo", True)
            .order("ordem").execute().data or [])
    return {"treinamentos": rows}


REGISTRY: dict[str, AgentTool] = {
    "contexto_marca": AgentTool(MarcaArgs, contexto_marca),
    "cerebros": AgentTool(CerebrosArgs, cerebros),
    "estruturas_buscar": AgentTool(EstruturasBuscarArgs, estruturas_buscar),
    "estrutura_detalhe": AgentTool(EstruturaDetalheArgs, estrutura_detalhe),
    "pesquisas": AgentTool(PesquisasArgs, pesquisas),
    "virais": AgentTool(ViraisArgs, virais),
    "desempenho": AgentTool(DesempenhoArgs, desempenho),
    "voz_amostras": AgentTool(VozAmostrasArgs, voz_amostras),
    "treinamentos": AgentTool(TreinamentosArgs, treinamentos),
}

__all__ = ["CRIACAO_TOOLS_ISSUER", "CRIACAO_TOOLS_SCOPE", "REGISTRY"]
