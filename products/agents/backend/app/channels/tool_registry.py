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

* required skill (``obrigatoria_skill`` on the tool row, or ``obrigatoria_para`` of a shared skill) not
  opened in this thread under the CURRENT ``compiled_hash``;
* ``trecho`` not in the lead's own words; offering before ``pode_ofertar``; concluding before a
  ``conclusivo`` stage; reacting to a code never offered; identity asked before the standard says so.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from noctusai_lib.integrations.llm import ToolCall, ToolResult, ToolSpec

from app.channels import proveniencia as prov
from app.channels import texto_seguro
from app.clients.social_wiring import (
    JULIA_TOOL_TIMEOUT_SECONDS,
    JULIA_TOOL_UNAVAILABLE as _INDISPONIVEL,
    SocialWiringClient,
    registrar_solicitacao_titular,
)
from app.qualificacao.matcher import MIN_TRECHO, normalizar
from app.qualificacao.identificacao import CAMPOS as IDENT_CAMPOS
from app.qualificacao.identificacao import EncryptionNotConfigured
from app.qualificacao.models import LeadSinais, VersaoPadrao
from app.qualificacao.service import ItemPerfil, QualificacaoService
from app.runtime.llm_runtime import LlmToolset
from app.studio.models import ConteudoBundle
from app.stores.threads import OPT_OUT_MENSAGEM_MAX
from app.studio.textos_registry import MOTIVOS_HANDOFF

logger = logging.getLogger(__name__)

__all__ = [
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
    "make_channel_tools_factory",
    "montar_tool_specs",
    "obrigatorias_por_ferramenta",
    "sanitize_motivo",
    "schema_de",
    "tools_ofertaveis",
]

MOTIVO_MAX_CHARS = 280
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
    ToolDef("registrar_intencao_visita", RegistrarIntencaoVisitaArgs, frozenset({"qualificacao"})),
    ToolDef("registrar_identificacao", RegistrarIdentificacaoArgs, frozenset({"identificacao"})),
    ToolDef("concluir_qualificacao", ConcluirQualificacaoArgs, frozenset({"qualificacao"})),
    ToolDef("handoff", HandoffArgs),
    ToolDef("encerrar", EncerrarArgs),
    ToolDef("captacao", CaptacaoArgs),
    ToolDef("consentimento_credito", ConsentimentoCreditoArgs, frozenset({"credito"})),
    ToolDef("registrar_solicitacao_titular", RegistrarSolicitacaoTitularArgs),
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

    def __init__(self, inner: SkillFonte, valores: Mapping[str, str]) -> None:
        self._inner = inner
        self._valores = dict(valores)

    def _resolver(self, out: dict[str, Any]) -> dict[str, Any]:
        from app.studio.especificacoes import resolver_texto

        if out.get("erro"):
            return out
        return {k: (resolver_texto(v, self._valores) if k in self._CAMPOS and isinstance(v, str) else v)
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
    # ── the turn's ledger ──
    actions: list[dict[str, Any]] = field(default_factory=list)
    recusas: int = 0
    erros: int = 0
    parar: str | None = None  # the motivo_codigo of the safe stop (limite_recusas / falhas_repetidas)
    registrou_criterios: set[str] = field(default_factory=set)
    links_vistos: set[str] = field(default_factory=set)
    codigos_vistos: set[str] = field(default_factory=set)
    #: The CPF / RG just registered this turn (normalised) -- the turn masks them in the thread's stored rows once it
    #: settles (guardrails B8.4). Memory only: never serialised, never in a repr.
    identificacoes_registradas: list[str] = field(default_factory=list, repr=False)
    #: Any identification field (name / e-mail / CPF / RG) was registered this turn: the turn response flag.
    identificacao_registrada: bool = False
    transferiu: bool = False
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
        credito = getattr(self.estado_sw, "credito", None)
        if credito is not None and credito.ativo:
            caps.add("credito")
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


# ── result shaping ──────────────────────────────────────────────────────────


def _json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


@dataclass(frozen=True)
class _Resultado:
    payload: dict[str, Any]
    erro: bool = False  # a refusal or failure the model should read as one
    recusa: bool = False  # counts against the refusal budget
    falha: bool = False  # counts against the tool-error budget


def _ok(**payload: Any) -> _Resultado:
    return _Resultado({"ok": True, **payload})


def _recusa(t: JuliaTurno, codigo: str, **extra: Any) -> _Resultado:
    """A typed refusal; the wording is the row ``ferramenta.resultado.recusa.<codigo>``."""
    sub = {"skill": extra["skill"]} if "skill" in extra else {}
    msg = t.texto(f"ferramenta.resultado.recusa.{codigo}", **sub)
    return _Resultado({"ok": False, "codigo": codigo, "mensagem": msg, **{k: v for k, v in extra.items() if k != "skill"}},
                      erro=True, recusa=True)


def _falha_sw(t: JuliaTurno) -> _Resultado:
    return _Resultado(
        {"ok": False, "codigo": "indisponivel", "mensagem": t.texto("ferramenta.resultado.recusa.indisponivel")},
        erro=True, falha=True,
    )


# ── the toolset factory ─────────────────────────────────────────────────────


def _pedaco_link(item: Any) -> str | None:
    link = item.get("link") if isinstance(item, dict) else None
    return link if isinstance(link, str) and link.strip() else None


def _consulta_sw(valores: Mapping[str, Any]) -> dict[str, Any]:
    """The SW search arguments from the lead's COMPUTED values.

    NOC-REMEDIATE[julia-v2-consulta-sw-mapa]: the criterion -> SW parameter mapping is keyed by the v1
    standard's criterion keys here; it belongs on the criterion row (a ``param_sw`` column of
    ``qualificacao_criterios``) so a renamed criterion cannot silently stop filtering -- 2026-10-19
    """
    q: dict[str, Any] = {}
    if valores.get("operacao") in ("compra", "aluguel"):
        q["operacao"] = valores["operacao"]
    if isinstance(valores.get("tipo_imovel"), str):
        q["tipo"] = valores["tipo_imovel"]
    faixa = valores.get("faixa_preco")
    if isinstance(faixa, dict):
        if "min" in faixa:
            q["preco_min"] = faixa["min"]
        if "max" in faixa:
            q["preco_max"] = faixa["max"]
    for src, dst in (("quartos_min", "quartos_min"), ("vagas_min", "vagas_min")):
        if isinstance(valores.get(src), (int, float)) and not isinstance(valores.get(src), bool):
            q[dst] = int(valores[src])
    reg = valores.get("regioes")
    if isinstance(reg, str) and reg.strip():
        q["bairros"] = [reg.strip()]
    elif isinstance(reg, list) and reg:
        q["bairros"] = [str(r) for r in reg][:10]
    # nice-to-haves (SW ranks by them and relaxes them first) vs MUST-haves (SW hard filters, never relaxed)
    for src, dst in (("caracteristicas", "caracteristicas"), ("itens_essenciais", "itens_essenciais")):
        if isinstance(valores.get(src), list) and valores[src]:
            q[dst] = [str(c) for c in valores[src]][:20]
    return q


#: The sibling keys of a ``buscar_imoveis`` answer (SW CONTRACT 8.3, v2) the model must see next to the listings:
#: how many more pass (``restantes_estimados``), which axes SW widened to fill the batch (``relaxado`` -- Julia
#: must say what was widened, never present a widened result as an exact match) and whether the campaign anchor
#: was found (``similar_a_encontrado``), and the asked items SW's catalogue cannot verify (``itens_nao_verificaveis``
#: -- pets, proximidades, ...: they did not filter the result, Julia confirms them with the lead / broker). Anything
#: else SW adds is NOT forwarded (explicit allowlist).
_BUSCA_META = ("restantes_estimados", "relaxado", "similar_a_encontrado", "itens_nao_verificaveis")


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
        return _ok(**{k: v for k, v in e.avaliar_payload().items()})

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

    async def _evento(codigo: str, evento: str, origem: str, motivo: str | None = None, lote: int | None = None) -> Any:
        return await asyncio.to_thread(
            t.qual.registrar_evento_imovel, t.org_id, t.lead_ref_id, agent_id=t.agent_id,
            versao_id=_versao_id(), codigo_imovel=codigo, evento=evento, origem=origem, lote=lote, motivo=motivo,
            thread_id=t.thread_id, escopo=t.escopo, sinais=t.sinais,
        )

    async def _origem_oferta(codigo: str) -> str:
        eventos = await asyncio.to_thread(t.qual.eventos, t.org_id, t.lead_ref_id)
        for e in eventos:
            if e.codigo_imovel == codigo and e.evento == "oferecido":
                return e.origem
        return "similar"

    async def _reacao(a: RegistrarReacaoImovelArgs) -> _Resultado:
        origem = await _origem_oferta(a.codigo)
        r = await _evento(a.codigo, a.reacao, origem, _limpo(a.motivo, 200))
        if not r.ok:
            return _recusa(t, r.codigo or "evento_invalido")
        return _ok(inalterado=r.inalterado)

    async def _visita(a: RegistrarIntencaoVisitaArgs) -> _Resultado:
        origem = await _origem_oferta(a.codigo)
        r = await _evento(a.codigo, "quer_visitar", origem)
        if not r.ok:
            return _recusa(t, r.codigo or "evento_invalido")
        if not r.inalterado:
            t.acao(type="intencao_visita", codigo=a.codigo, preferencia_horario=_limpo(a.preferencia_horario, 120))
        return _ok(inalterado=r.inalterado, mensagem=t.texto("ferramenta.resultado.registrado"))

    async def _identificar(a: RegistrarIdentificacaoArgs) -> _Resultado:
        estado = await asyncio.to_thread(t.qual.avaliar, t.org_id, t.lead_ref_id, _versao_id(), t.escopo, t.sinais)
        if not estado.pedir_identificacao:
            return _recusa(t, "identificacao_nao_devida")
        obrigatorios = tuple(c.chave for c in t.padrao.criterios if c.ativo and c.tipo == "identificacao") or IDENT_CAMPOS
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

    async def _oferecer(a: OferecerImoveisArgs) -> _Resultado:
        estado = await asyncio.to_thread(t.qual.avaliar, t.org_id, t.lead_ref_id, _versao_id(), t.escopo, t.sinais)
        if not estado.pode_ofertar:
            return _recusa(t, "nao_pode_ofertar")
        ja = await asyncio.to_thread(t.qual.codigos_oferecidos, t.org_id, t.lead_ref_id)
        restante_cap = t.limites.max_imoveis_distintos - len(ja)
        if restante_cap <= 0:
            return _recusa(t, "limite_ofertas")
        lote_padrao = max(1, int(t.padrao.parametros.lote_ofertas))
        limite = min(a.limite or lote_padrao, lote_padrao, restante_cap)
        origem = "campanha" if a.modo == "campanha" else "similar"
        campanha = getattr(getattr(t.estado_sw, "origem", None), "codigo_imovel_campanha", None)
        if a.modo == "campanha":
            if not campanha:
                return _recusa(t, "sem_codigo_campanha")
            if campanha in ja:
                return _ok(esgotado=True)
            body = await _sw("imovel_campanha", {"codigo": campanha})
        else:
            args = _consulta_sw(estado.valores)
            if campanha:
                args["similar_a"] = campanha
            args["excluir_codigos"] = ja[-200:]
            args["limite"] = limite
            body = await _sw("buscar_imoveis", {**args, **_interacao()})
        if body is None:
            return _falha_sw(t)
        itens = [i for i in (body.get("data") or []) if isinstance(i, dict) and str(i.get("codigo") or "").strip()]
        itens = [i for i in itens if str(i["codigo"]) not in ja][:limite]
        if not itens:
            return _ok(esgotado=True)
        lote = await asyncio.to_thread(t.qual.proximo_lote, t.org_id, t.lead_ref_id)
        for i in itens:
            r = await _evento(str(i["codigo"]), "oferecido", origem, lote=lote)
            if not r.ok and r.codigo != "imovel_ja_oferecido":
                return _recusa(t, r.codigo or "evento_invalido")
            t.codigos_vistos.add(str(i["codigo"]).casefold())
            if (lk := _pedaco_link(i)) is not None:
                t.links_vistos.add(lk)
        # the cards are the agency's listing text: shaped like every other catalogue text, wrapped under one key
        shaped = [_catalogo(body, i, texto_seguro.ALLOW_OFERTA).dados for i in itens]
        out: dict[str, Any] = {"lote": lote, "dados_catalogo": {"imoveis": shaped}}
        out.update({k: body[k] for k in _BUSCA_META if k in body})
        return _ok(**out)

    def _catalogo(body: Mapping[str, Any], item: Mapping[str, Any], allow: Mapping[str, Any]) -> texto_seguro.Catalogo:
        """The catalogue object shaped for the model; links the shaped object keeps are the ones the reply may carry."""
        c = texto_seguro.formatar_catalogo(item, allow, t.limites)
        if c.sinais:
            t.sinais_ferramenta.append(("injecao_ferramenta", {"campos": sorted({x["campo"] for x in c.sinais})}))
        return c

    async def _detalhes(a: DetalhesImovelArgs) -> _Resultado:
        body = await _sw("detalhes_imovel", {"codigo": a.codigo, **_interacao()})
        if body is None:
            return _falha_sw(t)
        item = body.get("data") if isinstance(body.get("data"), dict) else body
        if item.get("encontrado") is False:  # nothing was found: nothing is offered, nothing is remembered
            return _ok(encontrado=False)
        c = _catalogo(body, item, texto_seguro.ALLOW_DETALHES)
        ja = await asyncio.to_thread(t.qual.codigos_oferecidos, t.org_id, t.lead_ref_id)
        if a.codigo not in ja:
            if len(ja) >= t.limites.max_imoveis_distintos:
                return _recusa(t, "limite_ofertas")
            r = await _evento(a.codigo, "oferecido", "pedido_lead")
            if not r.ok and r.codigo != "imovel_ja_oferecido":
                return _recusa(t, r.codigo or "evento_invalido")
        t.codigos_vistos.add(a.codigo.casefold())
        if (lk := c.dados.get("link")) is not None:
            t.links_vistos.add(lk)
        return _ok(encontrado=True, dados_catalogo=c.dados)

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
        return _ok(**out)

    async def _ler_arquivo(a: LerArquivoSkillArgs) -> _Resultado:
        assert t.skills is not None
        out = await t.skills.ler_arquivo(a.nome, a.caminho)
        if out.get("erro"):
            return _recusa(t, "arquivo_inexistente", disponiveis=out.get("disponiveis", []))
        return _ok(**out)

    # ── actions ──
    async def _handoff(a: HandoffArgs) -> _Resultado:
        motivo = sanitize_motivo(a.motivo) or t.texto("ferramenta.handoff.motivo_padrao")
        await executar_handoff(t, a.motivo_codigo, motivo)
        return _ok(mensagem=t.texto("ferramenta.resultado.handoff"))

    async def _encerrar(a: EncerrarArgs) -> _Resultado:
        opt_out = a.motivo == MOTIVO_LEAD_PEDIU_PARAR
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
        if not t.encerrou:
            moved = await asyncio.to_thread(
                t.threads.transicionar, t.org_id, t.thread_id, t.agent_id, de=("ativo",), para="encerrado",
                ator_tipo="agente", motivo=a.motivo)
            if not moved:
                logger.info("agents.channel.encerrar_ja_movido thread_id=%s", t.thread_id)
            t.encerrou = True
            t.acao(type="encerrar", motivo=a.motivo)
        if opt_out and not any(x.get("lead_opt_out") for x in t.actions):
            # also when an earlier ``encerrar`` already ended this agent for another motive: the lead's request to
            # stop is what must not be lost (the turn's single ``encerrar`` action is upgraded to the opt-out).
            await _registrar_opt_out(motivo_texto or "")
            for x in t.actions:
                if x.get("type") == "encerrar":
                    x.update(motivo=a.motivo, lead_opt_out=True)
                    break
        return _ok(mensagem=t.texto("ferramenta.resultado.encerrado_opt_out" if opt_out else "ferramenta.resultado.encerrado"))

    async def _registrar_opt_out(motivo_texto: str) -> None:
        """The lead asked to stop: a LEAD-level opt-out (every agent stops) + the owner's record + notice. The
        lead's own words are what this turn received (the batch -- ``_encerrar`` refuses without it)."""
        lead = await asyncio.to_thread(t.threads.get_lead_ref, t.org_id, t.lead_ref_id)
        if lead is None:  # the thread has a lead (aplicar_controles links it); reaching here is a bug to see
            raise RuntimeError("encerrar: lead_ref not found")
        palavras = "\n".join(t.lote_lead)
        await asyncio.to_thread(
            t.opt_out.registrar, t.org_id, lead.ref_externa, origem="agente", motivo=motivo_texto,
            mensagem_lead=palavras[:OPT_OUT_MENSAGEM_MAX] or None, agent_id=t.agent_id, thread_id=t.thread_id)

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
        "consultar_empreendimento": _empreendimento, "registrar_reacao_imovel": _reacao,
        "registrar_intencao_visita": _visita, "registrar_identificacao": _identificar,
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
        }
        return t.chamadas > lim.max_chamadas_ferramenta_turno or (
            nome in por_tool and t.chamadas_por_ferramenta[nome] > por_tool[nome])

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
            _parar_se_estourou()
            return ToolResult(call.call_id, _json(res.payload), True)
        try:
            args = TOOLS[call.name].args.model_validate(call.arguments or {})
        except ValidationError as exc:
            res = await _recusar_args(call.name, exc)
        else:
            args = t.proteger_args(call.name, args)
            falta = None
            for skill in obrig.get(call.name, ()):
                if not await asyncio.to_thread(t.threads.skill_aberta, t.org_id, t.thread_id, skill, t.compiled_hash):
                    falta = skill
                    break
            if falta is not None:
                res = _recusa(t, "skill_nao_aberta", skill=falta)
            else:
                res = await despacho[call.name](args)
        if res.recusa:
            t.recusas += 1
        if res.falha:
            t.erros += 1
        _parar_se_estourou()
        return ToolResult(call.call_id, _json(res.payload), res.erro)

    def _resumo(nome: str, args: dict[str, Any]) -> str:
        # Operational one-liner for the admin timeline: the tool NAME only, never an argument value.
        return nome

    falha = t.conteudo.texto("runtime.ferramenta_falhou").strip()
    return LlmToolset(
        tools=specs, handler=_handler, resumo=_resumo, should_stop=lambda: t.parar is not None, falha=falha,
    )


# ── server-side effects shared by the tools and the route's deterministic escalation ──


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
    obrig = tuple(c.chave for c in t.padrao.criterios if c.ativo and c.tipo == "identificacao") or IDENT_CAMPOS
    faltando = await asyncio.to_thread(t.ident.faltando, t.org_id, t.lead_ref_id, obrig)
    try:
        mascarado = await asyncio.to_thread(t.ident.mascarado, t.org_id, t.lead_ref_id) or {}
    except Exception:  # noqa: BLE001 -- see docstring
        logger.exception("agents.channel.mascara_ilegivel thread_id=%s", t.thread_id)
        mascarado = {}
    return (not faltando), mascarado


async def executar_handoff(
    t: JuliaTurno, motivo_codigo: str, resumo: str, *, para_estado: str = "pausado",
) -> None:
    """Hand the lead to the operator (the org owner, for now): the note (profile + summary + masked
    identity) and the participant move in ONE store call. Idempotent within a turn."""
    if t.transferiu or t.concluiu:
        return
    perfil = await _perfil_para_handoff(t)
    completa, mascarada = await _mascara(t)
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
    t.acao(type="handoff", motivo_codigo=motivo_codigo, motivo=resumo)


async def finalizar_conclusao(t: JuliaTurno, lead_pronto: Mapping[str, Any]) -> None:
    """``concluir_qualificacao`` took effect: the ``lead_pronto`` action and the hand-off note to the owner
    (profile + summary), the participant ending ``concluido``."""
    if t.concluiu:
        return
    resumo = t.texto(
        "ferramenta.handoff.resumo_conclusao", estagio=lead_pronto.get("estagio", ""), score=lead_pronto.get("score", ""))
    perfil = await _perfil_para_handoff(t)
    completa, mascarada = await _mascara(t)
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
    t.acao(type="lead_pronto", **dict(lead_pronto))
