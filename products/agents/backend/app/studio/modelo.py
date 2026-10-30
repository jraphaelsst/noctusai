"""The AGENT MODEL schema: what every agent page and the creation wizard are rendered from (agents-unified CONTRACT §2).

One house, one model. Every agent (role agents such as Julia / Bia / Renata and the product guardians) is ONE card in
the listing and ONE page whose sections come from here -- never a per-key shell. The model is DERIVED, not
hand-duplicated:

* the 7 content AREAS are :data:`app.stores.studio_geracoes.AREAS` (the Julia v2 canonical model, CONTRACT §2.6) and
  each area's fields are read from the item model the generator AND the draft routers validate with
  (:data:`app.schemas.studio_geracao.SAIDAS` -> ``FerramentaIn`` / ``DecisaoIn`` / ``SpecDefIn`` / ...);
* the ``textos`` area lists the keys of :data:`app.studio.textos_registry.TEXTOS` (keys and categories only, no text);
* the ``ferramentas`` area lists :data:`app.studio.ferramentas_registry.FERRAMENTAS_CONHECIDAS`;
* the wizard steps (:data:`PASSOS_ASSISTENTE`) name fields of ``PlataformaAgentCreateRequest`` / ``Briefing`` -- the
  body ``POST /api/studio/plataforma/agents`` already accepts -- and their schema is read from those models.

What lives here by hand is presentation only (pt-BR titles) plus the section -> visibility table, both guarded by tests
against the derived sets (a new AREA without a title fails the suite, it never renders blank).

Visibility (D31, product-agents-platform roadmap): an agent's internals -- its content areas, versions, compiled
prompt, knowledge -- are NoctusAI-superadmin only. :func:`secoes_para` returns only the sections the CALLER may open
for THIS agent; every content route still enforces its own tier (this is the page's map, never the gate).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from app.schemas.studio_geracao import SAIDAS, Briefing
from app.schemas.studio_plataforma import PlataformaAgentCreateRequest
from app.stores.studio_geracoes import AREAS
from app.studio.ferramentas_registry import FERRAMENTAS_CONHECIDAS
from app.studio.textos_registry import TEXTOS

__all__ = [
    "AREA_ROTULOS",
    "Origem",
    "PASSOS_ASSISTENTE",
    "SECOES_PAGINA",
    "Tier",
    "FatosAgente",
    "SecaoPagina",
    "construir_modelo",
    "origem_de",
    "secoes_para",
]

MODELO_VERSAO = 1

#: Where an agent's definition lives: ``legado`` (code-defined, pre-Studio: Bia, One Chat) · ``plataforma`` (THE
#: definition, platform org) · ``instancia`` (an org's instance of a platform definition) · ``org`` (an org-owned
#: Studio agent, e.g. IsaIA -- stays as is).
Origem = Literal["legado", "plataforma", "instancia", "org"]
ORIGENS: tuple[str, ...] = get_args(Origem)

#: Caller tier, ordered: a higher tier sees every section of a lower one.
Tier = Literal["membro", "org_admin", "plataforma"]
_TIER_ORDEM = {"membro": 0, "org_admin": 1, "plataforma": 2}

#: pt-BR presentation of the canonical areas -- keys MUST equal :data:`AREAS` (test-guarded).
AREA_ROTULOS: dict[str, tuple[str, str]] = {
    "secoes": ("Prompt", "As seções do prompt: identidade, objetivo, conduta."),
    "textos": ("Textos do sistema", "Toda frase que chega ao modelo ou ao lead fora do prompt."),
    "ferramentas": ("Ferramentas", "Quais ferramentas o agente usa e como cada uma é descrita."),
    "decisoes": ("Decisões", "Regras de decisão com opções e um padrão."),
    "specs": ("Especificações declaradas", "Os dados que cada organização preenche ({{org.chave}})."),
    "skills": ("Skills", "Procedimentos da biblioteca que o agente deve seguir."),
    "configuracoes": ("Configurações", "Modelo, esforço, idioma e política de ferramentas."),
}


@dataclass(frozen=True)
class FatosAgente:
    """The data facts a section's visibility depends on -- never the agent's key."""

    origem: str
    conteudo_modo: str = "legado"
    kind: str = "runtime"
    runtime: str = "claude_sdk"
    usa_canais: bool = False

    @property
    def chat(self) -> bool:
        """An in-app chat runtime: a legacy ``claude_sdk`` agent, or an org Studio runtime agent off-channel."""
        if self.origem == "legado":
            return self.runtime == "claude_sdk"
        return self.origem == "org" and self.kind == "runtime" and not self.usa_canais


#: A section's extra requirement on :class:`FatosAgente` (all must hold).
_EXIGENCIAS = {
    "linhas": lambda f: f.conteudo_modo == "linhas",
    "legado": lambda f: f.conteudo_modo != "linhas",
    "canais": lambda f: f.usa_canais,
    "dev_advisor": lambda f: f.kind == "dev-advisor",
    "runtime": lambda f: f.kind != "dev-advisor",
    "chat": lambda f: f.chat,
}


@dataclass(frozen=True)
class SecaoPagina:
    """One section of the agent page. ``id`` is the stable section id the frontend maps to a renderer (it equals the
    pre-unification Studio tab id, so ``?tab=`` deep links keep working)."""

    id: str
    titulo: str
    grupo: Literal["painel", "conteudo", "operacao", "organizacao"]
    tier: str
    origens: tuple[str, ...]
    area: str | None = None
    exige: tuple[str, ...] = ()

    def visivel(self, fatos: FatosAgente, tier: str) -> bool:
        return (
            fatos.origem in self.origens
            and _TIER_ORDEM[tier] >= _TIER_ORDEM[self.tier]
            and all(_EXIGENCIAS[e](fatos) for e in self.exige)
        )


_DEFINICAO = ("plataforma", "org")


def _area(id_secao: str, area: str, *, exige: tuple[str, ...] = (), titulo: str | None = None) -> SecaoPagina:
    return SecaoPagina(
        id=id_secao, titulo=titulo or AREA_ROTULOS[area][0], grupo="conteudo", tier="plataforma",
        origens=_DEFINICAO, area=area, exige=exige,
    )


#: The page, in order. Areas first-class (one per canonical area; ``skills`` renders the shared library on a
#: ``linhas`` agent and the agent's own skills on a pre-v2 one).
SECOES_PAGINA: tuple[SecaoPagina, ...] = (
    SecaoPagina("visao-geral", "Visão geral", "painel", "membro", ORIGENS),
    SecaoPagina("conversar", "Conversar", "painel", "membro", ("legado", "org"), exige=("chat",)),
    SecaoPagina("persona", "Persona", "organizacao", "org_admin", ("legado",), exige=("chat",)),
    SecaoPagina("especificacoes-org", "Especificações da organização", "organizacao", "org_admin", ("instancia",)),
    SecaoPagina("controles", "Controles", "organizacao", "org_admin", ("instancia",)),
    SecaoPagina("conversas", "Conversas", "organizacao", "org_admin", ("instancia", "plataforma")),
    _area("prompt", "secoes"),
    _area("textos", "textos", exige=("linhas",)),
    _area("ferramentas", "ferramentas", exige=("linhas",)),
    _area("decisoes", "decisoes", exige=("linhas",)),
    _area("especificacoes", "specs", exige=("linhas",)),
    _area("biblioteca", "skills", exige=("linhas",), titulo="Skills da biblioteca"),
    _area("skills", "skills", exige=("legado",)),
    _area("configuracoes", "configuracoes"),
    SecaoPagina("qualificacao", "Qualificação", "operacao", "plataforma", _DEFINICAO, exige=("linhas",)),
    SecaoPagina("conformidade", "Conformidade", "operacao", "plataforma", _DEFINICAO, exige=("linhas",)),
    SecaoPagina("conhecimento", "Conhecimento", "operacao", "plataforma", ("org",)),
    SecaoPagina("clientes", "Clientes", "operacao", "plataforma", ("org",), exige=("runtime",)),
    SecaoPagina("canais", "Canais", "operacao", "plataforma", _DEFINICAO, exige=("canais",)),
    SecaoPagina("aprendizados", "Aprendizados", "operacao", "plataforma", ("org",), exige=("dev_advisor",)),
    SecaoPagina("avaliacoes", "Avaliações", "operacao", "plataforma", _DEFINICAO),
    SecaoPagina("versoes", "Versões", "operacao", "plataforma", _DEFINICAO),
    SecaoPagina("compilado", "Prompt compilado", "operacao", "plataforma", ("plataforma", "org", "instancia")),
)


def origem_de(definition_mode: str, definition_scope: str) -> str:
    """The agent's :data:`Origem` from its row (``definition_mode`` + ``definition_scope``)."""
    if definition_mode != "studio":
        return "legado"
    return definition_scope if definition_scope in ("plataforma", "instancia") else "org"


def secoes_para(fatos: FatosAgente, tier: str) -> list[str]:
    """The section ids the caller (``tier``) may open on this agent's page, in page order."""
    return [s.id for s in SECOES_PAGINA if s.visivel(fatos, tier)]


# ── fields, derived from the Pydantic models ────────────────────────────────


def _tipo(anotacao: Any) -> tuple[str, list[str] | None]:
    """(``texto`` | ``numero`` | ``booleano`` | ``escolha`` | ``lista`` | ``objeto``, options for ``escolha``)."""
    args = [a for a in get_args(anotacao) if a is not type(None)]
    origem = get_origin(anotacao)
    if origem is Literal:
        return "escolha", [str(a) for a in get_args(anotacao)]
    if args and origem is not list and origem is not dict:  # Optional[X] / X | None
        return _tipo(args[0])
    if origem is list:
        return "lista", None
    if origem is dict or anotacao is dict:
        return "objeto", None
    if anotacao is bool:
        return "booleano", None
    if anotacao in (int, float):
        return "numero", None
    return "texto", None


def _meta(info: FieldInfo, attr: str) -> Any:
    """The first ``attr`` constraint carried by the field's metadata (``max_length``, ``min_length``, ``pattern``,
    ``le``, ...), else None."""
    return next((getattr(m, attr) for m in info.metadata if getattr(m, attr, None) is not None), None)


def _campo(nome: str, info: FieldInfo) -> dict[str, Any]:
    tipo, opcoes = _tipo(info.annotation)
    padrao = None if info.is_required() else info.default
    return {
        "chave": nome,
        "rotulo": info.title or nome.replace("_", " ").capitalize(),
        "tipo": tipo,
        "obrigatorio": info.is_required(),
        "max_length": _meta(info, "max_length"),
        # The limits a form needs to block what the server would 422 (wizard validation reads them).
        "min_length": _meta(info, "min_length"),
        "pattern": _meta(info, "pattern"),
        "minimo": _meta(info, "ge"),
        "minimo_exclusivo": _meta(info, "gt"),
        "maximo": _meta(info, "le"),
        "padrao": padrao if isinstance(padrao, (str, int, float, bool)) else None,
        "opcoes": opcoes,
    }


def campos_de(modelo: type[BaseModel], *, so: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """The fields of ``modelo`` (all, or only ``so`` in that order)."""
    nomes = so if so is not None else tuple(n for n in modelo.model_fields if n != "lacunas")
    return [_campo(n, modelo.model_fields[n]) for n in nomes]


def _item_da_area(area: str) -> tuple[type[BaseModel], bool]:
    """(the model of ONE row of ``area``, whether the area is a list of rows) -- read from :data:`SAIDAS`."""
    saida = SAIDAS[area]
    for nome, info in saida.model_fields.items():
        if nome == "lacunas":
            continue
        if get_origin(info.annotation) is list:
            (item,) = get_args(info.annotation)
            return item, True
    return saida, False


def _enumeracao(area: str) -> dict[str, Any] | None:
    if area == "textos":
        grupos: dict[str, list[dict[str, Any]]] = {}
        for chave, spec in sorted(TEXTOS.items()):
            grupos.setdefault(spec.categoria, []).append(
                {"chave": chave, "obrigatoria": spec.obrigatoria, "aplica_a": spec.aplica_a,
                 "fixo_plataforma": spec.fixo_plataforma})
        return {"tipo": "chaves_por_categoria", "grupos": [{"categoria": c, "chaves": k} for c, k in grupos.items()]}
    if area == "ferramentas":
        return {"tipo": "opcoes", "opcoes": sorted(FERRAMENTAS_CONHECIDAS)}
    return None


def areas() -> list[dict[str, Any]]:
    out = []
    for ordem, area in enumerate(AREAS):
        item, multiplas = _item_da_area(area)
        titulo, descricao = AREA_ROTULOS[area]
        out.append({
            "id": area, "titulo": titulo, "descricao": descricao, "ordem": ordem,
            "multiplas_linhas": multiplas, "campos": campos_de(item), "enumeracao": _enumeracao(area),
            "secoes": [s.id for s in SECOES_PAGINA if s.area == area],
        })
    return out


# ── the creation wizard (10 short categorized steps) ────────────────────────


@dataclass(frozen=True)
class PassoAssistente:
    """One wizard step: its fields are ``(model, field)`` pairs of the create body -- ``plataforma`` =
    ``PlataformaAgentCreateRequest``, ``briefing`` = its ``briefing`` (``Briefing``). ``areas`` = the generation
    areas the step's answers feed (what the AI draft writes from them)."""

    id: str
    titulo: str
    categoria: Literal["quem", "como", "o_que", "fechamento"]
    descricao: str
    campos: tuple[tuple[str, str], ...] = ()
    areas: tuple[str, ...] = ()
    nota: str | None = None


PASSOS_ASSISTENTE: tuple[PassoAssistente, ...] = (
    PassoAssistente("identidade", "Identidade", "quem", "Nome, chave e uma linha sobre o agente.",
                    (("plataforma", "key"), ("plataforma", "nome"), ("plataforma", "descricao"))),
    PassoAssistente("papel", "Papel", "quem", "Para que o agente existe e quem ele atende.",
                    (("briefing", "objetivo"), ("briefing", "publico"), ("plataforma", "padrao_qualificacao"),
                     ("plataforma", "escopo_qualificacao")), areas=("secoes", "decisoes")),
    PassoAssistente("personalidade", "Personalidade e tom", "quem", "Como o agente fala.",
                    (("briefing", "tom_de_voz"), ("briefing", "idioma")), areas=("secoes", "textos")),
    PassoAssistente("conhecimento", "Conhecimento", "o_que", "Exemplos e material de referência.",
                    (("briefing", "exemplos"),), areas=("secoes", "skills"),
                    nota="Arquivos de conhecimento são enviados na página do agente, depois de criado."),
    PassoAssistente("ferramentas", "Ferramentas", "o_que", "O que o agente pode fazer além de conversar.",
                    areas=("ferramentas",),
                    nota="O rascunho gerado escolhe as ferramentas da lista conhecida; você revisa na página."),
    PassoAssistente("canais", "Canais", "como", "Onde o agente atende.",
                    (("briefing", "canal"), ("plataforma", "runtime"), ("plataforma", "owner_product")),
                    areas=("textos", "configuracoes")),
    PassoAssistente("regras", "Regras e limites", "como", "O que o agente nunca faz e quando passa para humano.",
                    (("briefing", "limites"),), areas=("secoes", "decisoes", "textos")),
    PassoAssistente("rotinas", "Rotinas", "como", "Retomadas, horários e encerramento.",
                    nota="Rotinas são ligadas nos Controles da instância de cada organização, após publicar."),
    PassoAssistente("revisao", "Revisão", "fechamento", "Confira as respostas antes de criar."),
    PassoAssistente("publicar", "Publicar", "fechamento", "Disponibilizar para as organizações e gerar o rascunho.",
                    (("plataforma", "instanciavel"), ("plataforma", "limite_usd")),
                    nota="Criar gera um RASCUNHO; publicar a versão passa pelo portão de avaliações."),
)

_MODELOS_ASSISTENTE: dict[str, type[BaseModel]] = {"plataforma": PlataformaAgentCreateRequest, "briefing": Briefing}


def passos_assistente() -> list[dict[str, Any]]:
    out = []
    for ordem, p in enumerate(PASSOS_ASSISTENTE):
        campos = []
        for modelo, nome in p.campos:
            c = _campo(nome, _MODELOS_ASSISTENTE[modelo].model_fields[nome])
            campos.append({**c, "modelo": modelo})
        out.append({
            "id": p.id, "titulo": p.titulo, "categoria": p.categoria, "descricao": p.descricao, "ordem": ordem,
            "campos": campos, "areas": list(p.areas), "nota": p.nota,
        })
    return out


# ── the endpoint body ───────────────────────────────────────────────────────


def construir_modelo(tier: str) -> dict[str, Any]:
    """``GET /api/studio/modelo``. The CONTENT areas + their sections are listed only for a platform-tier caller
    (D31: an agent's internals are superadmin-only; their very structure is platform IP); the wizard steps likewise
    (only platform admins create definitions)."""
    plataforma = tier == "plataforma"
    secoes = [
        {"id": s.id, "titulo": s.titulo, "grupo": s.grupo, "tier": s.tier, "origens": list(s.origens),
         "area": s.area, "exige": list(s.exige)}
        for s in SECOES_PAGINA
        if _TIER_ORDEM[tier] >= _TIER_ORDEM[s.tier]
    ]
    return {
        "versao": MODELO_VERSAO,
        "tier": tier,
        "conteudo_modo": "linhas",
        "origens": list(ORIGENS),
        "secoes": secoes,
        "areas": areas() if plataforma else [],
        "assistente": {"passos": passos_assistente()} if plataforma else None,
    }

