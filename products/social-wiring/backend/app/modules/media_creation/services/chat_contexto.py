"""Chat retrieval -- the v1 "tools" (``specs/geracao-contract.md`` section 6.3).

The seed LLM layer has no tool calling, so what CoreStudio's agents fetched through tools
(``consultar_variaveis_perfil`` / ``searchMyResearch`` / ``searchMyCerebro``) is assembled here,
server-side, **per message**, in a fixed priority order under a hard character cap:

1. Meu Perfil  2. Memorias of (user, marca)  3. explicit ``@`` references (ownership-checked)
4. automatic retrieval (HEADLINE: allow-list structures + approved research; ROTEIRO: Nucleo + Metodo
   "Elementos para conteudo").

Everything third-party or user-authored is emitted inside ``<material tipo="...">`` blocks with the
closing tag neutralised (prompt-injection fence, section 9.1); the system prompts state that a
``<material>`` block is data, never instructions.

``NOC-REMEDIATE[llm-tool-use]`` -- 2026-10-10: when the seed grows tool calling (Fake + Real per
provider) these retrievers become model tools with no API change.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from noctusai_lib.integrations.persistence.table_reads import batched

from app.modules.media_creation.geracao_taxonomias import NICHOS, PROFISSOES
from app.modules.media_creation.pesquisa_variables import VARIABLES
from app.modules.media_creation.prompts.cerebro_synthesis import ELEMENTOS_HEADING

logger = logging.getLogger(__name__)

PERFIL = "cs_marca_perfil"
MEMORIAS = "cs_memorias"
ITENS = "cs_research_items"
BRAINS = "cs_brains"
VIRAIS = "cs_virais"
PERFIS = "cs_perfis_monitorados"
REFERENCIAS_BIB = "cs_biblioteca_referencias"
HEADLINES = "cs_headlines"

#: Hard caps of the automatic retrieval (section 6.3).
MAX_ESTRUTURAS = 12
MAX_ITENS_PESQUISA = 150
MAX_CHARS_PESQUISA = 8000
MAX_CHARS_CEREBRO = 20_000
MAX_VIRAIS_PERFIL = 15
MENCOES_PAGE_SIZE = 30

NICHO_NOMES = dict(NICHOS)
PROFISSAO_NOMES = dict(PROFISSOES)
VARIAVEL_ROTULOS = {v.slug: v.label for v in VARIABLES}

#: The two Sistema brains whose "Elementos para conteudo" feed the ROTEIRO agent.
ROTEIRO_BRAINS = ("nucleo-de-influencia", "metodo-do-especialista")

_TRUNCADO = "\n[...conteudo truncado pelo limite de contexto]"
_MIN_SECAO = 200
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_FENCE_RE = re.compile(r"<\s*(/?)\s*material", re.IGNORECASE)
_LIKE_RE = re.compile(r"[%_*\\,()]")


class ChatError(Exception):
    """A request-level failure: HTTP ``status`` + pt-BR ``detail`` (+ optional machine ``code``)."""

    def __init__(self, status: int, detail: str, *, code: Optional[str] = None,
                 headers: Optional[dict[str, str]] = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code
        self.headers = headers or {}


def eh_uuid(valor: str) -> bool:
    return bool(_UUID_RE.match(valor or ""))


def cerca(texto: str) -> str:
    """Neutralise any ``<material`` / ``</material`` inside untrusted text so it cannot close the fence."""
    return _FENCE_RE.sub(lambda m: f"&lt;{m.group(1)}material", texto or "")


def bloco(tipo: str, conteudo: str, **attrs: str) -> str:
    extra = "".join(f' {k}="{cerca(str(v)).replace(chr(34), chr(39))}"' for k, v in attrs.items())
    return f'<material tipo="{tipo}"{extra}>\n{cerca(conteudo).strip()}\n</material>'


def _like(q: Optional[str]) -> str:
    return _LIKE_RE.sub(" ", q or "").strip()


@dataclass
class ReferenciaResolvida:
    tipo: str
    id: str
    rotulo: str
    dados: dict[str, Any] = field(default_factory=dict)

    def como_dict(self) -> dict[str, str]:
        return {"tipo": self.tipo, "id": self.id, "rotulo": self.rotulo}


@dataclass
class ContextoMontado:
    texto: str
    chars: int
    truncado: bool
    codigos_permitidos: list[int]


class _Orcamento:
    """Appends sections in priority order; a section that no longer fits is clipped (marked) or dropped."""

    def __init__(self, limite: int) -> None:
        self.restante = limite
        self.partes: list[str] = []
        self.truncado = False

    def add(self, secao: str) -> bool:
        if not secao:
            return True
        custo = len(secao) + 2
        if custo <= self.restante:
            self.partes.append(secao)
            self.restante -= custo
            return True
        self.truncado = True
        if self.restante >= _MIN_SECAO:
            corte = max(self.restante - len(_TRUNCADO) - 2 - len("\n</material>"), 0)
            self.partes.append(secao[:corte] + _TRUNCADO + "\n</material>")
            self.restante = 0
        return False

    def texto(self) -> str:
        return "\n\n".join(self.partes)


class ChatContexto:
    """Org-scoped, marca-scoped reads for the chat. Every id coming from the client is checked here."""

    def __init__(self, db: Any, org_id: str, user_id: str, limite: int) -> None:
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.limite = limite

    # ── allow-list (Minha Biblioteca) ────────────────────────────────────

    def _allowlist(self, marca_id: str) -> list[dict[str, Any]]:
        return (
            self.db.table(REFERENCIAS_BIB)
            .select("id,modo,perfil_id,viral_id,posts_ate")
            .eq("org_id", self.org_id).eq("marca_id", marca_id).execute().data
        ) or []

    def _viral_permitido(self, marca_id: str, viral: dict[str, Any], refs: list[dict[str, Any]]) -> bool:
        for r in refs:
            if r["modo"] == "video" and r.get("viral_id") == viral["id"]:
                return True
            if r["modo"] == "perfil" and r.get("perfil_id") == viral.get("perfil_id"):
                return True
        return False

    # ── @ references: resolution + ownership (404 BEFORE streaming) ──────

    def resolver(self, marca_id: str, refs: list[Any]) -> list[ReferenciaResolvida]:
        vistos: set[tuple[str, str]] = set()
        out: list[ReferenciaResolvida] = []
        allow: Optional[list[dict[str, Any]]] = None
        for ref in refs:
            chave = (ref.tipo, ref.id)
            if chave in vistos:
                continue
            vistos.add(chave)
            if ref.tipo == "pesquisa":
                out.append(self._resolver_pesquisa(marca_id, ref.id))
            elif ref.tipo == "cerebro":
                out.append(self._resolver_cerebro(marca_id, ref.id))
            elif ref.tipo == "headline":
                out.append(self._resolver_headline(marca_id, ref.id))
            else:
                if allow is None:
                    allow = self._allowlist(marca_id)
                out.append(self._resolver_biblioteca(marca_id, ref.id, allow))
        return out

    def _nao_encontrado(self, o_que: str) -> ChatError:
        return ChatError(404, f"{o_que} não encontrado(a)")

    def _resolver_pesquisa(self, marca_id: str, ref_id: str) -> ReferenciaResolvida:
        if eh_uuid(ref_id):
            rows = (
                self.db.table(ITENS).select("id,variable_slug,content,status")
                .eq("id", ref_id).eq("org_id", self.org_id).eq("marca_id", marca_id).execute().data
            )
            if not rows or rows[0]["status"] != "approved":
                raise self._nao_encontrado("Item de pesquisa")
            item = rows[0]
            return ReferenciaResolvida("pesquisa", ref_id, item["content"][:80], {"itens": [item]})
        if ref_id not in VARIAVEL_ROTULOS:
            raise self._nao_encontrado("Variável de pesquisa")
        itens = (
            self.db.table(ITENS).select("id,variable_slug,content")
            .eq("org_id", self.org_id).eq("marca_id", marca_id)
            .eq("variable_slug", ref_id).eq("status", "approved")
            .order("created_at", desc=True).limit(MAX_ITENS_PESQUISA).execute().data
        ) or []
        return ReferenciaResolvida("pesquisa", ref_id, VARIAVEL_ROTULOS[ref_id], {"itens": itens})

    def _resolver_cerebro(self, marca_id: str, ref_id: str) -> ReferenciaResolvida:
        rows = (
            self.db.table(BRAINS).select("id,name,content")
            .eq("id", ref_id).eq("org_id", self.org_id).eq("marca_id", marca_id).execute().data
        ) if eh_uuid(ref_id) else []
        if not rows:
            raise self._nao_encontrado("Cérebro")
        return ReferenciaResolvida("cerebro", ref_id, rows[0]["name"], {"brain": rows[0]})

    def _resolver_headline(self, marca_id: str, ref_id: str) -> ReferenciaResolvida:
        rows = (
            self.db.table(HEADLINES).select("id,texto")
            .eq("id", ref_id).eq("org_id", self.org_id).eq("marca_id", marca_id).execute().data
        ) if eh_uuid(ref_id) else []
        if not rows:
            raise self._nao_encontrado("Headline")
        return ReferenciaResolvida("headline", ref_id, rows[0]["texto"][:80], {"headline": rows[0]})

    def _resolver_biblioteca(
        self, marca_id: str, ref_id: str, allow: list[dict[str, Any]]
    ) -> ReferenciaResolvida:
        if ref_id.startswith("perfil:"):
            perfil_id = ref_id[len("perfil:"):]
            permitido = eh_uuid(perfil_id) and any(
                r["modo"] == "perfil" and r.get("perfil_id") == perfil_id for r in allow
            )
            rows = (
                self.db.table(PERFIS).select("id,handle")
                .eq("id", perfil_id).eq("org_id", self.org_id).execute().data
            ) if permitido else []
            if not rows:
                raise self._nao_encontrado("Perfil")
            handle = rows[0]["handle"]
            virais = (
                self.db.table(VIRAIS)
                .select("id,codigo,gancho,blueprint,score_viral,perfil_id")
                .eq("org_id", self.org_id).eq("perfil_id", perfil_id)
                .order("score_viral", desc=True).limit(MAX_VIRAIS_PERFIL).execute().data
            ) or []
            return ReferenciaResolvida(
                "biblioteca", ref_id, f"@{handle} — Todos os vídeos", {"perfil": rows[0], "virais": virais}
            )
        rows = (
            self.db.table(VIRAIS)
            .select("id,codigo,perfil_id,gancho,blueprint,transcricao_texto,caption")
            .eq("id", ref_id).eq("org_id", self.org_id).execute().data
        ) if eh_uuid(ref_id) else []
        if not rows or not self._viral_permitido(marca_id, rows[0], allow):
            raise self._nao_encontrado("Vídeo")
        viral = rows[0]
        rotulo = f"#{viral['codigo']} — {(viral.get('gancho') or viral.get('caption') or '')[:60]}".rstrip(" —")
        return ReferenciaResolvida("biblioteca", ref_id, rotulo, {"viral": viral})

    # ── context assembly ─────────────────────────────────────────────────

    def montar(self, conversa: dict[str, Any], refs: list[ReferenciaResolvida]) -> ContextoMontado:
        marca_id, agente = conversa["marca_id"], conversa["agente"]
        orc = _Orcamento(self.limite)
        codigos: list[int] = []

        def add_codigo(codigo: Any) -> None:
            if isinstance(codigo, int) and codigo not in codigos:
                codigos.append(codigo)

        # 1 + 2: perfil, memorias (always first: they survive a tight cap)
        orc.add(self._secao_perfil(marca_id))
        orc.add(self._secao_memorias(marca_id))
        # 3: explicit references, in the order the user attached them
        for ref in refs:
            orc.add(self._secao_referencia(ref, add_codigo))
        # 4: automatic retrieval
        if agente == "headline":
            orc.add(self._secao_estruturas(marca_id, refs, add_codigo))
            orc.add(self._secao_pesquisa(marca_id))
        else:
            orc.add(self._secao_roteiro_brains(marca_id))
        texto = orc.texto()
        return ContextoMontado(texto=texto, chars=len(texto), truncado=orc.truncado, codigos_permitidos=codigos)

    def _secao_perfil(self, marca_id: str) -> str:
        rows = (
            self.db.table(PERFIL)
            .select("bio,nichos,profissoes,apresentacao_magnetica,ctas")
            .eq("marca_id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            return ""
        p = rows[0]
        linhas: list[str] = []
        if p.get("bio"):
            linhas.append(f"BIO:\n{p['bio']}")
        nichos = [NICHO_NOMES[i] for i in (p.get("nichos") or []) if i in NICHO_NOMES]
        if nichos:
            linhas.append("NICHOS: " + ", ".join(nichos))
        profs = [PROFISSAO_NOMES[i] for i in (p.get("profissoes") or []) if i in PROFISSAO_NOMES]
        if profs:
            linhas.append("PROFISSÕES: " + ", ".join(profs))
        if p.get("apresentacao_magnetica"):
            linhas.append(f"<Apresentação Magnética>\n{p['apresentacao_magnetica']}\n</Apresentação Magnética>")
        if p.get("ctas"):
            linhas.append(f"<CTAs>\n{p['ctas']}\n</CTAs>")
        return bloco("perfil_da_marca", "\n\n".join(linhas)) if linhas else ""

    def _secao_memorias(self, marca_id: str) -> str:
        rows = (
            self.db.table(MEMORIAS).select("texto,created_at")
            .eq("org_id", self.org_id).eq("user_id", self.user_id).eq("marca_id", marca_id)
            .order("created_at").execute().data
        ) or []
        if not rows:
            return ""
        return bloco("memorias_do_usuario", "\n".join(f"- {r['texto']}" for r in rows))

    def _secao_referencia(self, ref: ReferenciaResolvida, add_codigo) -> str:
        d = ref.dados
        if ref.tipo == "pesquisa":
            itens = d["itens"]
            if not itens:
                return bloco("pesquisa", "(nenhum item aprovado)", variavel=ref.rotulo)
            corpo = "\n".join(f"- [{i['variable_slug']}] {i['content']}" for i in itens)
            return bloco("pesquisa", corpo, referencia=ref.rotulo)
        if ref.tipo == "cerebro":
            b = d["brain"]
            return bloco("cerebro", (b.get("content") or "")[:MAX_CHARS_CEREBRO] or "(vazio)", nome=b["name"])
        if ref.tipo == "headline":
            return bloco("headline", d["headline"]["texto"])
        if "viral" in d:
            v = d["viral"]
            add_codigo(v.get("codigo"))
            partes = [f"estrutura #{v['codigo']}"]
            if v.get("gancho"):
                partes.append(f"GANCHO: {v['gancho']}")
            if v.get("blueprint"):
                partes.append(f"BLUEPRINT: {v['blueprint']}")
            texto = v.get("transcricao_texto") or v.get("caption")
            if texto:
                partes.append(f"TRANSCRIÇÃO/LEGENDA:\n{texto[:6000]}")
            return bloco("estrutura_viral", "\n".join(partes), origem="perfil de terceiros")
        linhas = []
        for v in d["virais"]:
            add_codigo(v.get("codigo"))
            linhas.append(
                f"estrutura #{v['codigo']}: " + (v.get("blueprint") or v.get("gancho") or "(sem estrutura ainda)")
            )
        return bloco("estrutura_viral", "\n".join(linhas) or "(sem vídeos)", origem=ref.rotulo)

    def _secao_estruturas(self, marca_id: str, refs: list[ReferenciaResolvida], add_codigo) -> str:
        perfis_foco = {r.dados["perfil"]["id"] for r in refs if r.tipo == "biblioteca" and "perfil" in r.dados}
        pool = self._pool_estruturas(marca_id, perfis_foco)
        ja_citados = {r.dados["viral"]["id"] for r in refs if r.tipo == "biblioteca" and "viral" in r.dados}
        linhas = []
        for v in pool:
            if v["id"] in ja_citados:
                continue
            add_codigo(v["codigo"])
            linhas.append(f"estrutura #{v['codigo']}: {v['blueprint']}")
        return bloco("estruturas_virais", "\n".join(linhas), origem="perfis de terceiros") if linhas else ""

    def _pool_estruturas(self, marca_id: str, perfis_foco: set[str]) -> list[dict[str, Any]]:
        """Section 5.1 pool, ranked by ``score_viral``: allow-list -> niche overlap -> all org virais."""
        cols = "id,codigo,blueprint,score_viral,perfil_id,publicado_em,nicho_ids"

        def base():
            return (
                self.db.table(VIRAIS).select(cols)
                .eq("org_id", self.org_id).eq("classificacao_status", "concluida")
            )

        def util(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [r for r in rows if r.get("blueprint")]

        achados: dict[str, dict[str, Any]] = {}
        allow = self._allowlist(marca_id)
        for r in allow:
            if r["modo"] == "perfil":
                if perfis_foco and r["perfil_id"] not in perfis_foco:
                    continue
                q = base().eq("perfil_id", r["perfil_id"])
                if r.get("posts_ate"):
                    q = q.gte("publicado_em", r["posts_ate"])
                rows = q.order("score_viral", desc=True).limit(MAX_ESTRUTURAS).execute().data or []
            elif not perfis_foco:
                rows = base().eq("id", r["viral_id"]).execute().data or []
            else:
                rows = []
            for v in util(rows):
                achados[v["id"]] = v
        if not achados and not perfis_foco:
            perfil = (
                self.db.table(PERFIL).select("nichos").eq("marca_id", marca_id).eq("org_id", self.org_id)
                .execute().data
            )
            nichos = (perfil[0].get("nichos") if perfil else None) or []
            if nichos:
                for v in util(base().overlaps("nicho_ids", nichos)
                              .order("score_viral", desc=True).limit(MAX_ESTRUTURAS).execute().data or []):
                    if set(v.get("nicho_ids") or []) & set(nichos):  # belt and braces over the SQL overlap
                        achados[v["id"]] = v
            if not achados:
                for v in util(base().order("score_viral", desc=True).limit(MAX_ESTRUTURAS).execute().data or []):
                    achados[v["id"]] = v
        ordenado = sorted(achados.values(), key=lambda v: (v.get("score_viral") is None, -(v.get("score_viral") or 0)))
        return ordenado[:MAX_ESTRUTURAS]

    def _secao_pesquisa(self, marca_id: str) -> str:
        itens = (
            self.db.table(ITENS).select("variable_slug,content")
            .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("status", "approved")
            .order("created_at", desc=True).limit(MAX_ITENS_PESQUISA).execute().data
        ) or []
        linhas: list[str] = []
        total = 0
        for i in itens:
            linha = f"- [{i['variable_slug']}] {i['content']}"
            if total + len(linha) > MAX_CHARS_PESQUISA:
                break
            linhas.append(linha)
            total += len(linha) + 1
        return bloco("pesquisa_aprovada", "\n".join(linhas)) if linhas else ""

    def _secao_roteiro_brains(self, marca_id: str) -> str:
        rows = (
            self.db.table(BRAINS).select("name,template_slug,content")
            .eq("org_id", self.org_id).eq("marca_id", marca_id).in_("template_slug", list(ROTEIRO_BRAINS))
            .execute().data
        ) or []
        partes = []
        for slug in ROTEIRO_BRAINS:
            for b in rows:
                if b["template_slug"] != slug:
                    continue
                elementos = elementos_para_conteudo(b.get("content") or "")
                if elementos:
                    partes.append(bloco("cerebro", elementos, nome=b["name"]))
        return "\n\n".join(partes)

    # ── @ picker (endpoint 46) ───────────────────────────────────────────

    def mencoes(self, marca_id: str, tipo: str, q: Optional[str], variavel: Optional[str], page: int) -> list[dict]:
        inicio = max(page, 0) * MENCOES_PAGE_SIZE
        fim = inicio + MENCOES_PAGE_SIZE - 1
        busca = _like(q)
        if tipo == "pesquisa":
            query = (
                self.db.table(ITENS).select("id,variable_slug,content")
                .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("status", "approved")
            )
            if variavel:
                query = query.eq("variable_slug", variavel)
            if busca:
                query = query.ilike("content", f"%{busca}%")
            rows = query.order("created_at", desc=True).range(inicio, fim).execute().data or []
            return [
                {"tipo": "pesquisa", "id": r["id"], "rotulo": r["content"][:80],
                 "detalhe": VARIAVEL_ROTULOS.get(r["variable_slug"], r["variable_slug"])}
                for r in rows
            ]
        if tipo == "cerebro":
            query = self.db.table(BRAINS).select("id,name,kind").eq("org_id", self.org_id).eq("marca_id", marca_id)
            if busca:
                query = query.ilike("name", f"%{busca}%")
            rows = query.order("created_at").range(inicio, fim).execute().data or []
            return [
                {"tipo": "cerebro", "id": r["id"], "rotulo": r["name"],
                 "detalhe": "Sistema" if r["kind"] == "sistema" else "Personalizado"}
                for r in rows
            ]
        if tipo == "headline":
            query = self.db.table(HEADLINES).select("id,texto,favorita").eq("org_id", self.org_id).eq("marca_id", marca_id)
            if busca:
                query = query.ilike("texto", f"%{busca}%")
            rows = query.order("created_at", desc=True).range(inicio, fim).execute().data or []
            return [
                {"tipo": "headline", "id": r["id"], "rotulo": r["texto"][:80],
                 "detalhe": "Favorita" if r.get("favorita") else None}
                for r in rows
            ]
        return self._mencoes_biblioteca(marca_id, busca, inicio, fim, page)

    def _mencoes_biblioteca(self, marca_id: str, busca: str, inicio: int, fim: int, page: int) -> list[dict]:
        allow = self._allowlist(marca_id)
        perfil_ids = [r["perfil_id"] for r in allow if r["modo"] == "perfil"]
        video_ids = [r["viral_id"] for r in allow if r["modo"] == "video"]
        if not perfil_ids and not video_ids:
            return []
        perfis: dict[str, dict] = {}
        for lote in batched(perfil_ids):
            for p in self.db.table(PERFIS).select("id,handle").eq("org_id", self.org_id).in_("id", lote).execute().data or []:
                perfis[p["id"]] = p
        out: list[dict] = []
        if page <= 0:
            for pid in perfil_ids:
                p = perfis.get(pid)
                if p and (not busca or busca.lower().lstrip("@") in p["handle"].lower()):
                    out.append({"tipo": "biblioteca", "id": f"perfil:{pid}",
                                "rotulo": f"@{p['handle']} — Todos os vídeos", "detalhe": "Perfil"})
        cols = "id,codigo,perfil_id,gancho,caption"
        virais: list[dict] = []
        if perfil_ids:
            for lote in batched(perfil_ids):
                q = self.db.table(VIRAIS).select(cols).eq("org_id", self.org_id).in_("perfil_id", lote)
                if busca:
                    q = q.ilike("gancho", f"%{busca}%")
                virais += q.order("score_viral", desc=True).range(inicio, fim).execute().data or []
        if page <= 0:
            for lote in batched(video_ids):
                virais += self.db.table(VIRAIS).select(cols).eq("org_id", self.org_id).in_("id", lote).execute().data or []
        vistos: set[str] = set()
        for v in virais:
            if v["id"] in vistos:
                continue
            vistos.add(v["id"])
            handle = (perfis.get(v["perfil_id"]) or {}).get("handle")
            texto = (v.get("gancho") or v.get("caption") or "")[:60]
            out.append({"tipo": "biblioteca", "id": v["id"], "rotulo": f"#{v['codigo']} — {texto}".rstrip(" —"),
                        "detalhe": f"@{handle}" if handle else None})
        return out


def elementos_para_conteudo(content: str) -> str:
    """The "### Elementos para conteudo" tail of a synthesized brain (empty when absent)."""
    pos = content.find(ELEMENTOS_HEADING)
    if pos < 0:
        return ""
    resto = content[pos + len(ELEMENTOS_HEADING):]
    fim = re.search(r"^#{1,3} ", resto, re.MULTILINE)
    return (resto[: fim.start()] if fim else resto).strip()


__all__ = [
    "ChatContexto", "ChatError", "ContextoMontado", "MAX_CHARS_PESQUISA", "MAX_ESTRUTURAS",
    "MAX_ITENS_PESQUISA", "ReferenciaResolvida", "bloco", "cerca", "eh_uuid", "elementos_para_conteudo",
]
