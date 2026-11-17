"""Chat retrieval -- the v1 "tools" (``specs/geracao-contract.md`` section 6.3).

The seed LLM layer has no tool calling, so what the reference app's agents fetched through tools
(``consultar_variaveis_perfil`` / ``searchMyResearch`` / ``searchMyCerebro``) is assembled here,
server-side, **per message**, in a fixed priority order under a hard character cap:

1. Meu Perfil  2. Memorias of (user, marca)  3. Cerebros of the marca (HEADLINE)  4. explicit ``@`` references
(ownership-checked)  5. the structure-selection mode (+ free-text profile resolution)  6. approved research
(HEADLINE) / Nucleo + Metodo "Elementos para conteudo" (ROTEIRO)  7. the Estruturas POOL
(``estruturas-contract.md`` section 8: platform-wide library, the brand's selected profiles first).

Everything third-party or user-authored is emitted inside ``<material tipo="...">`` blocks with the
closing tag neutralised (prompt-injection fence, section 9.1); the system prompts state that a
``<material>`` block is data, never instructions.

``NOC-REMEDIATE[llm-tool-use]`` -- 2026-10-10: when the seed grows tool calling (Fake + Real per
provider) these retrievers become model tools with no API change.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from noctusai_lib.integrations.persistence.table_reads import batched

from app.modules.media_creation.geracao_taxonomias import NICHOS, PROFISSOES
from app.modules.media_creation.pesquisa_variables import VARIABLES
from app.modules.media_creation.prompts.biblioteca_classificador import normalizar_nfkc
from app.modules.media_creation.prompts.cerebro_synthesis import ELEMENTOS_HEADING
from app.modules.media_creation.prompts import estruturas_contexto as ec
from app.modules.media_creation.services.estruturas_retrieval import (
    EstruturaPool,
    FiltrosPool,
    MAX_ESTRUTURAS,
    ResolucaoPerfis,
    carregar_estruturas,
    indice_de_perfis,
    montar_pool,
    resolver_perfis_no_texto,
)
from app.modules.media_creation.services.estruturas_service import EstruturasService
from app.modules.media_creation.services.propostas import EstruturaCitavel

logger = logging.getLogger(__name__)

PERFIL = "cs_marca_perfil"
MEMORIAS = "cs_memorias"
ITENS = "cs_research_items"
BRAINS = "cs_brains"
VIRAIS = "cs_virais"
PERFIS = "cs_perfis_monitorados"
REFERENCIAS_BIB = "cs_biblioteca_referencias"
HEADLINES = "cs_headlines"
ESTRUTURAS = "cs_estruturas"

#: Hard caps of the automatic retrieval (section 6.3); ``MAX_ESTRUTURAS`` (12) lives with the pool.
MAX_ITENS_PESQUISA = 150
MAX_CHARS_PESQUISA = 8000
MAX_CHARS_CEREBRO = 20_000
MAX_CEREBROS_MARCA = 5
MAX_CHARS_CEREBRO_MARCA = 6000
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
    return _FENCE_RE.sub(lambda m: f"&lt;{m.group(1)}material", normalizar_nfkc(texto))


def bloco(tipo: str, conteudo: str, **attrs: str) -> str:
    extra = "".join(f' {k}="{cerca(str(v)).replace(chr(34), chr(39))}"' for k, v in attrs.items())
    return f'<material tipo="{tipo}"{extra}>\n{cerca(conteudo).strip()}\n</material>'


def _like(q: Optional[str]) -> str:
    return _LIKE_RE.sub(" ", q or "").strip()


def modo_de_selecao(refs: list["ReferenciaResolvida"], resolucao: Optional[ResolucaoPerfis] = None) -> str:
    """How the agent picks its structure (estruturas-contract section 8.2):
    ``post`` = exactly one ``@estrutura`` (or the legacy ``@post``) and no other library mention -> that
    structure, mandatory; ``mencoes`` = any other set of library mentions (``@perfil``, several ``@estrutura``,
    free-text profiles the resolver settled) -> ONLY those; ``auto`` = no library mention -> the pool.
    ``perfil_ambiguo`` (a typed name matched several profiles) and ``perfil_nao_encontrado`` (matched none, and no
    explicit mention to fall back on) offer NO pool: the agent asks."""
    if resolucao is not None and resolucao.ambiguos:
        return "perfil_ambiguo"
    bib = [r for r in refs if r.tipo in ("biblioteca", "estrutura")]
    if not bib:
        return "perfil_nao_encontrado" if resolucao is not None and resolucao.nao_encontrados else "auto"
    if len(bib) == 1 and (bib[0].tipo == "estrutura" or "viral" in bib[0].dados):
        return "post"
    return "mencoes"


@dataclass
class ReferenciaResolvida:
    tipo: str
    id: str
    rotulo: str
    dados: dict[str, Any] = field(default_factory=dict)
    #: ``"texto"`` when the SERVER resolved it from a typed profile name (section 8.3), else unset.
    via: Optional[str] = None

    def como_dict(self) -> dict[str, str]:
        base = {"tipo": self.tipo, "id": self.id, "rotulo": self.rotulo}
        return {**base, "via": self.via} if self.via else base


@dataclass
class ContextoMontado:
    texto: str
    chars: int
    truncado: bool
    #: Numeric codes of every Estrutura shown in full (the SSE ``meta.codigos_permitidos`` shape, unchanged).
    codigos_permitidos: list[int]
    #: The SAME set keyed by code string -> what ``propostas.extrair_propostas`` validates the model's citations
    #: against (the EST-4a/UNI-1a seam; the dict view of ``codigos_permitidos``).
    citaveis: dict[str, EstruturaCitavel] = field(default_factory=dict)
    modo_estrutura: str = "auto"
    resolucao: Optional[ResolucaoPerfis] = None
    #: ``cs_fluxo_eventos`` rows the chat flow writes (``perfil_resolvido|perfil_ambiguo|perfil_nao_encontrado``).
    eventos: list[dict[str, Any]] = field(default_factory=list)
    #: Profile mentions the server resolved from the typed text -- stored on the message ``referencias``.
    referencias_via_texto: list[ReferenciaResolvida] = field(default_factory=list)


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

    def add_linhas(self, tipo: str, linhas: list[tuple[str, str]], **attrs: str) -> list[str]:
        """Fits as many whole ``(chave, linha)`` as the budget allows into ONE material block (never half a line);
        returns the keys that made it in. The caller derives the citable codes from the RETURN, not from what it
        rendered, so a clipped pool never lets the model cite a structure it never saw."""
        dentro: list[str] = []
        melhor = ""
        for chave, linha in linhas:
            candidato = bloco(tipo, "\n".join([*(t for _, t in linhas[: len(dentro)]), linha]), **attrs)
            if len(candidato) + 2 > self.restante:
                self.truncado = True
                break
            dentro.append(chave)
            melhor = candidato
        if melhor:
            self.partes.append(melhor)
            self.restante -= len(melhor) + 2
        return dentro

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
            elif ref.tipo == "estrutura":
                out.append(self._resolver_estrutura(ref.id))
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

    def _resolver_estrutura(self, ref_id: str) -> ReferenciaResolvida:
        """``@estrutura``: an ``ativa`` Estrutura of the PLATFORM library. Explicit intent beats the brand's default
        scope, so the brand's selection is not required; a rascunho / arquivada / unknown id is a 404."""
        rows = (
            self.db.table(ESTRUTURAS).select("id,codigo,formula_headline,status").eq("id", ref_id).eq("status", "ativa")
            .execute().data
        ) if eh_uuid(ref_id) else []
        if not rows:
            raise ChatError(404, "Estrutura não encontrada ou não está ativa", code="estrutura_indisponivel")
        e = rows[0]
        rotulo = f"#{e['codigo']} — {(e.get('formula_headline') or '')[:60]}".rstrip(" —")
        return ReferenciaResolvida("estrutura", ref_id, rotulo, {"estrutura_id": str(e["id"])})

    def _resolver_biblioteca(
        self, marca_id: str, ref_id: str, allow: list[dict[str, Any]]
    ) -> ReferenciaResolvida:
        if ref_id.startswith("perfil:"):
            # An explicit ``@perfil`` (picker, or a chip the user clicked after ``perfil_ambiguo``): any PLATFORM
            # library profile -- explicit intent beats the brand's default selection. Not a library profile => coded 404.
            perfil_id = ref_id[len("perfil:"):]
            rows = self.db.table(PERFIS).select("id,handle").eq("id", perfil_id).execute().data if eh_uuid(perfil_id) else []
            if not rows:
                raise ChatError(404, "Perfil não encontrado na biblioteca", code="perfil_invalido")
            return ReferenciaResolvida(
                "biblioteca", ref_id, f"@{rows[0]['handle']} — Todos os vídeos", {"perfil": rows[0]}
            )
        rows = (
            self.db.table(VIRAIS)
            .select("id,codigo,perfil_id,gancho,blueprint,transcricao_texto,caption")
            .eq("id", ref_id).execute().data
        ) if eh_uuid(ref_id) else []
        if not rows or not self._viral_permitido(marca_id, rows[0], allow):
            raise self._nao_encontrado("Vídeo")
        viral = rows[0]
        rotulo = f"#{viral['codigo']} — {(viral.get('gancho') or viral.get('caption') or '')[:60]}".rstrip(" —")
        dados: dict[str, Any] = {"viral": viral}
        # A video that already has an ``ativa`` Estrutura is offered AS that Estrutura (one code namespace).
        derivada = (
            self.db.table(ESTRUTURAS).select("id").eq("viral_id", viral["id"]).eq("status", "ativa").limit(1).execute().data
        )
        if derivada:
            dados["estrutura_id"] = str(derivada[0]["id"])
        return ReferenciaResolvida("biblioteca", ref_id, rotulo, dados)

    def resolver_texto(self, texto: str, refs: list[ReferenciaResolvida]) -> tuple[ResolucaoPerfis, list[ReferenciaResolvida]]:
        """Section 8.3, pre-LLM: the profile names typed in ``texto``. Returns the resolution and the profile mentions
        the SERVER added (``via="texto"``) -- a profile the user already mentioned explicitly is not added twice."""
        resolucao = resolver_perfis_no_texto(texto, indice_de_perfis(self.db), reportar_arroba_desconhecido=False)
        ja = {r.id for r in refs}
        explicitos = {i[len("perfil:"):] for i in ja if i.startswith("perfil:")}
        if explicitos:
            # An explicit profile reference wins: the same name never re-raises ambiguity / not-found.
            resolucao.ambiguos = [a for a in resolucao.ambiguos if not any(c.id in explicitos for c in a.candidatos)]
            resolucao.nao_encontrados = []
        novas: list[ReferenciaResolvida] = []
        for r in resolucao.resolvidos:
            ref_id = f"perfil:{r.perfil_id}"
            if ref_id in ja:
                continue
            ja.add(ref_id)
            novas.append(ReferenciaResolvida(
                "biblioteca", ref_id, f"@{r.handle} — Todos os vídeos",
                {"perfil": {"id": r.perfil_id, "handle": r.handle}}, via="texto",
            ))
        return resolucao, novas

    # ── context assembly ─────────────────────────────────────────────────

    def montar(
        self, conversa: dict[str, Any], refs: list[ReferenciaResolvida], texto: Optional[str] = None,
    ) -> ContextoMontado:
        """``texto`` (the user's message) turns on the free-text profile-name resolution; omitted (the context meter,
        a fresh conversation) it resolves nothing."""
        marca_id, agente = conversa["marca_id"], conversa["agente"]
        semente = str(conversa.get("id") or marca_id)
        orc = _Orcamento(self.limite)
        citaveis: dict[str, EstruturaCitavel] = {}
        codigos: list[int] = []

        def add_estrutura(e: EstruturaPool) -> None:
            citaveis.setdefault(e.codigo, EstruturaCitavel(uuid.UUID(e.id), e.codigo, e.formato or ""))
            if e.codigo.isdigit() and int(e.codigo) not in codigos:
                codigos.append(int(e.codigo))

        def add_codigo(codigo: Any) -> None:  # legacy: a video with no Estrutura yet is still cited by its own code
            if isinstance(codigo, int) and codigo not in codigos:
                codigos.append(codigo)

        resolucao: Optional[ResolucaoPerfis] = None
        via_texto: list[ReferenciaResolvida] = []
        if texto:
            resolucao, via_texto = self.resolver_texto(texto, refs)
        efetivas = [*refs, *via_texto]
        modo = modo_de_selecao(efetivas, resolucao)
        estruturista = agente in ("headline", "roteiro")

        # 1 + 2 + 3: perfil, memorias, cerebros (always first: they survive a tight cap)
        orc.add(self._secao_perfil(marca_id))
        orc.add(self._secao_memorias(marca_id))
        if agente == "headline":
            orc.add(self._secao_cerebros_marca(marca_id))
        # 4: explicit references (and the profiles resolved from the text), in the order the user gave them
        for ref in efetivas:
            orc.add(self._secao_referencia(ref, semente, add_estrutura, add_codigo))
        # 5: the selection mode + the resolution rules
        if estruturista:
            orc.add(bloco("selecao_de_estrutura", f"modo: {modo}", modo=modo))
            if modo in ("perfil_ambiguo", "perfil_nao_encontrado") and resolucao is not None:
                orc.add(bloco("resolucao_de_perfis", ec.renderizar_resolucao(resolucao, modo=modo), modo=modo))
        # The pool: only a mention-free turn gets the open automatic pool; any mention restricts the offer to what
        # was mentioned, and an ambiguous / unknown profile offers nothing (the agent asks).
        pool = self._pool(marca_id, semente) if estruturista and modo == "auto" else []
        if estruturista and (citaveis or pool):
            orc.add(bloco("regras_de_estrutura", ec.REGRA_PLACEHOLDERS))
        # 6: research / roteiro brains
        if agente == "headline":
            orc.add(self._secao_pesquisa(marca_id))
        else:
            orc.add(self._secao_roteiro_brains(marca_id))
        # 7: the pool is the section that gets clipped first (it is last); only fitted lines are citable
        if estruturista and modo == "auto":
            if pool:
                por_codigo = {e.codigo: e for e in pool}
                dentro = orc.add_linhas(
                    "estruturas_biblioteca", ec.renderizar_lista(pool), origem="biblioteca de estruturas",
                )
                for cod in dentro:
                    add_estrutura(por_codigo[cod])
            else:
                orc.add(bloco("estruturas_biblioteca", ec.BIBLIOTECA_VAZIA))
        texto_final = orc.texto()
        return ContextoMontado(
            texto=texto_final, chars=len(texto_final), truncado=orc.truncado, codigos_permitidos=codigos,
            citaveis=citaveis, modo_estrutura=modo, resolucao=resolucao,
            eventos=resolucao.eventos() if resolucao is not None else [], referencias_via_texto=via_texto,
        )

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

    def _secao_referencia(self, ref: ReferenciaResolvida, semente: str, add_estrutura, add_codigo) -> str:
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
        if ref.tipo == "estrutura":
            return self._secao_estruturas_citadas(carregar_estruturas(self.db, [d["estrutura_id"]]), ref.rotulo, add_estrutura)
        if "perfil" in d:
            # an ``@perfil`` (typed or resolved from the text): that profile's Estruturas, round-robin-free (one profile)
            pool = montar_pool(self.db, FiltrosPool(perfil_ids=[str(d["perfil"]["id"])]), semente=semente)
            if not pool:
                return bloco("estruturas_biblioteca", "(este perfil não tem estruturas ativas)", origem=ref.rotulo)
            return self._secao_estruturas_citadas(pool, ref.rotulo, add_estrutura)
        if d.get("estrutura_id"):
            return self._secao_estruturas_citadas(carregar_estruturas(self.db, [d["estrutura_id"]]), ref.rotulo, add_estrutura)
        v = d["viral"]  # a video with no ativa Estrutura yet: the legacy blueprint rendering
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

    @staticmethod
    def _secao_estruturas_citadas(estruturas: list[EstruturaPool], origem: str, add_estrutura) -> str:
        if not estruturas:
            return ""
        for e in estruturas:
            add_estrutura(e)
        return bloco("estruturas_biblioteca", "\n".join(t for _, t in ec.renderizar_lista(estruturas)), origem=origem)

    def _pool(self, marca_id: str, semente: str) -> list[EstruturaPool]:
        """The automatic pool (section 8.2): ``ativa`` Estruturas of the brand's SELECTED profiles
        (``cs_biblioteca_referencias`` read through ``EstruturasService.perfis_selecionados``); the whole library when
        the brand selected nothing; round-robin across profiles, seeded within each, capped at ``MAX_ESTRUTURAS``."""
        selecionados = EstruturasService(
            self.db, org_id=self.org_id, user_id=self.user_id, is_admin=False
        ).perfis_selecionados(marca_id)
        escopo = sorted(selecionados) if selecionados else None
        return montar_pool(self.db, FiltrosPool(perfil_ids=escopo), semente=semente, limite=MAX_ESTRUTURAS)

    def _secao_cerebros_marca(self, marca_id: str) -> str:
        """The brand's Cerebros (org-scoped, most recently updated first): with the bio they fill a formula's
        ``[placeholders]`` (section 8.1)."""
        rows = (
            self.db.table(BRAINS).select("name,content,updated_at")
            .eq("org_id", self.org_id).eq("marca_id", marca_id)
            .order("updated_at", desc=True).limit(MAX_CEREBROS_MARCA).execute().data
        ) or []
        partes = [
            bloco("cerebro", (b.get("content") or "")[:MAX_CHARS_CEREBRO_MARCA] or "(vazio)", nome=b["name"])
            for b in rows if (b.get("content") or "").strip()
        ]
        return "\n\n".join(partes)

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
        if tipo == "estrutura":
            return self._mencoes_estrutura(busca, inicio, fim)
        return self._mencoes_biblioteca(marca_id, busca, inicio, fim, page)

    def _mencoes_estrutura(self, busca: str, inicio: int, fim: int) -> list[dict]:
        query = self.db.table(ESTRUTURAS).select("id,codigo,perfil_id,formula_headline").eq("status", "ativa")
        if busca:
            query = query.ilike("formula_headline", f"%{busca}%")
        rows = query.order("codigo").range(inicio, fim).execute().data or []
        handles = {
            p["id"]: p["handle"] for p in (
                self.db.table(PERFIS).select("id,handle").in_("id", sorted({r["perfil_id"] for r in rows if r.get("perfil_id")}))
                .execute().data or []
            )
        } if rows else {}
        return [
            {"tipo": "estrutura", "id": r["id"], "rotulo": f"#{r['codigo']} — {(r.get('formula_headline') or '')[:60]}".rstrip(" —"),
             "detalhe": f"@{handles[r['perfil_id']]}" if handles.get(r.get("perfil_id")) else None}
            for r in rows
        ]

    def _mencoes_biblioteca(self, marca_id: str, busca: str, inicio: int, fim: int, page: int) -> list[dict]:
        allow = self._allowlist(marca_id)
        perfil_ids = [r["perfil_id"] for r in allow if r["modo"] == "perfil"]
        video_ids = [r["viral_id"] for r in allow if r["modo"] == "video"]
        if not perfil_ids and not video_ids:
            return []
        perfis: dict[str, dict] = {}
        for lote in batched(perfil_ids):
            for p in self.db.table(PERFIS).select("id,handle").in_("id", lote).execute().data or []:
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
                q = self.db.table(VIRAIS).select(cols).in_("perfil_id", lote)
                if busca:
                    q = q.ilike("gancho", f"%{busca}%")
                virais += q.order("score_viral", desc=True).range(inicio, fim).execute().data or []
        if page <= 0:
            for lote in batched(video_ids):
                virais += self.db.table(VIRAIS).select(cols).in_("id", lote).execute().data or []
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
    "MAX_ITENS_PESQUISA", "ReferenciaResolvida", "modo_de_selecao", "bloco", "cerca", "eh_uuid", "elementos_para_conteudo",
]
