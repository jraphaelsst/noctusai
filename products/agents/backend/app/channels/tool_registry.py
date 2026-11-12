"""The channel tool registry and the Julia v2 toolset (CONTRACT §3.4 / §3.5).

**Schemas live in code, words live in rows.** :data:`TOOLS` maps a tool name to its strict argument model
(the JSON schema the provider sees is DERIVED from it, with no ``description`` anywhere). The description of
a tool and of each parameter -- and the label of each enum value -- is a row of
``agent_version_ferramentas`` (``descricao`` / ``parametros``), read from the compiled prompt's content
bundle. A tool whose row is missing or inactive is not offered; there is no default description.

**The model never names an org or a lead.** Every id a handler uses comes from the server-built
:class:`JuliaTurno`; every argument model forbids unknown fields.

**Gates (E2).** A refusal is typed (``codigo``), its wording is the row
``ferramenta.resultado.recusa.<codigo>``. Per turn the refusals and the tool errors are budgeted
(``canal_limites``): past the budget the toolset *stops* the turn (:attr:`LlmToolset.should_stop`) and the
caller applies the safe outcome (hand-off to the owner + a flagged event, or silence / the DB text).

* a tool tied to a skill (``obrigatoria_skill`` on the tool row, or ``obrigatoria_para`` of a shared skill) is
  NOT refused when the skill is closed: the server AUTO-LOADS it for this turn and the result carries the
  procedure (``procedimento_obrigatorio``); the tool's own business preconditions still apply;
* ``trecho`` not in the lead's own words; offering before ``pode_ofertar``; concluding before a
  ``conclusivo`` stage; reacting to a code never offered; identity asked before the standard says so.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal, Protocol, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from noctusai_lib.integrations.llm import ToolCall, ToolResult, ToolSpec

from app.channels import proveniencia as prov
from app.catalogos import CATALOGO_PADRAO, CatalogoDesconhecido, CatalogoIndisponivel, CatalogoOpcoes, ImoveisSwCatalogo, catalogo_para, chaves_de_catalogo
from app.catalogos.imoveis_sw import BUSCA_META as _BUSCA_META, consulta_sw as _consulta_sw  # noqa: F401  (re-exported: tests + eval)
from app.channels import texto_seguro
from app.clients.social_wiring import (
    JULIA_TOOL_TIMEOUT_SECONDS,
    JULIA_TOOL_UNAVAILABLE as _INDISPONIVEL,
    SocialWiringClient,
    registrar_solicitacao_titular,
)
from app.qualificacao.matcher import MIN_TRECHO, normalizar
from app.qualificacao.identificacao import TIPOS_DOCUMENTO, EncryptionNotConfigured, obrigatorios_do_padrao
from app.qualificacao.models import LeadSinais, VersaoPadrao
from app.qualificacao.service import ItemPerfil, QualificacaoService
from app.runtime.llm_runtime import LlmToolset
from app.studio.models import ConteudoBundle
from app.stores.skills_biblioteca import FERRAMENTAS_DE_ABERTURA
from app.stores.threads import OPT_OUT_MENSAGEM_MAX
from app.stores.thread_alertas import TIPOS_ALERTA
from app.studio.textos_registry import CODIGOS_RECUSA_OPCIONAIS, MOTIVO_INFO_INDISPONIVEL, MOTIVOS_HANDOFF

logger = logging.getLogger(__name__)

__all__ = [
    "OPT_OUT_PALAVRA_CHAVE",
    "OPT_OUT_PEDIDO_DO_LEAD",
    "aplicar_encerramento",
    "enriquecer_schema",
    "executar_handoff",
    "finalizar_conclusao",
    "construir_toolset",
    "MOTIVO_MAX_CHARS",
    "FERRAMENTAS_MODO_RESTRITO",
    "MOTIVOS_ENCERRAR",
    "MOTIVO_LEAD_PEDIU_PARAR",
    "TOOLS",
    "JuliaTurno",
    "SkillFonte",
    "SkillsComSpecs",
    "SkillsDaVersao",
    "TextoAusente",
    "ToolDef",
    "alertar_info_indisponivel",
    "make_channel_tools_factory",
    "montar_tool_specs",
    "obrigatorias_por_ferramenta",
    "sanitize_motivo",
    "schema_de",
    "tools_ofertaveis",
]

MOTIVO_MAX_CHARS = 280
#: An emergency alert keeps the thread open and closes it after this many minutes without a message (the owner's rule:
#: "stay open, point to the numbers and close after 10 min of inactivity; every interaction refreshes the timer").
#: NOC-REMEDIATE[inatividade-por-agente]: a per-agent window (agent/definition setting) replaces this constant -- 2026-11-10
EMERGENCIA_JANELA_MIN = 10
TIPO_ALERTA_EMERGENCIA = "emergencia"
#: ``sinalizar_alerta`` caps (migration 057 CHECKs).
ALERTA_DESCRICAO_MAX = 500
ALERTA_TRECHO_MAX = 500
#: The longest quote a data-subject request stores (the lead's own words; the SW record column is 500).
TRECHO_TITULAR_MAX = 300
#: The longest quote consent / opt-out evidence stores (matches the qualification ``trecho`` column).
TRECHO_EVIDENCIA_MAX = 160
#: Kinds of data-subject request (LGPD art. 18) the model may register; the label of each is a tool-row parameter.
TIPOS_SOLICITACAO_TITULAR = (
    "confirmacao", "acesso", "correcao", "eliminacao", "portabilidade", "revogacao_consentimento", "oposicao",
    "info_compartilhamento", "outro",
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
_ANGLE = re.compile(r"[<>]")


def sanitize_motivo(raw: object) -> str:
    """Plain text, single-spaced, no markup brackets, <= 280 chars; ``""`` when nothing usable is left
    (the caller then reads ``ferramenta.handoff.motivo_padrao`` -- there is no default in code)."""
    text = raw if isinstance(raw, str) else ""
    text = _ANGLE.sub("", _CONTROL.sub(" ", text))
    text = " ".join(text.split())
    text = texto_seguro.sem_contatos(text)  # staff-facing: no URL / phone / e-mail / @-mention from the lead's words
    if len(text) > MOTIVO_MAX_CHARS:
        text = text[: MOTIVO_MAX_CHARS - 1].rstrip() + "…"
    return text


def _limpo(raw: object, max_chars: int) -> str | None:
    """Same normalisation as :func:`sanitize_motivo` with its own cap; ``None`` when nothing is left."""
    t = raw if isinstance(raw, str) else ""
    t = texto_seguro.sem_contatos(" ".join(_ANGLE.sub("", _CONTROL.sub(" ", t)).split()))
    return ((t[: max_chars - 1].rstrip() + "…") if len(t) > max_chars else t) or None


# ── argument models (the schemas) ───────────────────────────────────────────


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Valor = Union[str, int, float, bool, list[str], dict[str, float]]


class AbrirSkillArgs(_Args):
    nome: str = Field(min_length=1, max_length=64)


class LerArquivoSkillArgs(_Args):
    nome: str = Field(min_length=1, max_length=64)
    caminho: str = Field(min_length=1, max_length=255)


class AvaliarLeadArgs(_Args):
    pass


class ItemPerfilArgs(_Args):
    criterio: str = Field(min_length=1, max_length=64)
    valor: Valor
    trecho: str | None = Field(default=None, max_length=160)


class RegistrarPerfilArgs(_Args):
    itens: list[ItemPerfilArgs] = Field(min_length=1, max_length=10)


class OferecerImoveisArgs(_Args):
    modo: Literal["campanha", "similares"]
    limite: int | None = Field(default=None, ge=1, le=5)


class DetalhesImovelArgs(_Args):
    codigo: str = Field(min_length=1, max_length=64)


class OferecerOpcoesArgs(_Args):
    #: ``origem`` = the option the lead arrived with; ``similares`` = a search by the lead's profile.
    modo: Literal["origem", "similares"]
    limite: int | None = Field(default=None, ge=1, le=5)


class DetalhesOpcaoArgs(_Args):
    codigo: str = Field(min_length=1, max_length=64)


class RegistrarReacaoOpcaoArgs(_Args):
    codigo: str = Field(min_length=1, max_length=64)
    reacao: Literal["gostou", "nao_gostou", "quer_ver_mais"]
    motivo: str | None = Field(default=None, max_length=200)


class ConsultarEmpreendimentoArgs(_Args):
    nome: str = Field(min_length=1, max_length=120)


class RegistrarReacaoImovelArgs(_Args):
    codigo: str = Field(min_length=1, max_length=64)
    reacao: Literal["gostou", "nao_gostou", "quer_ver_mais"]
    motivo: str | None = Field(default=None, max_length=200)


class RegistrarIntencaoVisitaArgs(_Args):
    codigo: str = Field(min_length=1, max_length=64)
    preferencia_horario: str | None = Field(default=None, max_length=120)


class RegistrarIdentificacaoArgs(_Args):
    campo: Literal["nome", "email", "cpf", "rg"]
    valor: str = Field(min_length=1, max_length=120)


class RegistrarDocumentoArgs(_Args):
    #: The inbound lead message that carried the photo / scan (a ``midia`` of tipo imagem or documento).
    provider_message_id: str = Field(min_length=1, max_length=256)
    tipo_provavel: Literal[*TIPOS_DOCUMENTO]


class SinalizarAlertaArgs(_Args):
    tipo: Literal[*TIPOS_ALERTA]
    descricao: str = Field(min_length=1, max_length=ALERTA_DESCRICAO_MAX)
    trecho: str | None = Field(default=None, max_length=ALERTA_TRECHO_MAX)


class ConcluirQualificacaoArgs(_Args):
    pass


class HandoffArgs(_Args):
    motivo_codigo: Literal[*MOTIVOS_HANDOFF]
    motivo: str | None = Field(default=None, max_length=MOTIVO_MAX_CHARS)


MOTIVOS_ENCERRAR = ("lead_encerrou", "sem_interesse", "invalido", "outro", "lead_pediu_parar")
#: The ``encerrar`` motive that is also a LEAD-level opt-out (every agent stops, the owner is told).
MOTIVO_LEAD_PEDIU_PARAR = "lead_pediu_parar"


class EncerrarArgs(_Args):
    motivo: Literal[*MOTIVOS_ENCERRAR]
    #: Why, in a few words (required for ``lead_pediu_parar``: it is the owner's record of the opt-out).
    motivo_texto: str | None = Field(default=None, max_length=MOTIVO_MAX_CHARS)
    #: ``lead_pediu_parar`` only: the lead's own words (from THIS turn's batch) asking to stop. The opt-out is
    #: immediate and lead-wide, so it needs evidence the lead said it just now.
    trecho: str | None = Field(default=None, max_length=TRECHO_EVIDENCIA_MAX)


class CaptacaoArgs(_Args):
    descricao: str = Field(min_length=1, max_length=1000)
    endereco: str | None = Field(default=None, max_length=300)
    operacao: Literal["venda", "aluguel"] | None = None


class ConsentimentoCreditoArgs(_Args):
    aceito: bool
    #: The lead's own words (from THIS turn's batch) that answer the credit-analysis consent question.
    trecho: str = Field(min_length=1, max_length=TRECHO_EVIDENCIA_MAX)


class RegistrarSolicitacaoTitularArgs(_Args):
    tipo: Literal[*TIPOS_SOLICITACAO_TITULAR]
    #: The lead's own words (from THIS turn's batch) that make the request.
    trecho: str = Field(min_length=1, max_length=TRECHO_TITULAR_MAX)


@dataclass(frozen=True)
class ToolDef:
    nome: str
    args: type[BaseModel]
    #: Capabilities the turn must have for the tool to be offered at all.
    exige: frozenset[str] = frozenset()


#: The registry. Order = the order the tools are offered in (deterministic, cache-friendly).
TOOLS: dict[str, ToolDef] = {t.nome: t for t in (
    ToolDef("abrir_skill", AbrirSkillArgs, frozenset({"skills"})),
    ToolDef("ler_arquivo_skill", LerArquivoSkillArgs, frozenset({"skills"})),
    ToolDef("avaliar_lead", AvaliarLeadArgs, frozenset({"qualificacao"})),
    ToolDef("registrar_perfil", RegistrarPerfilArgs, frozenset({"qualificacao"})),
    ToolDef("oferecer_imoveis", OferecerImoveisArgs, frozenset({"qualificacao", "sw"})),
    ToolDef("detalhes_imovel", DetalhesImovelArgs, frozenset({"qualificacao", "sw"})),
    ToolDef("consultar_empreendimento", ConsultarEmpreendimentoArgs, frozenset({"sw"})),
    ToolDef("registrar_reacao_imovel", RegistrarReacaoImovelArgs, frozenset({"qualificacao"})),
    # the catalogue-neutral counterparts (081). ``catalogo`` is a runtime capability (the standard names a catalogue the
    # turn can build) the readiness derivation never grants, so they are never "expected" of an agent that did not opt in
    ToolDef("oferecer_opcoes", OferecerOpcoesArgs, frozenset({"qualificacao", "catalogo"})),
    ToolDef("detalhes_opcao", DetalhesOpcaoArgs, frozenset({"qualificacao", "catalogo"})),
    ToolDef("registrar_reacao_opcao", RegistrarReacaoOpcaoArgs, frozenset({"qualificacao", "catalogo"})),
    ToolDef("registrar_intencao_visita", RegistrarIntencaoVisitaArgs, frozenset({"qualificacao"})),
    ToolDef("registrar_identificacao", RegistrarIdentificacaoArgs, frozenset({"identificacao"})),
    ToolDef("registrar_documento", RegistrarDocumentoArgs, frozenset({"identificacao", "documentos"})),
    ToolDef("concluir_qualificacao", ConcluirQualificacaoArgs, frozenset({"qualificacao"})),
    ToolDef("handoff", HandoffArgs),
    ToolDef("encerrar", EncerrarArgs),
    ToolDef("captacao", CaptacaoArgs),
    ToolDef("consentimento_credito", ConsentimentoCreditoArgs, frozenset({"credito"})),
    ToolDef("registrar_solicitacao_titular", RegistrarSolicitacaoTitularArgs),
    ToolDef("sinalizar_alerta", SinalizarAlertaArgs, frozenset({"alertas"})),
)}

_STRIP = ("title", "default")


def _inline(node: Any, defs: Mapping[str, Any]) -> Any:
    """JSON schema with ``$ref``/``$defs`` resolved, ``title``/``default`` dropped (no prose from code)."""
    if isinstance(node, list):
        return [_inline(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _inline(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
    return {k: _inline(v, defs) for k, v in node.items() if k not in _STRIP and k != "$defs"}


def _valores_enum(sub: Mapping[str, Any]) -> list[Any]:
    """The enum values of a property, also when it is OPTIONAL: pydantic renders ``Literal[...] | None`` as
    ``anyOf: [{enum: [...]}, {type: null}]``, where a bare ``sub["enum"]`` sees nothing and the labels of the
    values would silently never reach the model."""
    if sub.get("enum"):
        return list(sub["enum"])
    out: list[Any] = []
    for ramo in (sub.get("anyOf") or sub.get("oneOf") or []):
        if isinstance(ramo, Mapping):
            out += [v for v in (ramo.get("enum") or []) if v not in out]
    return out


def enriquecer_schema(node: Any, parametros: Mapping[str, Any], caminho: str = "") -> None:
    """Write the row's parameter descriptions into the schema: ``parametros["a"]`` for property ``a``,
    ``parametros["a.b"]`` for ``b`` inside ``a``'s items; each enum value contributes
    ``parametros["a.<valor>"]`` (its label), appended to the property's description."""
    if not isinstance(node, dict):
        return
    for nome, sub in (node.get("properties") or {}).items():
        cam = f"{caminho}.{nome}" if caminho else nome
        alvo = sub.get("items") if sub.get("type") == "array" and isinstance(sub.get("items"), dict) else None
        partes = []
        base = parametros.get(cam)
        if isinstance(base, str) and base.strip():
            partes.append(base.strip())
        valores = _valores_enum(sub)
        rotulos = [f"{v}: {parametros[f'{cam}.{v}'].strip()}" for v in valores
                   if isinstance(parametros.get(f"{cam}.{v}"), str) and parametros[f"{cam}.{v}"].strip()]
        if rotulos:
            partes.append("; ".join(rotulos))
        if partes:
            sub["description"] = " ".join(partes)
        enriquecer_schema(sub, parametros, cam)
        if alvo is not None:
            enriquecer_schema(alvo, parametros, cam)


def schema_de(nome: str, parametros: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The provider-facing JSON schema of tool ``nome`` (parameter words from ``parametros``)."""
    raw = TOOLS[nome].args.model_json_schema()
    schema = _inline(raw, raw.get("$defs", {}))
    schema.setdefault("properties", {})
    schema["additionalProperties"] = False
    if parametros:
        enriquecer_schema(schema, parametros)
    return schema


#: The whole toolset of a ``modo_restrito`` turn (spec B4): hand over to a person, stop, or read the standing.
FERRAMENTAS_MODO_RESTRITO = frozenset({"handoff", "encerrar", "avaliar_lead"})


def tools_ofertaveis(conteudo: ConteudoBundle, capacidades: frozenset[str]) -> list[Any]:
    """The tool ROWS the turn may offer: active ∩ registry ∩ capabilities, in registry order. ``modo_restrito``
    in the capabilities narrows the set to :data:`FERRAMENTAS_MODO_RESTRITO` (a marker, never a grant)."""
    por_nome = {f.ferramenta: f for f in conteudo.ferramentas if f.ativo and (f.descricao or "").strip()}
    restrito = "modo_restrito" in capacidades
    return [
        por_nome[n] for n, d in TOOLS.items()
        if n in por_nome and d.exige <= capacidades and (not restrito or n in FERRAMENTAS_MODO_RESTRITO)
    ]


def montar_tool_specs(conteudo: ConteudoBundle, capacidades: frozenset[str]) -> tuple[ToolSpec, ...]:
    return tuple(
        ToolSpec(name=f.ferramenta, description=f.descricao.strip(), parameters=schema_de(f.ferramenta, f.parametros))
        for f in tools_ofertaveis(conteudo, capacidades)
    )


def obrigatorias_por_ferramenta(
    conteudo: ConteudoBundle, skill_obrigatoria_para: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, tuple[str, ...]]:
    """tool -> skills that must have been opened first. Two sources: the tool row's ``obrigatoria_skill``
    and the shared library's per-skill ``obrigatoria_para`` (A-SKILLS; any mapping skill -> tools)."""
    out: dict[str, list[str]] = {}
    for f in conteudo.ferramentas:
        if f.ativo and f.obrigatoria_skill:
            out.setdefault(f.ferramenta, []).append(f.obrigatoria_skill)
    for skill, tools in (skill_obrigatoria_para or {}).items():
        for t in tools:
            if t in FERRAMENTAS_DE_ABERTURA:
                # Gating the skill-opening tools would make the skill unopenable; the PUT refuses them
                # (422), this keeps a legacy row from ever deadlocking a live thread.
                logger.warning("agents.channel.gate_ignorado skill=%s ferramenta=%s", skill, t)
                continue
            if skill not in out.setdefault(t, []):
                out[t].append(skill)
    return {k: tuple(v) for k, v in out.items()}


# ── skills (port of studio/tools.py to the provider-neutral runtime, D7) ───


class SkillFonte(Protocol):
    """Where the turn's skills come from. The default reads the version's own skills; A-SKILLS' shared,
    pinned library is another implementation of the same three calls."""

    async def abrir(self, nome: str) -> dict[str, Any]: ...

    async def ler_arquivo(self, nome: str, caminho: str) -> dict[str, Any]: ...

    def obrigatoria_para(self) -> Mapping[str, Sequence[str]]:
        """skill -> the tools it must be opened before (``obrigatoria_para``)."""
        ...


class SkillsDaVersao:
    """The version's skills through the SAME read-only handlers the studio chat uses
    (``app.studio.tools.studio_tool_specs`` -- no SDK, org/version bound server-side)."""

    def __init__(self, definitions: Any, org_id: UUID, agent_id: UUID, version_id: UUID) -> None:
        from app.studio.tools import studio_tool_specs

        specs = studio_tool_specs(
            org_id=org_id, agent_id=agent_id, version_id=version_id, knowledge_enabled=False,
            definitions=definitions, knowledge=None,
        )
        self._handlers = {s.name: s.handler for s in specs}

    async def _chamar(self, nome: str, args: dict[str, Any]) -> dict[str, Any]:
        out = await self._handlers[nome](args)
        return json.loads(out["content"][0]["text"])

    async def abrir(self, nome: str) -> dict[str, Any]:
        return await self._chamar("abrir_skill", {"nome": nome})

    async def ler_arquivo(self, nome: str, caminho: str) -> dict[str, Any]:
        return await self._chamar("ler_arquivo_skill", {"nome": nome, "caminho": caminho})

    def obrigatoria_para(self) -> Mapping[str, Sequence[str]]:
        return {}


class SkillsComSpecs:
    """A :class:`SkillFonte` whose texts are resolved FOR THIS ORG: every ``{{org.chave}}`` in a skill's index line,
    body or reference file is replaced by the org's value with the SAME resolver the prompt sections use
    (:func:`app.studio.especificacoes.resolver_texto`), at the moment the model opens it. The definition stays one
    for every org; what an org's model reads is that org's text (CONTRACT §2.6, Q2)."""

    _CAMPOS = ("descricao", "corpo", "conteudo", "titulo")

    def __init__(self, inner: SkillFonte, valores: Mapping[str, str], fenced: Collection[str] = ()) -> None:
        self._inner = inner
        self._valores = dict(valores)
        #: free-text keys: ``[dado: chave]`` here, the value only in the prompt's data section (Julia-line E3)
        self._fenced = frozenset(fenced)

    def _resolver(self, out: dict[str, Any]) -> dict[str, Any]:
        from app.studio.especificacoes import resolver_texto

        if out.get("erro"):
            return out
        return {k: (resolver_texto(v, self._valores, self._fenced) if k in self._CAMPOS and isinstance(v, str) else v)
                for k, v in out.items()}

    async def abrir(self, nome: str) -> dict[str, Any]:
        return self._resolver(await self._inner.abrir(nome))

    async def ler_arquivo(self, nome: str, caminho: str) -> dict[str, Any]:
        return self._resolver(await self._inner.ler_arquivo(nome, caminho))

    def obrigatoria_para(self) -> Mapping[str, Sequence[str]]:
        return self._inner.obrigatoria_para()


# ── the per-turn state ──────────────────────────────────────────────────────


class TextoAusente(Exception):
    """A text the turn needs is blank. ``conteudo_status`` refuses the turn before this can happen for a
    required key; reaching it means a registry/prompt mismatch and is a bug to see, never a default."""


@dataclass
class JuliaTurno:
    """Everything one channel turn's tools act on, built by the route (server side) and handed to the
    runtime through ``TurnContext.julia``. Mutable on purpose: it is the turn's ledger."""

    org_id: UUID
    agent_id: UUID
    agent_key: str
    thread_id: UUID
    lead_ref_id: UUID
    conteudo: ConteudoBundle
    compiled_hash: str
    padrao: VersaoPadrao
    qual: QualificacaoService
    threads: Any
    skills: SkillFonte | None
    sw: SocialWiringClient | None
    ident: Any | None
    #: Persistent hand-off bookkeeping (the owner is the default operator).
    handoff_destino: Any
    limites: Any
    mensagens_lead: list[str]
    sinais: LeadSinais
    escopo: str | None = None
    #: ``contexto.estado`` (interacao_id, origem, credito) -- the operational facts SW sent.
    estado_sw: Any | None = None
    ferramentas_sw: bool = True
    #: A catalogue that REPLACES the one the standard names (the eval world's synthetic one); ``None`` = the standard's.
    catalogo_fixo: Any | None = None
    # ── the turn's ledger ──
    actions: list[dict[str, Any]] = field(default_factory=list)
    recusas: int = 0
    erros: int = 0
    #: Skills whose procedure the model has read IN THIS TURN (auto-loaded by the first call of a tool tied to it, or
    #: opened with ``abrir_skill``). Turn-scoped on purpose: a thread-level flag outlives the context that held the text.
    skills_carregadas: set[str] = field(default_factory=set)
    #: Refusals / errors / calls spent by attempts BEFORE the current one (a corrective re-run starts clean).
    recusas_anteriores: int = 0
    #: Prompt-derived text tools handed to the model THIS turn (skill bodies / files, rendered for the org): added to the
    #: leak fingerprint, because a skill reaches the model as a tool result, outside the compiled text. Kept across re-runs.
    textos_derivados: list[str] = field(default_factory=list)
    parar: str | None = None  # the motivo_codigo of the safe stop (limite_recusas / falhas_repetidas)
    registrou_criterios: set[str] = field(default_factory=set)
    links_vistos: set[str] = field(default_factory=set)
    #: The (successful) tool results of THIS turn as the model read them: the only figures (R$ / %) a reply may repeat
    #: besides the lead's own words (``valor_sem_ferramenta``).
    resultados_texto: list[str] = field(default_factory=list)
    codigos_vistos: set[str] = field(default_factory=set)
    #: The CPF / RG just registered this turn (normalised) -- the turn masks them in the thread's stored rows once it
    #: settles (guardrails B8.4). Memory only: never serialised, never in a repr.
    identificacoes_registradas: list[str] = field(default_factory=list, repr=False)
    #: Any identification field (name / e-mail / CPF / RG) was registered this turn: the turn response flag.
    identificacao_registrada: bool = False
    transferiu: bool = False
    #: a ``registrar_intencao_visita`` call succeeded this turn (also when the intention was already on record)
    visita_registrada: bool = False
    encerrou: bool = False
    concluiu: bool = False
    resumo_handoff: str | None = None
    #: The texts of the lead batch THIS turn answers (empty for a re-engagement): the lead's own words the
    #: ``encerrar`` opt-out record quotes.
    lote_lead: list[str] = field(default_factory=list)
    #: :class:`app.channels.opt_out.OptOutService` -- the lead-level opt-out + the owner's notice.
    opt_out: Any | None = None
    #: Security escalation (spec B4): the abuse counter crossed ``limiar_suspeito`` -- only
    #: :data:`FERRAMENTAS_MODO_RESTRITO` are offered. Set by the route from DATA; it can only REMOVE tools.
    modo_restrito: bool = False
    #: Spec B3.6: ``text -> True`` when the text reproduces the prompt (canary / fingerprint); ``None`` = off.
    guarda_campos: Callable[[str], bool] | None = None
    #: ``tool.field`` codes of the lead-influenced arguments replaced this turn (codes only, never the text).
    campos_substituidos: list[str] = field(default_factory=list)
    #: The turn's honeytoken and how many tool calls carried it in their RAW arguments (counted before the staff-facing
    #: sanitisers run: a random hex marker can contain a digit run ``sem_contatos`` reads as a phone and strips).
    marcador: str | None = None
    chamadas_com_marcador: int = 0
    #: Julia v3 seams (all optional; ``None`` = the capability is off for this turn):
    #: ``agents.thread_alertas`` store (``sinalizar_alerta``).
    alertas: Any | None = None
    #: ``provider_message_id -> the midia dict`` of an INBOUND LEAD message of this thread, else ``None``
    #: (``registrar_documento`` validates the id against it).
    midia_da_mensagem: Callable[[str], dict[str, Any] | None] | None = None
    #: ``() -> narrative`` -- the ``/resumo`` generator for the report (CONTRACT §12.4); ``None`` = no LLM call
    #: (the report's ``resumo_conversa`` is then ``None`` by design, not a failure).
    resumo_conversa: Callable[[], Awaitable[str]] | None = None
    #: ``code -> None``: books a thread event (``area:codigo``), e.g. ``relatorio:degradado``.
    auditar: Callable[[str], None] | None = None
    #: The alert types already raised this turn (one per tipo per turn) -- the fast path of the store check.
    alertas_tipos: set[str] = field(default_factory=set)
    #: A "turn" for the alert dedupe starts after the thread's last assistant message (``None`` = the thread has
    #: none yet): an alert of the same tipo recorded in ``thread_alertas`` since then is a repeat, also when this
    #: turn is a re-run of a failed one (a fresh ``JuliaTurno`` has an empty in-memory set).
    alertas_desde: datetime | None = None
    #: property code -> the link SW's tool results carried this turn (the report prints it when known).
    links_por_codigo: dict[str, str] = field(default_factory=dict)
    #: The report built for this turn's hand-off / conclusion.
    relatorio: dict[str, Any] | None = None
    #: REQUIRED org specs with no value (the prompt carries the INDISPONIVEL sentinel for them): drives the alerts.
    specs_faltando: tuple[str, ...] = ()

    def proteger_args(self, nome: str, args: BaseModel) -> BaseModel:
        """The lead-influenced arguments that reach humans, scanned for the prompt: a hit replaces the field
        with the DB text ``ferramenta.campo_removido`` and is booked (code only) in ``campos_substituidos``."""
        from app.channels.conformidade import CAMPOS_PROTEGIDOS

        if self.guarda_campos is None:
            return args
        troca: dict[str, str] = {}
        for campo in CAMPOS_PROTEGIDOS.get(nome, ()):
            valor = getattr(args, campo, None)
            if isinstance(valor, str) and valor.strip() and self.guarda_campos(valor):
                troca[campo] = self.texto("ferramenta.campo_removido")
                self.campos_substituidos.append(f"{nome}.{campo}")
        return args.model_copy(update=troca) if troca else args
    #: The chat id on the lead's connection (``channel_ref.chat_id``): travels to SW with a data-subject request.
    chat_id: str | None = None
    #: Tool calls made this turn, total and per tool (the per-turn caps of ``canal_limites``).
    chamadas: int = 0
    chamadas_por_ferramenta: dict[str, int] = field(default_factory=dict)
    #: ``(regra, detalhe)`` signals a tool saw (codes only): ``injecao_ferramenta`` -- catalogue text that read like an
    #: extraction attempt. ``turno.executar`` records them as violations.
    sinais_ferramenta: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def texto(self, chave: str, **valores: object) -> str:
        bruto = self.conteudo.texto(chave)
        if not bruto.strip():
            raise TextoAusente(chave)
        for k, v in valores.items():
            bruto = bruto.replace("{" + k + "}", str(v))
        return bruto

    def capacidades(self) -> frozenset[str]:
        caps = {"qualificacao"}
        if self.modo_restrito:
            caps.add("modo_restrito")  # narrows the offer to FERRAMENTAS_MODO_RESTRITO (tools_ofertaveis)
        if self.skills is not None:
            caps.add("skills")
        if self.sw is not None and self.ferramentas_sw:
            caps.add("sw")
        if self.ident is not None:
            caps.add("identificacao")
            if self.midia_da_mensagem is not None:
                caps.add("documentos")
        if self.alertas is not None:
            caps.add("alertas")
        credito = getattr(self.estado_sw, "credito", None)
        if credito is not None and credito.ativo:
            caps.add("credito")
        chave = self.padrao.parametros.catalogo
        if self.catalogo_fixo is not None or (
            chave in chaves_de_catalogo() and (chave != "imoveis_sw" or "sw" in caps)
        ):
            caps.add("catalogo")  # the standard names a catalogue this turn can build: the generic offer tools may be offered
        return frozenset(caps)

    def no_lote(self, trecho: str | None, maximo: int) -> bool:
        """Is ``trecho`` (the lead's own words) in THIS turn's batch? Normalised containment, the batch's messages
        each alone or joined. An empty batch (a re-engagement turn) never holds evidence."""
        if not self.lote_lead or not isinstance(trecho, str) or len(trecho) > maximo:
            return False
        alvo = normalizar(trecho)
        if len(alvo) < MIN_TRECHO:
            return False
        janela = [m for m in (normalizar(x) for x in self.lote_lead) if m]
        return any(alvo in c for c in janela + ([" ".join(janela)] if len(janela) > 1 else []))

    def acao(self, **kw: Any) -> None:
        self.actions.append(dict(kw))

    def reiniciar_tentativa(self) -> None:
        """A corrective re-run is a NEW attempt: it starts with the refusal / error / call budgets and the loaded skills
        of a fresh turn (the model of the re-run has not read the first attempt's tool results), while what the first
        attempt DID (actions, offers, registered criteria) stays on the ledger."""
        self.recusas_anteriores += self.recusas
        self.recusas = 0
        self.erros = 0
        self.chamadas = 0
        self.chamadas_por_ferramenta.clear()
        self.skills_carregadas.clear()
        self.parar = None


#: The payload key carrying an auto-loaded skill's procedure, and its cap per skill.
PROCEDIMENTO = "procedimento_obrigatorio"
PROCEDIMENTO_MAX_CHARS = 4000


# ── result shaping ──────────────────────────────────────────────────────────


def _json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


@dataclass(frozen=True)
class _Resultado:
    payload: dict[str, Any]
    erro: bool = False  # a refusal or failure the model should read as one
    recusa: bool = False  # counts against the refusal budget
    falha: bool = False  # counts against the tool-error budget
    corrigivel: bool = False  # a CORRECTABLE refusal (``RECUSAS_CORRIGIVEIS``): guidance, not counted in ``recusas``


def _ok(**payload: Any) -> _Resultado:
    return _Resultado({"ok": True, **payload})


def _msg_esgotado(t: Any) -> dict[str, str]:
    """The optional instruction row for an exhausted catalogue; a version without it keeps the bare ``esgotado`` flag."""
    try:
        return {"mensagem": t.texto("ferramenta.resultado.esgotado")}
    except TextoAusente:  # optional row the version has not written
        return {}


#: Refusal classes. CORRECTABLE = a procedural precondition the model can satisfy by a DIFFERENT call in the same turn
#: (open the skill, use the search mode when there is no campaign code, offer before reacting): guidance, not abuse, so it
#: does not spend ``max_recusas_por_turno`` -- the per-tool / per-turn call caps still bound a loop of them.
#: COUNTED = everything else (evidence mismatch, forged/forbidden/abusive calls, caps, anything unclassified: fail-closed).
#: Every code literal of this module (and ``CODIGOS_RECUSA``) sits in exactly one of the two (tested).
RECUSAS_CORRIGIVEIS: frozenset[str] = frozenset({
    "skill_inexistente", "arquivo_inexistente", "sem_codigo_campanha", "imovel_nao_oferecido",
    "sem_origem", "opcao_nao_oferecida",
})
RECUSAS_CONTADAS: frozenset[str] = frozenset({
    "sem_itens", "itens_demais", "versao_nao_publicada", "fonte_invalida", "criterio_repetido", "criterio_derivado",
    "criterio_desconhecido", "nao_coletar", "fora_do_escopo", "valor_invalido", "opcao_invalida", "usar_identificacao",
    "trecho_ausente", "trecho_longo", "trecho_curto", "trecho_nao_confere", "evento_invalido", "origem_invalida",
    "codigo_invalido", "motivo_longo", "lote_invalido", "imovel_ja_oferecido", "estagio_nao_conclusivo",
    "nao_pode_ofertar", "limite_ofertas", "identificacao_nao_devida", "campo_desconhecido", "valor_nao_confere",
    "identificacao_indisponivel", "credito_inativo", "limite_recusas", "indisponivel", "motivo_texto_ausente",
    "consentimento_sem_evidencia", "opt_out_sem_evidencia", "limite_ferramentas", "argumentos_invalidos",
    "documento_nao_encontrado", "documento_sem_midia", "emergencia_aberta", "opcao_ja_oferecida",
})


def classe_recusa(codigo: str) -> str:
    """``corrigivel`` only for a code explicitly listed so; anything else (incl. unknown) is ``contada``."""
    return "corrigivel" if codigo in RECUSAS_CORRIGIVEIS else "contada"


def _recusa(t: JuliaTurno, codigo: str, **extra: Any) -> _Resultado:
    """A typed refusal; the wording is the row ``ferramenta.resultado.recusa.<codigo>``."""
    sub = {"skill": extra["skill"]} if "skill" in extra else {}
    try:
        msg = t.texto(f"ferramenta.resultado.recusa.{codigo}", **sub)
    except TextoAusente:
        if codigo not in CODIGOS_RECUSA_OPCIONAIS:
            raise
        msg = codigo  # an optional row not written yet: the bare code, never prose from code
    return _Resultado({"ok": False, "codigo": codigo, "mensagem": msg, **{k: v for k, v in extra.items() if k != "skill"}},
                      erro=True, recusa=True, corrigivel=codigo in RECUSAS_CORRIGIVEIS)


def _falha_sw(t: JuliaTurno) -> _Resultado:
    return _Resultado(
        {"ok": False, "codigo": "indisponivel", "mensagem": t.texto("ferramenta.resultado.recusa.indisponivel")},
        erro=True, falha=True,
    )


# ── the toolset factory ─────────────────────────────────────────────────────


def _pedaco_link(item: Any) -> str | None:
    link = item.get("link") if isinstance(item, dict) else None
    return link if isinstance(link, str) and link.strip() else None


def _link_do_evento(link: object) -> str | None:
    """The link stored on an ``oferecido`` event (``motivo`` is capped at 200); ``None`` when absent or too long."""
    return link if isinstance(link, str) and link.startswith(("http://", "https://")) and len(link) <= 200 else None


#: The generic offer tool forwards only these sibling facts of a catalogue answer (the contract of ``oferecer_opcoes``).
_META_OPCOES = ("relaxado", "itens_nao_verificaveis")
#: The real-estate refusal codes the generic tools answer under their catalogue-neutral names.
_ALIAS_OPCAO = {"imovel_ja_oferecido": "opcao_ja_oferecida", "imovel_nao_oferecido": "opcao_nao_oferecida"}


def _codigo_recusa(codigo: str | None, generico: bool, padrao: str = "evento_invalido") -> str:
    """The refusal code of an event the service refused, in the vocabulary of the tool that asked."""
    c = codigo or padrao
    return _ALIAS_OPCAO.get(c, c) if generico else c


def make_channel_tools_factory(**_unused: Any):
    """``(spec, ctx) -> LlmToolset | None`` for the provider-neutral runtime.

    A channel turn carries a :class:`JuliaTurno` in ``ctx.julia``; without one (the studio test chat, an
    eval case) there are no channel tools. Keyword arguments are accepted and ignored so the pre-v2 call
    sites (``make_channel_tools_factory(collector, ...)``) keep composing while they are migrated."""

    def _factory(spec: Any, ctx: Any) -> LlmToolset | None:
        t: JuliaTurno | None = getattr(ctx, "julia", None)
        if t is None:
            return None
        return construir_toolset(t)

    return _factory


def construir_toolset(t: JuliaTurno) -> LlmToolset:
    caps = t.capacidades()
    specs = montar_tool_specs(t.conteudo, caps)
    oferecidas = {s.name for s in specs}
    obrig = obrigatorias_por_ferramenta(
        t.conteudo, t.skills.obrigatoria_para() if t.skills is not None else None)
    if "modo_restrito" in caps:  # skills are not offered here: a skill gate must not lock the way out to a person
        obrig = {}

    async def _recusar_args(nome: str, exc: ValidationError) -> _Resultado:
        campos = ", ".join(sorted({".".join(str(p) for p in e["loc"]) or "args" for e in exc.errors()}))
        return _Resultado(
            {"ok": False, "codigo": "argumentos_invalidos",
             "mensagem": t.texto("ferramenta.resultado.argumentos_invalidos", motivo=campos)},
            erro=True, recusa=True)

    def _mensagens_lead() -> list[str]:
        return t.mensagens_lead

    # ── qualification tools ──
    async def _avaliar() -> _Resultado:
        e = await asyncio.to_thread(t.qual.avaliar, t.org_id, t.lead_ref_id, _versao_id(), t.escopo, t.sinais)
        payload = e.avaliar_payload()
        if "nome" in payload.get("identificacao_desejada", ()) and await _contato_tem_nome():
            payload["identificacao_desejada"] = [k for k in payload["identificacao_desejada"] if k != "nome"]
        return _ok(**payload)

    async def _contato_tem_nome() -> bool:
        """The name came with the contact (the Meta form): it counts as present -- Julia never asks it, unless she
        judges it a business name and registers the person's own (``registrar_identificacao`` campo=nome)."""
        lead = await asyncio.to_thread(t.threads.get_lead_ref, t.org_id, t.lead_ref_id)
        return bool((getattr(lead, "contato", None) or {}).get("nome"))

    def _versao_id() -> UUID:
        assert t.padrao.id is not None
        return t.padrao.id

    async def _registrar_perfil(a: RegistrarPerfilArgs) -> _Resultado:
        itens = [ItemPerfil(i.criterio, i.valor, i.trecho) for i in a.itens]
        r = await asyncio.to_thread(
            t.qual.registrar_perfil, t.org_id, t.lead_ref_id, agent_id=t.agent_id, versao_id=_versao_id(),
            itens=itens, mensagens_lead=_mensagens_lead(), thread_id=t.thread_id, escopo=t.escopo, sinais=t.sinais,
        )
        if r.codigo:  # batch-level refusal
            return _recusa(t, r.codigo)
        t.registrou_criterios.update(r.aceitos)
        t.registrou_criterios.update(r.inalterados)
        payload = r.to_payload()
        payload["recusados"] = [
            {"criterio": x.criterio, "codigo": x.codigo, "mensagem": t.texto(f"ferramenta.resultado.recusa.{x.codigo}")}
            for x in r.recusados
        ]
        payload.pop("codigo", None)
        return _Resultado(payload, erro=bool(r.recusados), recusa=bool(r.recusados))

    async def _evento(
        codigo: str, evento: str, origem: str, motivo: str | None = None, lote: int | None = None,
        catalogo: str = CATALOGO_PADRAO,
    ) -> Any:
        return await asyncio.to_thread(
            t.qual.registrar_evento_imovel, t.org_id, t.lead_ref_id, agent_id=t.agent_id,
            versao_id=_versao_id(), codigo_imovel=codigo, evento=evento, origem=origem, lote=lote, motivo=motivo,
            thread_id=t.thread_id, escopo=t.escopo, sinais=t.sinais, catalogo=catalogo,
        )

    async def _origem_oferta(codigo: str, catalogo: str = CATALOGO_PADRAO) -> str:
        eventos = await asyncio.to_thread(t.qual.eventos, t.org_id, t.lead_ref_id)
        for e in eventos:
            if e.codigo_imovel == codigo and e.evento == "oferecido" and e.catalogo == catalogo:
                return e.origem
        return "similar"

    async def _reacao_nucleo(
        codigo: str, reacao: str, motivo: str | None, *, catalogo: str, generico: bool,
    ) -> _Resultado:
        """One reaction of the lead to an offered option: the event the qualification engine reads (``gostou`` /
        ``nao_gostou`` / ``quer_ver_mais``). The real-estate and the generic tool share it; only the refusal names differ."""
        origem = await _origem_oferta(codigo, catalogo)
        r = await _evento(codigo, reacao, origem, _limpo(motivo, 200), catalogo=catalogo)
        if not r.ok:
            return _recusa(t, _codigo_recusa(r.codigo, generico))
        return _ok(inalterado=r.inalterado)

    async def _reacao(a: RegistrarReacaoImovelArgs) -> _Resultado:
        return await _reacao_nucleo(a.codigo, a.reacao, a.motivo, catalogo=CATALOGO_PADRAO, generico=False)

    async def _reacao_opcao(a: RegistrarReacaoOpcaoArgs) -> _Resultado:
        return await _reacao_nucleo(a.codigo, a.reacao, a.motivo, catalogo=_catalogo_do_turno().chave, generico=True)

    async def _visita(a: RegistrarIntencaoVisitaArgs) -> _Resultado:
        origem = await _origem_oferta(a.codigo)
        pref = _limpo(a.preferencia_horario, 120)
        # the lead's OWN availability rides on the event (``motivo``): the report reads it back on a later turn
        r = await _evento(a.codigo, "quer_visitar", origem, pref)
        if not r.ok:
            return _recusa(t, r.codigo or "evento_invalido")
        t.visita_registrada = True
        if not r.inalterado:
            t.acao(type="intencao_visita", codigo=a.codigo, preferencia_horario=pref)
        return _ok(inalterado=r.inalterado, mensagem=t.texto("ferramenta.resultado.registrado"))

    async def _identificar(a: RegistrarIdentificacaoArgs) -> _Resultado:
        estado = await asyncio.to_thread(t.qual.avaliar, t.org_id, t.lead_ref_id, _versao_id(), t.escopo, t.sinais)
        # the NAME is not sensitive and the form's may be a business name: it is registrable at any point
        if a.campo != "nome" and not estado.pedir_identificacao:
            return _recusa(t, "identificacao_nao_devida")
        obrigatorios = obrigatorios_do_padrao(t.padrao.criterios)
        try:
            r = await asyncio.to_thread(
                t.ident.registrar_identificacao, t.org_id, t.lead_ref_id, agent_id=t.agent_id, campo=a.campo,
                valor=a.valor, mensagens_lead=_mensagens_lead(), obrigatorios=obrigatorios,
            )
        except EncryptionNotConfigured:
            logger.error("agents.channel.identificacao_indisponivel org_id=%s", t.org_id)
            return _Resultado(
                {"ok": False, "codigo": "identificacao_indisponivel",
                 "mensagem": t.texto("ferramenta.resultado.recusa.identificacao_indisponivel")},
                erro=True, falha=True)
        if r.status != "registrado":
            return _recusa(t, r.codigo or "valor_invalido")
        t.identificacao_registrada = True
        if r.valor_registrado:
            t.identificacoes_registradas.append(r.valor_registrado)
        # NEVER the value: the field name, the status, what is still missing.
        return _ok(**r.to_payload())

    async def _documento(a: RegistrarDocumentoArgs) -> _Resultado:
        """The lead sent a photo / scan of an ID: the id must be an inbound LEAD message of this thread carrying
        imagem|documento media. Remembers THAT (the CPF counts as satisfied pending extraction); SW extracts."""
        assert t.ident is not None and t.midia_da_mensagem is not None
        midia = await asyncio.to_thread(t.midia_da_mensagem, a.provider_message_id)
        if midia is None:
            return _recusa(t, "documento_nao_encontrado")
        if midia.get("tipo") not in ("imagem", "documento"):
            return _recusa(t, "documento_sem_midia")
        estado = await asyncio.to_thread(t.qual.avaliar, t.org_id, t.lead_ref_id, _versao_id(), t.escopo, t.sinais)
        if not estado.pedir_identificacao:
            return _recusa(t, "identificacao_nao_devida")
        await asyncio.to_thread(
            t.ident.registrar_documento, t.org_id, t.lead_ref_id, agent_id=t.agent_id,
            tipo_provavel=a.tipo_provavel, provider_message_id=a.provider_message_id)
        t.identificacao_registrada = True
        if not any(x.get("type") == "documento_identificacao" and x.get("provider_message_id") == a.provider_message_id
                   for x in t.actions):
            t.acao(type="documento_identificacao", provider_message_id=a.provider_message_id,
                   tipo_provavel=a.tipo_provavel)
        faltando = await asyncio.to_thread(
            t.ident.faltando, t.org_id, t.lead_ref_id, obrigatorios_do_padrao(t.padrao.criterios))
        return _ok(mensagem=t.texto("ferramenta.resultado.registrado"), faltando=list(faltando))

    async def _alerta(a: SinalizarAlertaArgs) -> _Resultado:
        """Julia flags an unhappy lead / her own mistake / a drift. One alert per tipo per turn (a repeat is a
        no-op answered ok); SW turns the ``alerta`` action into a message to the report destination."""
        assert t.alertas is not None
        if a.tipo == TIPO_ALERTA_EMERGENCIA:
            # idempotent (also on a repeat / re-run): the thread stays open and the inactivity job closes it
            await asyncio.to_thread(
                t.threads.definir_janela_inatividade, t.org_id, t.thread_id, t.agent_id, EMERGENCIA_JANELA_MIN)
        if a.tipo in t.alertas_tipos:
            return _ok(inalterado=True, mensagem=t.texto("ferramenta.resultado.registrado"))
        previos = await asyncio.to_thread(t.alertas.listar, t.org_id, t.thread_id)
        if any(p.tipo == a.tipo and (t.alertas_desde is None or p.created_at >= t.alertas_desde) for p in previos):
            t.alertas_tipos.add(a.tipo)
            return _ok(inalterado=True, mensagem=t.texto("ferramenta.resultado.registrado"))
        # staff-facing (WhatsApp to the owner): a second-order injection channel -- no link / PIX / contact survives
        descricao = texto_seguro.para_equipe(a.descricao, maximo=ALERTA_DESCRICAO_MAX) or None
        if descricao is None:
            return _recusa(t, "valor_invalido")
        rec = await asyncio.to_thread(
            t.alertas.registrar, t.org_id, t.thread_id, t.agent_id, tipo=a.tipo, descricao=descricao,
            trecho=texto_seguro.para_equipe(a.trecho or "", maximo=ALERTA_TRECHO_MAX) or None)
        t.alertas_tipos.add(a.tipo)
        t.acao(type="alerta", tipo=a.tipo, descricao=descricao, alerta_id=str(rec.id))
        return _ok(mensagem=t.texto("ferramenta.resultado.registrado"))

    async def _concluir() -> _Resultado:
        r = await asyncio.to_thread(
            t.qual.pode_concluir, t.org_id, t.lead_ref_id, _versao_id(), t.escopo, t.sinais)
        if not r.ok:
            return _recusa(t, r.codigo or "estagio_nao_conclusivo")
        if not t.concluiu:
            await finalizar_conclusao(t, r.lead_pronto or {})
        return _ok(mensagem=t.texto("ferramenta.resultado.concluido"))

    # ── Sw-backed tools ──
    async def _sw(nome: str, args: dict[str, Any]) -> dict[str, Any] | None:
        assert t.sw is not None
        try:
            body = await asyncio.wait_for(t.sw.julia_ferramenta(t.org_id, nome, args), JULIA_TOOL_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 -- a tool failure is a result, never a crashed turn
            logger.warning("agents.channel.sw_tool_failed org_id=%s tool=%s error=%s", t.org_id, nome, type(exc).__name__)
            return None
        if not isinstance(body, dict) or body.get("erro"):
            return None
        return body

    def _interacao() -> dict[str, Any]:
        iid = getattr(t.estado_sw, "interacao_id", None)
        return {"interacao_id": str(iid)} if iid is not None else {}

    def _interacao_id() -> str | None:
        iid = getattr(t.estado_sw, "interacao_id", None)
        return str(iid) if iid is not None else None

    def _catalogo_do_turno() -> CatalogoOpcoes:
        """The catalogue the GENERIC tools read: the eval world's fixture, else the one the standard names. An unknown
        key or a missing client raises (loud) -- the handler answers ``indisponivel``, never another catalogue."""
        if t.catalogo_fixo is not None:
            return t.catalogo_fixo
        return catalogo_para(t.padrao.parametros.catalogo, sw=t.sw if t.ferramentas_sw else None)

    def _catalogo_ou_falha() -> CatalogoOpcoes | _Resultado:
        try:
            return _catalogo_do_turno()
        except (CatalogoDesconhecido, CatalogoIndisponivel) as exc:
            logger.error("agents.channel.catalogo_indisponivel org_id=%s agent_id=%s cause=%s", t.org_id, t.agent_id, exc)
            return _falha_sw(t)

    def _lembrar(item: Mapping[str, Any]) -> None:
        """What the reply may repeat about an offered option: its code and its link (conformance reads both)."""
        t.codigos_vistos.add(str(item["codigo"]).casefold())
        if (lk := _pedaco_link(item)) is not None:
            t.links_vistos.add(lk)
            t.links_por_codigo[str(item["codigo"])] = lk

    async def _oferecer_nucleo(
        catalogo: CatalogoOpcoes, *, de_origem: bool, limite_pedido: int | None, generico: bool,
    ) -> _Resultado:
        """Offer from ``catalogo``. ONE implementation for ``oferecer_imoveis`` (the real-estate catalogue) and
        ``oferecer_opcoes`` (any catalogue): they differ only in the names they speak -- refusal codes, the result's
        list key, and the option shape (``generico``)."""
        origem_codigo = catalogo.origem(t.estado_sw)
        ja = await asyncio.to_thread(
            t.qual.codigos_oferecidos, t.org_id, t.lead_ref_id, *((catalogo.chave,) if generico else ()))
        reenvio = False
        if de_origem:
            # The origin option (the ad's own property) is the ONE exception to ``pode_ofertar``: it opens the
            # conversation, before any qualification, and it is the lead's own interest, not a search result. The caps
            # still bind.
            if not origem_codigo:
                return _recusa(t, "sem_origem" if generico else "sem_codigo_campanha")
            # Already offered => the lead asks for it again (the link, "qual era o imóvel?"): resend the card and its
            # link, never ``esgotado`` -- an origin option is not a batch to exhaust. No new offer event, no cap use.
            reenvio = origem_codigo in ja
            if not reenvio and t.limites.max_imoveis_distintos - len(ja) <= 0:
                return _recusa(t, "limite_ofertas")
            limite, origem = 1, "campanha"
            busca = await catalogo.buscar_origem(t.org_id, origem_codigo, interacao_id=_interacao_id())
        else:
            estado = await asyncio.to_thread(t.qual.avaliar, t.org_id, t.lead_ref_id, _versao_id(), t.escopo, t.sinais)
            if not estado.pode_ofertar:
                return _recusa(t, "nao_pode_ofertar")
            restante_cap = t.limites.max_imoveis_distintos - len(ja)
            if restante_cap <= 0:
                return _recusa(t, "limite_ofertas")
            lote_padrao = max(1, int(t.padrao.parametros.lote_ofertas))
            limite, origem = min(limite_pedido or lote_padrao, lote_padrao, restante_cap), "similar"
            busca = await catalogo.buscar(
                t.org_id, perfil=estado.valores, excluir=ja, limite=limite, similar_a=origem_codigo,
                interacao_id=_interacao_id())
        if busca is None:
            return _falha_sw(t)
        itens = [i for i in busca.itens if reenvio or str(i["codigo"]) not in ja][:limite]
        if not itens:
            return _ok(esgotado=True, **_msg_esgotado(t))
        chave_lista, allow = ("opcoes", texto_seguro.ALLOW_OPCAO) if generico else ("imoveis", texto_seguro.ALLOW_OFERTA)

        def _forma(i: Mapping[str, Any]) -> dict[str, Any]:
            # the cards are the catalogue's own text: shaped like every other catalogue text, wrapped under one key
            return _catalogo({}, catalogo.opcao(i) if generico else i, allow).dados

        if reenvio:  # the offer event already exists: only the card + link are handed to the model again
            for i in itens:
                _lembrar(i)
            return _ok(reenvio=True, dados_catalogo={chave_lista: [_forma(i) for i in itens]})
        lote = await asyncio.to_thread(t.qual.proximo_lote, t.org_id, t.lead_ref_id)
        for i in itens:
            # the listing link rides on the offer event (``motivo``): the hand-off report reads it back on a later turn
            r = await _evento(
                str(i["codigo"]), "oferecido", origem, _link_do_evento(_pedaco_link(i)), lote=lote, catalogo=catalogo.chave)
            if not r.ok and r.codigo != "imovel_ja_oferecido":
                return _recusa(t, _codigo_recusa(r.codigo, generico))
            _lembrar(i)
        out: dict[str, Any] = {"lote": lote, "dados_catalogo": {chave_lista: [_forma(i) for i in itens]}}
        out.update({k: busca.meta[k] for k in (_META_OPCOES if generico else _BUSCA_META) if k in busca.meta})
        return _ok(**out)

    def _catalogo(body: Mapping[str, Any], item: Mapping[str, Any], allow: Mapping[str, Any]) -> texto_seguro.Catalogo:
        """The catalogue object shaped for the model; links the shaped object keeps are the ones the reply may carry."""
        c = texto_seguro.formatar_catalogo(item, allow, t.limites)
        if c.sinais:
            t.sinais_ferramenta.append(("injecao_ferramenta", {"campos": sorted({x["campo"] for x in c.sinais})}))
        return c

    async def _detalhes_nucleo(catalogo: CatalogoOpcoes, codigo: str, *, generico: bool) -> _Resultado:
        item = await catalogo.detalhar(t.org_id, codigo, interacao_id=_interacao_id())
        if item is None:
            return _falha_sw(t)
        if item.get("encontrado") is False:  # nothing was found: nothing is offered, nothing is remembered
            return _ok(encontrado=False)
        c = (_catalogo({}, catalogo.opcao(item), texto_seguro.ALLOW_OPCAO) if generico
             else _catalogo({}, item, texto_seguro.ALLOW_DETALHES))
        ja = await asyncio.to_thread(
            t.qual.codigos_oferecidos, t.org_id, t.lead_ref_id, *((catalogo.chave,) if generico else ()))
        if codigo not in ja:
            if len(ja) >= t.limites.max_imoveis_distintos:
                return _recusa(t, "limite_ofertas")
            r = await _evento(
                codigo, "oferecido", "pedido_lead", _link_do_evento(c.dados.get("link")), catalogo=catalogo.chave)
            if not r.ok and r.codigo != "imovel_ja_oferecido":
                return _recusa(t, _codigo_recusa(r.codigo, generico))
        t.codigos_vistos.add(codigo.casefold())
        if (lk := c.dados.get("link")) is not None:
            t.links_vistos.add(lk)
            t.links_por_codigo[codigo] = lk
        return _ok(encontrado=True, dados_catalogo=c.dados)

    # the real-estate tools: the SAME cores over the real-estate catalogue
    async def _oferecer(a: OferecerImoveisArgs) -> _Resultado:
        assert t.sw is not None
        return await _oferecer_nucleo(
            ImoveisSwCatalogo(t.sw), de_origem=a.modo == "campanha", limite_pedido=a.limite, generico=False)

    async def _detalhes(a: DetalhesImovelArgs) -> _Resultado:
        assert t.sw is not None
        return await _detalhes_nucleo(ImoveisSwCatalogo(t.sw), a.codigo, generico=False)

    # the generic tools: the catalogue is data (the standard's ``parametros.catalogo``)
    async def _oferecer_opcoes(a: OferecerOpcoesArgs) -> _Resultado:
        catalogo = _catalogo_ou_falha()
        if isinstance(catalogo, _Resultado):
            return catalogo
        return await _oferecer_nucleo(catalogo, de_origem=a.modo == "origem", limite_pedido=a.limite, generico=True)

    async def _detalhes_opcao(a: DetalhesOpcaoArgs) -> _Resultado:
        catalogo = _catalogo_ou_falha()
        if isinstance(catalogo, _Resultado):
            return catalogo
        return await _detalhes_nucleo(catalogo, a.codigo, generico=True)

    async def _empreendimento(a: ConsultarEmpreendimentoArgs) -> _Resultado:
        body = await _sw("consultar_empreendimento", {"nome": a.nome})
        if body is None:
            return _falha_sw(t)
        brutos = body.get("data") if isinstance(body.get("data"), list) else [body.get("data") if isinstance(body.get("data"), dict) else body]
        lista = []
        for item in brutos:
            if isinstance(item, dict):
                dados = _catalogo(body, item, texto_seguro.ALLOW_EMPREENDIMENTO).dados
                if dados:
                    lista.append(dados)
        for item in brutos:  # the listing links the reply may carry (examples are the only link-bearing part)
            if (lk := _pedaco_link(item)) is not None:
                t.links_vistos.add(lk)
        return _ok(encontrado=bool(lista), dados_catalogo={"empreendimentos": lista})

    # ── skills ──
    async def _abrir_skill(a: AbrirSkillArgs) -> _Resultado:
        assert t.skills is not None
        out = await t.skills.abrir(a.nome)
        if out.get("erro"):
            return _recusa(t, "skill_inexistente", disponiveis=out.get("disponiveis", []))
        await asyncio.to_thread(t.threads.registrar_abertura_skill, t.org_id, t.thread_id, a.nome, t.compiled_hash)
        t.skills_carregadas.add(a.nome)
        t.textos_derivados += [str(out[c]) for c in ("corpo", "descricao") if out.get(c)]
        return _ok(**out)

    async def _ler_arquivo(a: LerArquivoSkillArgs) -> _Resultado:
        assert t.skills is not None
        out = await t.skills.ler_arquivo(a.nome, a.caminho)
        if out.get("erro"):
            return _recusa(t, "arquivo_inexistente", disponiveis=out.get("disponiveis", []))
        t.textos_derivados += [str(out[c]) for c in ("conteudo", "titulo") if out.get(c)]
        return _ok(**out)

    # ── actions ──
    async def _handoff(a: HandoffArgs) -> _Resultado:
        motivo = sanitize_motivo(a.motivo) or t.texto("ferramenta.handoff.motivo_padrao")
        await executar_handoff(t, a.motivo_codigo, motivo)
        return _ok(mensagem=t.texto("ferramenta.resultado.handoff"))

    async def _encerrar(a: EncerrarArgs) -> _Resultado:
        opt_out = a.motivo == MOTIVO_LEAD_PEDIU_PARAR
        if not opt_out:
            # an open emergency is closed by inactivity or by a person -- never by the agent. The lead's own stop request
            # is the exception: it is a right, not a conversation choice.
            part = await asyncio.to_thread(t.threads.get_participante, t.org_id, t.thread_id, t.agent_id)
            if part is not None and part.fecha_inativo_min is not None:
                return _recusa(t, "emergencia_aberta")
        motivo_texto = _limpo(a.motivo_texto, MOTIVO_MAX_CHARS)
        if opt_out and motivo_texto is None:
            return _recusa(t, "motivo_texto_ausente")
        if opt_out and not t.no_lote(a.trecho, TRECHO_EVIDENCIA_MAX):
            # the opt-out is immediate and lead-wide: it needs the lead's words from THIS batch (never an old message,
            # never a re-engagement turn, which carries none)
            return _recusa(t, "opt_out_sem_evidencia")
        if opt_out and t.opt_out is None:
            logger.error("agents.channel.opt_out_indisponivel org_id=%s thread_id=%s", t.org_id, t.thread_id)
            return _falha_sw(t)
        await aplicar_encerramento(
            t, a.motivo, opt_out=opt_out, motivo_texto=motivo_texto, origem_opt_out=OPT_OUT_PEDIDO_DO_LEAD, trecho=a.trecho)
        return _ok(mensagem=t.texto("ferramenta.resultado.encerrado_opt_out" if opt_out else "ferramenta.resultado.encerrado"))

    async def _captacao(a: CaptacaoArgs) -> _Resultado:
        t.acao(type="captacao", descricao=_limpo(a.descricao, 1000), endereco=_limpo(a.endereco, 300),
               operacao=a.operacao)
        return _ok(mensagem=t.texto("ferramenta.resultado.registrado"))

    async def _titular_identificado() -> bool:
        """Is the CPF of THIS lead on record? (consent to a credit analysis is given by the person it is run on)"""
        if t.ident is None:
            return False
        faltando = await asyncio.to_thread(t.ident.faltando, t.org_id, t.lead_ref_id, ("cpf",))
        return not faltando

    async def _credito(a: ConsentimentoCreditoArgs) -> _Resultado:
        credito = getattr(t.estado_sw, "credito", None)
        if (
            not t.no_lote(a.trecho, TRECHO_EVIDENCIA_MAX)  # evidence: the lead said it in THIS batch
            or (credito is not None and credito.consentimento is not None)  # already decided: not re-decidable by chat
            or (a.aceito and not await _titular_identificado())  # a yes needs the lead's own CPF on record
        ):
            return _recusa(t, "consentimento_sem_evidencia")
        t.acao(type="consentimento_credito", aceito=a.aceito, trecho=a.trecho)
        return _ok(mensagem=t.texto("ferramenta.resultado.registrado"))

    async def _solicitacao_titular(a: RegistrarSolicitacaoTitularArgs) -> _Resultado:
        """A data-subject request (LGPD art. 18): recorded on SW's side, then a person takes the lead. Nothing is
        erased here -- erasure is an operator decision; the lead only ever asks."""
        if not t.no_lote(a.trecho, TRECHO_TITULAR_MAX):
            return _recusa(t, "trecho_nao_confere")
        lead = await asyncio.to_thread(t.threads.get_lead_ref, t.org_id, t.lead_ref_id)
        if lead is None:  # the thread has a lead (aplicar_controles links it); reaching here is a bug to see
            raise RuntimeError("registrar_solicitacao_titular: lead_ref not found")
        registro: Mapping[str, Any] = _INDISPONIVEL
        if t.sw is not None:
            try:
                registro = await asyncio.wait_for(
                    registrar_solicitacao_titular(
                        t.sw, t.org_id, lead_ref=lead.ref_externa, tipo=a.tipo, trecho=a.trecho, chat_id=t.chat_id),
                    JULIA_TOOL_TIMEOUT_SECONDS)
            except Exception as exc:  # noqa: BLE001 -- a lost record is handled below (the hand-off still goes out)
                logger.warning("agents.channel.solicitacao_titular_falhou org_id=%s cause=%s", t.org_id, type(exc).__name__)
        # The request reaches a person either way: even when SW could not record it, the hand-off note says so.
        await executar_handoff(t, "direito_titular", t.texto("ferramenta.handoff.resumo_titular", tipo=a.tipo))
        if not isinstance(registro, Mapping) or registro.get("erro") or not registro.get("id"):
            return _falha_sw(t)
        t.acao(type="solicitacao_titular", tipo=a.tipo, id=str(registro["id"]), prazo_em=(str(registro["prazo_em"]) if registro.get("prazo_em") else None))
        return _ok(mensagem=t.texto("ferramenta.resultado.solicitacao_registrada"), prazo_em=registro.get("prazo_em"))

    despacho: dict[str, Callable[[Any], Awaitable[_Resultado]]] = {
        "abrir_skill": _abrir_skill, "ler_arquivo_skill": _ler_arquivo,
        "avaliar_lead": lambda a: _avaliar(), "registrar_perfil": _registrar_perfil,
        "oferecer_imoveis": _oferecer, "detalhes_imovel": _detalhes,
        "oferecer_opcoes": _oferecer_opcoes, "detalhes_opcao": _detalhes_opcao,
        "registrar_reacao_opcao": _reacao_opcao,
        "consultar_empreendimento": _empreendimento, "registrar_reacao_imovel": _reacao,
        "registrar_intencao_visita": _visita, "registrar_identificacao": _identificar,
        "registrar_documento": _documento, "sinalizar_alerta": _alerta,
        "concluir_qualificacao": lambda a: _concluir(), "handoff": _handoff, "encerrar": _encerrar,
        "captacao": _captacao, "consentimento_credito": _credito,
        "registrar_solicitacao_titular": _solicitacao_titular,
    }

    def _parar_se_estourou() -> None:
        if t.parar is None:
            if t.recusas >= t.limites.max_recusas_por_turno:
                t.parar = "limite_recusas"
            elif t.erros >= t.limites.max_erros_ferramenta_por_turno:
                t.parar = "falhas_repetidas"

    def _acima_do_limite_do_turno(nome: str) -> bool:
        lim = t.limites
        por_tool = {
            "oferecer_imoveis": lim.max_oferecer_turno, "abrir_skill": lim.max_abrir_skill_turno,
            "detalhes_imovel": lim.max_detalhes_turno,
            "oferecer_opcoes": lim.max_oferecer_turno, "detalhes_opcao": lim.max_detalhes_turno,
        }
        return t.chamadas > lim.max_chamadas_ferramenta_turno or (
            nome in por_tool and t.chamadas_por_ferramenta[nome] > por_tool[nome])

    async def _carregar_skills(nome: str) -> list[dict[str, Any]]:
        """AUTO-LOAD (decision record ``julia-v2/DECISAO-SKILL-AUTOLOAD.md``): a tool tied to a skill never refuses
        for the skill not being open. The server opens it for THIS turn (once) and the result carries the procedure
        next to the tool's own answer. The tool's business preconditions stay in its handler."""
        out: list[dict[str, Any]] = []
        for skill in obrig.get(nome, ()):
            if skill in t.skills_carregadas or t.skills is None:
                continue
            aberta = await t.skills.abrir(skill)
            if aberta.get("erro"):  # a gate naming a skill the library lacks: seen, never a lead-facing refusal
                logger.error("agents.channel.skill_obrigatoria_inexistente org_id=%s skill=%s ferramenta=%s",
                             t.org_id, skill, nome)
                t.skills_carregadas.add(skill)
                continue
            t.skills_carregadas.add(skill)
            await asyncio.to_thread(t.threads.registrar_abertura_skill, t.org_id, t.thread_id, skill, t.compiled_hash)
            corpo = str(aberta.get("corpo") or "")
            t.textos_derivados.append(corpo)
            out.append({"skill": skill, "corpo": corpo[:PROCEDIMENTO_MAX_CHARS]})
        return out

    def _com_procedimento(res: _Resultado, procedimentos: list[dict[str, Any]]) -> _Resultado:
        return replace(res, payload={**res.payload, PROCEDIMENTO: procedimentos})

    async def _handler(call: ToolCall) -> ToolResult:
        if t.parar is not None:
            return ToolResult(call.call_id, _json({"ok": False, "codigo": "limite_recusas",
                                                   "mensagem": t.texto("ferramenta.resultado.recusa.limite_recusas")}), True)
        if call.name not in oferecidas:
            return ToolResult(call.call_id, t.texto("ferramenta.resultado.desconhecida"), True)
        t.chamadas += 1
        t.chamadas_com_marcador += prov.marcador_em([prov.texto_da_acao(call.arguments or {})], t.marcador)
        t.chamadas_por_ferramenta[call.name] = t.chamadas_por_ferramenta.get(call.name, 0) + 1
        if _acima_do_limite_do_turno(call.name):  # over the per-turn cap: a refusal that counts against the budget
            res = _recusa(t, "limite_ferramentas")
            t.recusas += 1
            logger.info("agents.channel.recusa org_id=%s ferramenta=%s codigo=limite_ferramentas classe=contada "
                        "recusas=%d chamadas=%d", t.org_id, call.name, t.recusas, t.chamadas)
            _parar_se_estourou()
            return ToolResult(call.call_id, _json(res.payload), True)
        try:
            args = TOOLS[call.name].args.model_validate(call.arguments or {})
        except ValidationError as exc:
            res = await _recusar_args(call.name, exc)
        else:
            args = t.proteger_args(call.name, args)
            procedimentos = await _carregar_skills(call.name)
            res = await despacho[call.name](args)
            if procedimentos:
                res = _com_procedimento(res, procedimentos)
        if res.recusa:
            classe = "corrigivel" if res.corrigivel else "contada"
            if res.corrigivel:
                # the corrected retry must not hit the per-tool cap; the global ``t.chamadas`` still bounds a loop
                t.chamadas_por_ferramenta[call.name] -= 1
            else:
                t.recusas += 1
            logger.info("agents.channel.recusa org_id=%s ferramenta=%s codigo=%s classe=%s recusas=%d chamadas=%d",
                        t.org_id, call.name, res.payload.get("codigo") or "itens_recusados", classe, t.recusas, t.chamadas)
        if res.falha:
            t.erros += 1
        _parar_se_estourou()
        saida = _json(res.payload)
        if not res.erro:
            # the skill's procedure text is guidance, not a source of figures a reply may repeat
            t.resultados_texto.append(_json({k: v for k, v in res.payload.items() if k != PROCEDIMENTO}))
        return ToolResult(call.call_id, saida, res.erro)

    def _resumo(nome: str, args: dict[str, Any]) -> str:
        # Operational one-liner for the admin timeline: the tool NAME only, never an argument value.
        return nome

    falha = t.conteudo.texto("runtime.ferramenta_falhou").strip()
    return LlmToolset(
        tools=specs, handler=_handler, resumo=_resumo, should_stop=lambda: t.parar is not None, falha=falha,
    )


# ── server-side effects shared by the tools and the route's deterministic escalation ──


async def alertar_operacao(t: JuliaTurno, codigo: str) -> None:
    """An OPERATOR alert for a failure that is the agent's, not the lead's (a procedural stop): the thread's alert row
    (``erro_agente``) and the ``alerta`` action SW forwards to the report destination. Codes only -- no lead text."""
    alerta_id: str | None = None
    if t.alertas is not None:
        try:
            rec = await asyncio.to_thread(
                t.alertas.registrar, t.org_id, t.thread_id, t.agent_id, tipo="erro_agente", descricao=codigo)
            alerta_id = str(rec.id)
        except Exception:  # noqa: BLE001 -- the stop already happened; the alert row is best effort but SEEN
            logger.exception("agents.channel.alerta_operacao_falhou thread_id=%s codigo=%s", t.thread_id, codigo)
    logger.error("agents.channel.parada_procedural org_id=%s thread_id=%s codigo=%s", t.org_id, t.thread_id, codigo)
    t.acao(type="alerta", tipo="erro_agente", descricao=codigo, alerta_id=alerta_id)


async def _perfil_para_handoff(t: JuliaTurno) -> dict[str, Any]:
    e = await asyncio.to_thread(t.qual.avaliar, t.org_id, t.lead_ref_id, t.padrao.id, t.escopo, t.sinais)
    eventos = await asyncio.to_thread(t.qual.eventos, t.org_id, t.lead_ref_id)
    ultimos: dict[str, str] = {}
    for ev in eventos:
        if ev.evento != "oferecido":
            ultimos[ev.codigo_imovel] = ev.evento
    return {
        "estagio": e.estagio, "score": e.score, "valores": dict(e.valores),
        "imoveis_gostou": sorted(c for c, ev in ultimos.items() if ev in ("gostou", "quer_visitar")),
        "intencoes_visita": sorted(c for c, ev in ultimos.items() if ev == "quer_visitar"),
        "faltando": list(e.faltando),
    }


async def _mascara(t: JuliaTurno) -> tuple[bool, dict[str, Any]]:
    """``(identity complete?, MASKED identity)`` for a hand-off note. The masked view needs the key; an
    unreadable one (a key rotated under stored values) is logged and the note carries no masked view -- the
    hand-off itself must never be lost to it."""
    if t.ident is None:
        return False, {}
    obrig = obrigatorios_do_padrao(t.padrao.criterios)
    faltando = await asyncio.to_thread(t.ident.faltando, t.org_id, t.lead_ref_id, obrig)
    try:
        mascarado = await asyncio.to_thread(t.ident.mascarado, t.org_id, t.lead_ref_id) or {}
    except Exception:  # noqa: BLE001 -- see docstring
        logger.exception("agents.channel.mascara_ilegivel thread_id=%s", t.thread_id)
        mascarado = {}
    return (not faltando), mascarado


async def _relatorio(t: JuliaTurno, motivo: str, perfil: Mapping[str, Any]) -> dict[str, Any]:
    """The report of this hand-off / conclusion (CONTRACT §12.4), built once per turn."""
    from app.channels.relatorio import montar_relatorio

    if t.relatorio is None:
        faltando = ()
        if t.ident is not None:
            faltando = await asyncio.to_thread(
                t.ident.faltando, t.org_id, t.lead_ref_id, obrigatorios_do_padrao(t.padrao.criterios))
        t.relatorio = await montar_relatorio(t, motivo=motivo, perfil=perfil, faltando_ident=faltando)
    return t.relatorio


async def registrar_opt_out_do_lead(t: JuliaTurno, motivo_texto: str) -> None:
    """The lead asked to stop: a LEAD-level opt-out (every agent stops) + the owner's record + notice. The lead's own
    words are what this turn received (the batch -- ``encerrar`` refuses without it, the STOP backstop IS it)."""
    lead = await asyncio.to_thread(t.threads.get_lead_ref, t.org_id, t.lead_ref_id)
    if lead is None:  # the thread has a lead (aplicar_controles links it); reaching here is a bug to see
        raise RuntimeError("encerrar: lead_ref not found")
    palavras = "\n".join(t.lote_lead)
    await asyncio.to_thread(
        t.opt_out.registrar, t.org_id, lead.ref_externa, origem="agente", motivo=motivo_texto,
        mensagem_lead=palavras[:OPT_OUT_MENSAGEM_MAX] or None, agent_id=t.agent_id, thread_id=t.thread_id)


#: Why an opt-out happened, as the turn response reports it to SW (``encerrar`` action, ``opt_out_origem``).
OPT_OUT_PALAVRA_CHAVE = "palavra_chave"  # legacy origin value (the deterministic backstop was removed 2026-11-08); kept for old events
OPT_OUT_PEDIDO_DO_LEAD = "pedido_do_lead"  # the model's ``encerrar(lead_pediu_parar)`` on the lead's words
TRECHO_OPT_OUT_MAX = 200


async def aplicar_encerramento(
    t: JuliaTurno, motivo: str, *, opt_out: bool, motivo_texto: str | None,
    origem_opt_out: str = OPT_OUT_PEDIDO_DO_LEAD, trecho: str | None = None,
) -> None:
    """End this agent's participation and, for an opt-out, record it lead-wide. ONE implementation for the model's
    ``encerrar`` tool and the deterministic STOP backstop (``channels/turno.py``), so both leave the same record."""
    if not t.encerrou:
        moved = await asyncio.to_thread(
            t.threads.transicionar, t.org_id, t.thread_id, t.agent_id, de=("ativo",), para="encerrado",
            ator_tipo="agente", motivo=motivo)
        if not moved:
            logger.info("agents.channel.encerrar_ja_movido thread_id=%s", t.thread_id)
        t.encerrou = True
        t.acao(type="encerrar", motivo=motivo)
    if opt_out and not any(x.get("lead_opt_out") for x in t.actions):
        # also when an earlier ``encerrar`` already ended this agent for another motive: the lead's request to
        # stop is what must not be lost (the turn's single ``encerrar`` action is upgraded to the opt-out).
        await registrar_opt_out_do_lead(t, motivo_texto or "")
        for x in t.actions:
            if x.get("type") == "encerrar":
                x.update(motivo=motivo, lead_opt_out=True, opt_out_origem=origem_opt_out,
                         trecho=_limpo(trecho, TRECHO_OPT_OUT_MAX))
                break
        # the explicit report SW consumes (discriminator ``type``, like every action)
        # `motivo_texto` = the agent's own reason (the recorded event's `motivo`): SW shows it in the owner's notice.
        t.acao(type="opt_out", motivo=origem_opt_out, motivo_texto=_limpo(motivo_texto, MOTIVO_MAX_CHARS),
               trecho=_limpo(trecho, TRECHO_OPT_OUT_MAX))


#: ``trecho`` prefix of a missing-spec alert: the machine key the dedupe reads (never shown to a lead).
_PREFIXO_ALERTA_INFO = "info_indisponivel"
ETAPAS_INFO_INDISPONIVEL = ("aviso", "redirecionado")


async def alertar_info_indisponivel(t: JuliaTurno, etapa: str) -> bool:
    """Tell the org (the existing ``alerta`` action: in-app + WhatsApp via SW) that a REQUIRED org spec is missing
    for this lead's conversation -- ``aviso``: the agent is answering "I will check" without it; ``redirecionado``: the
    lead was handed to a person because of it. Dedupe: each ``(thread, etapa, chave)`` alerts once; the pending keys of
    a step go in ONE alert. Never raises (a lost alert is logged and the turn goes on). Returns whether one was raised."""
    if not t.specs_faltando or t.alertas is None or etapa not in ETAPAS_INFO_INDISPONIVEL:
        if t.specs_faltando and t.alertas is None:
            logger.error("agents.channel.info_indisponivel_sem_alertas thread_id=%s", t.thread_id)
        return False
    try:
        previos = await asyncio.to_thread(t.alertas.listar, t.org_id, t.thread_id)
        ja = {
            c for p in previos if (p.trecho or "").startswith(f"{_PREFIXO_ALERTA_INFO}:{etapa}:")
            for c in p.trecho.split(":", 2)[2].split(",")
        }
        pendentes = [c for c in t.specs_faltando if c not in ja]
        if not pendentes:
            return False
        chaves = ", ".join(pendentes)
        try:
            descricao = t.texto(f"ferramenta.alerta.info_indisponivel.{etapa}", chaves=chaves)
        except TextoAusente:  # optional rows: an older version alerts with the bare code (never prose from code)
            descricao = f"{_PREFIXO_ALERTA_INFO}:{etapa}: {chaves}"
        rec = await asyncio.to_thread(
            t.alertas.registrar, t.org_id, t.thread_id, t.agent_id, tipo="outro", descricao=descricao[:ALERTA_DESCRICAO_MAX],
            trecho=f"{_PREFIXO_ALERTA_INFO}:{etapa}:{','.join(pendentes)}")
        t.acao(type="alerta", tipo="outro", descricao=descricao[:ALERTA_DESCRICAO_MAX], alerta_id=str(rec.id))
        return True
    except Exception:  # noqa: BLE001 -- a lost alert must be seen, never stop a lead's reply
        logger.exception("agents.channel.info_indisponivel_alerta_falhou thread_id=%s etapa=%s", t.thread_id, etapa)
        return False


async def executar_handoff(
    t: JuliaTurno, motivo_codigo: str, resumo: str, *, para_estado: str = "pausado",
) -> None:
    """Hand the lead to the operator (the org owner, for now): the note (profile + summary + masked
    identity) and the participant move in ONE store call. Idempotent within a turn."""
    if t.transferiu or t.concluiu:
        return
    perfil = await _perfil_para_handoff(t)
    completa, mascarada = await _mascara(t)
    relatorio = await _relatorio(t, resumo, perfil)
    perfil = {**perfil, "relatorio": relatorio}
    try:
        await asyncio.to_thread(
            t.threads.registrar_handoff, t.org_id, t.thread_id, t.agent_id, para=t.handoff_destino,
            motivo_codigo=motivo_codigo, resumo=resumo, perfil=perfil, identificacao_completa=completa,
            identificacao_mascarada=mascarada, perguntas_abertas=perfil.get("faltando", []),
            compromissos=[{"imovel": c} for c in perfil.get("intencoes_visita", [])], para_estado=para_estado,
        )
    except Exception as exc:  # noqa: BLE001 -- the participant moved under us (a human paused it): record, don't crash
        logger.warning("agents.channel.handoff_nao_registrado thread_id=%s cause=%s", t.thread_id, type(exc).__name__)
    t.transferiu = True
    t.resumo_handoff = resumo
    t.acao(type="handoff", motivo_codigo=motivo_codigo, motivo=resumo, relatorio=relatorio)
    if motivo_codigo == MOTIVO_INFO_INDISPONIVEL:  # the second notice: the lead was redirected because of the missing info
        await alertar_info_indisponivel(t, "redirecionado")


async def finalizar_conclusao(t: JuliaTurno, lead_pronto: Mapping[str, Any]) -> None:
    """``concluir_qualificacao`` took effect: the ``lead_pronto`` action and the hand-off note to the owner
    (profile + summary), the participant ending ``concluido``."""
    if t.concluiu:
        return
    resumo = t.texto(
        "ferramenta.handoff.resumo_conclusao", estagio=lead_pronto.get("estagio", ""), score=lead_pronto.get("score", ""))
    perfil = await _perfil_para_handoff(t)
    completa, mascarada = await _mascara(t)
    relatorio = await _relatorio(t, resumo, perfil)
    perfil = {**perfil, "relatorio": relatorio}
    try:
        await asyncio.to_thread(
            t.threads.registrar_handoff, t.org_id, t.thread_id, t.agent_id, para=t.handoff_destino,
            motivo_codigo="qualificacao_concluida", resumo=resumo, perfil=perfil, identificacao_completa=completa,
            identificacao_mascarada=mascarada, perguntas_abertas=[], para_estado="concluido",
            compromissos=[{"imovel": c} for c in perfil.get("intencoes_visita", [])],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("agents.channel.conclusao_nao_registrada thread_id=%s cause=%s", t.thread_id, type(exc).__name__)
    t.concluiu = True
    t.resumo_handoff = resumo
    t.acao(type="lead_pronto", **dict(lead_pronto), relatorio=relatorio)
