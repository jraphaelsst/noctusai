"""Running one channel turn of a platform-defined agent (Julia v2 CONTRACT §3.5, §6.3, §8.1).

The route (``channels_router``) owns HTTP, auth, idempotency and the order of refusals; this module owns what
happens once a turn is cleared to run:

1. :func:`preparar` -- resolve the platform definition + the org's specs, pin the qualification standard,
   compile FOR THE ORG, refuse (typed) when the content is incomplete, build the runtime spec, stamp the
   version tuple (:func:`app.studio.resolucao.carimbo`) and the prompt-leak fingerprint;
2. :func:`executar` -- build the turn's server-side state (:class:`JuliaTurno`), the dossier + per-agent
   thread context, run the model through the provider-neutral runtime, apply the conformance policy (one
   corrective re-run for a blocked reply, then silence + hand-off), the deterministic escalations and the
   safe stop, persist the assistant message stamped with the version tuple and shape the result.

Nothing here owns a model-visible string: every word is a row of the agent version's content tables.
"""
from __future__ import annotations

import asyncio
import logging
import time
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.channels import admissao, metricas
from app.channels import conformidade as conf
from app.studio.especificacoes import completar_indisponiveis, placeholder_cru_em
from app.channels.contexto import Dossie, render_contexto_system
from app.channels import proveniencia as prov
from app.channels.opt_out import OptOutService
from app.channels.tool_registry import (
    alertar_info_indisponivel,
    JuliaTurno,
    SkillFonte,
    SkillsComSpecs,
    SkillsDaVersao,
    alertar_operacao,
    executar_handoff,
    finalizar_conclusao,
    tools_ofertaveis,
)
from app.config import settings
from app.qualificacao.models import LeadSinais, VersaoPadrao
from app.qualificacao.prompt import qualificacao_data
from app.realtime import conversation_scope, get_bus, publish_event
from noctusai_lib.integrations.llm.context_window import fit_history
from noctusai_lib.integrations.llm.usage import coletar_uso
from noctusai_lib.realtime import redact_values
from app.runtime.llm_runtime import service_principal_id
from app.runtime.types import AgentSpec, TurnContext
from app.stores.conformidade import SINAIS_SEGURANCA, Impressao, Violacao
from app.stores.errors import NotFound
from app.stores.marcadores import get_marcador_store
from app.stores.studio_definitions_conteudo import OrgSpecRecord
from app.stores.threads import HandoffDestino, contexto_thread, mapa_agentes, rotular_historico
from app.studio.especificacoes_service import config_atual, preparar as preparar_valores
from app.studio.plataforma import escopo_de, padrao_de
from app.studio.resolucao import (
    AgenteResolvido, Carimbo, carimbo, compile_for_org, conteudo_status, org_specs_hash, resolve_agent_for_org,
)
from app.studio.spec import MAX_COMPILED_PROMPT_CHARS
from app.studio.camadas import efetivo

logger = logging.getLogger(__name__)

__all__ = [
    "conteudo_completo",
    "estagios_em_ordem",
    "padrao_do_turno",
    "limite_atingido",
    "status_do_limite",
    "mensagem_publica",
    "Preparado",
    "ResultadoTurno",
    "ServicosCanal",
    "TurnoRecusado",
    "executar",
    "preparar",
]

_SP = ZoneInfo("America/Sao_Paulo")
_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
#: How many of the lead's own recent messages the ``trecho`` / identity checks search.
_JANELA_LEAD = 12


class TurnoRecusado(Exception):
    """A turn that must not start; ``codigo`` is the 409 code the route answers."""

    def __init__(self, status: int, codigo: str, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status, self.codigo, self.detalhe = status, codigo, detalhe


@dataclass(frozen=True)
class ServicosCanal:
    """Every collaborator of a channel turn, resolved by the route through FastAPI ``Depends`` (so a test
    overrides a seam, never patches our code)."""

    studio_store: Any
    catalog: Any
    conversations: Any
    messages: Any
    threads: Any
    controles: Any
    conformidade: Any
    qual: Any  # QualificacaoService
    padroes: Any  # PadraoStore
    ident: Any | None
    sw: Any | None
    #: ``(definitions_store, definition_org, definition_agent_id, version_id) -> SkillFonte``; ``None`` = the
    #: version's own skills. The shared library (A-SKILLS) plugs in here.
    skills_factory: Any | None = None
    #: The notification seam (``app.notifications.NotificationSink``) the lead opt-out notice goes through.
    notificacoes: Any | None = None
    #: ``agents.thread_alertas`` store (``sinalizar_alerta``); ``None`` = the tool is not offered.
    alertas: Any | None = None
    #: ``relatorio.ResumoFactory``: builds the narrative generator of the hand-off report; ``None`` = no LLM call
    #: for the report (``resumo_conversa`` stays ``None``).
    resumo_factory: Any | None = None
    #: ``agents.turn_metrics`` store (migration 066): one row per turn, written at its end; ``None`` = not recorded.
    metricas: Any | None = None
    #: A catalogue that REPLACES whatever the qualification standard names (``parametros.catalogo``): the eval world's
    #: synthetic one. ``None`` = the standard's own catalogue, built by ``catalogo_para``.
    catalogo_fixo: Any | None = None


@dataclass(frozen=True)
class Preparado:
    r: AgenteResolvido
    padrao: VersaoPadrao
    compiled: Any
    carimbo: Carimbo
    spec: AgentSpec
    canario: str
    impressao: Impressao
    escopo: str | None
    #: The version's honeytoken (``None`` only when its store failed, which is logged).
    marcador: str | None = None


#: Channel turns sample at a LOW temperature: a lead-facing agent that follows a procedure has no use for the
#: variance that ``1.0`` buys (measured on the mechanism suite, ``DECISAO-SKILL-AUTOLOAD.md`` §3). The version can
#: override it with ``tool_policy.temperature`` (0.0 .. 1.0).
TEMPERATURA_CANAL_PADRAO = 0.3

#: ``(definition org, compiled hash)`` already stored as proof of use (the row is write-once): once per hash per process.
_PROMPTS_SALVOS: set[tuple[UUID, str]] = set()

#: Compile cache of a PUBLISHED version: ``(definition org, version id, org-specs hash, standard version id) ->
#: (compiled prompt, content complete)``. A published version is immutable, so the key is the whole input: a publish
#: (new version id), a spec write (new specs hash) and a new standard version (new id) each MISS by construction -- no
#: explicit invalidation to forget. A DRAFT (an eval run) is never cached: it changes under the key. Bounded (FIFO).
_COMPILADOS: dict[tuple[UUID, UUID, str, Any], tuple[Any, tuple[str, ...]]] = {}
_COMPILADOS_MAX = 64
#: How often a turn compiled / hit the cache / stored the proof of use (tests and the ops log read it).
ESTATISTICAS = {"compilou": 0, "reaproveitou": 0, "salvou_prompt": 0}


def limpar_cache_compilacao() -> None:
    """Drop the compile cache and the proof-of-use memo (tests; an operator after a manual DB fix)."""
    _COMPILADOS.clear()
    _PROMPTS_SALVOS.clear()


#: The stop causes that are a PROCEDURAL / TOOL slip of the model (refusal budget, tool-error budget): silent re-run,
#: then fallback + operator alert -- never a customer-facing hand-off.
PARADAS_PROCEDURAIS = frozenset({"limite_recusas", "falhas_repetidas"})


def temperatura_da_versao(versao: Any) -> float:
    """The version's sampling temperature for a channel turn: ``tool_policy.temperature`` clamped to [0, 1], else the default."""
    bruto = (getattr(versao, "tool_policy", None) or {}).get("temperature")
    if isinstance(bruto, bool) or not isinstance(bruto, (int, float)):
        return TEMPERATURA_CANAL_PADRAO
    return min(1.0, max(0.0, float(bruto)))


def _texto_opcional(conteudo: Any, chave: str) -> str:
    try:
        return conteudo.texto(chave).strip()
    except Exception:  # noqa: BLE001 -- an optional row the version has not written: the silent outcome
        return ""


def padrao_do_turno(svc: ServicosCanal, r: AgenteResolvido) -> VersaoPadrao:
    """The pinned standard version of the agent version; unpinned = the newest PUBLISHED version of the
    agent's standard (its key is part of the platform definition)."""
    pin = getattr(r.versao, "qualificacao_versao_id", None)
    try:
        if pin is not None:
            return svc.padroes.obter_versao(pin)
        chave = padrao_de(r.definicao)
        if chave is None:
            raise TurnoRecusado(409, "qualificacao_indisponivel", "O agente não tem padrão de qualificação.")
        return svc.padroes.obter_versao_publicada(chave)
    except NotFound as exc:
        raise TurnoRecusado(409, "qualificacao_indisponivel", "O padrão de qualificação não está publicado.") from exc


def _compilar(
    svc: ServicosCanal, org_id: UUID, agent: Any, *, versao: UUID | str = "ativa",
    specs: Mapping[str, str] | None = None, tolerar_specs_faltando: bool = False,
) -> tuple[AgenteResolvido, VersaoPadrao, Any]:
    """Resolve + compile FOR THE ORG with the pinned standard; refuses (typed) when there is nothing to run
    or the content is incomplete. No side effect. ``versao``/``specs`` serve the eval driver (a DRAFT, with
    synthetic org-spec values); a live turn always runs the active version with the org's own values."""
    r = resolve_agent_for_org(svc.studio_store, org_id, agent.key, versao=versao)
    if specs is not None:
        r = replace(r, specs_org=tuple(
            OrgSpecRecord(
                id=UUID(int=0), org_id=org_id, agent_key=agent.key, chave=k, valor=v, updated_by=None,
                created_at=datetime.min.replace(tzinfo=timezone.utc), updated_at=datetime.min.replace(tzinfo=timezone.utc))
            for k, v in specs.items()))
    if r.versao is None:
        raise TurnoRecusado(409, "no_active_version", "O agente não tem versão publicada.")
    padrao = padrao_do_turno(svc, r)
    publicada = getattr(r.versao, "status", None) in ("ativa", "substituida")
    chave = (r.definicao.org_id, r.versao.id, org_specs_hash(r), padrao.id)
    if publicada and chave in _COMPILADOS:
        compiled, avisos = _COMPILADOS[chave]
        ESTATISTICAS["reaproveitou"] += 1
    else:
        compiled = compile_for_org(svc.studio_store, svc.catalog, r, qualificacao=qualificacao_data(padrao))
        avisos = tuple(conteudo_status(svc.studio_store, svc.catalog, r, compiled=compiled).avisos_bloqueantes)
        ESTATISTICAS["compilou"] += 1
        if publicada and padrao.id is not None:
            if len(_COMPILADOS) >= _COMPILADOS_MAX:
                _COMPILADOS.pop(next(iter(_COMPILADOS)))
            _COMPILADOS[chave] = (compiled, avisos)  # the BLOCKING warnings, not a verdict: ``tolerar_specs_faltando`` is per call
    # A REQUIRED org spec with no value is readiness (publish), not a refusal at turn time: the prompt carries the
    # INDISPONIVEL sentinel for it and the turn alerts the org (``alertar_info_indisponivel``). ``conteudo_completo``
    # (what SW / Studio show) stays strict.
    bloqueantes = set(avisos) - ({"spec_org_faltando"} if tolerar_specs_faltando else set())
    if bloqueantes:
        raise TurnoRecusado(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.")
    return r, padrao, compiled


def conteudo_completo(svc: ServicosCanal, org_id: UUID, agent: Any) -> bool:
    """Would a turn start? (``status.conteudo_completo`` for SW / Studio.)"""
    try:
        _compilar(svc, org_id, agent)
    except TurnoRecusado:
        return False
    return True


def _marcador_do_prompt(r: AgenteResolvido, compiled: Any) -> tuple[str | None, str]:
    """``(marker, the DB line that carries it)``. The marker is generated once per version (publish, or the first
    turn of an older version) and lives only in the DB; the line is the version's ``seguranca.marcador_interno`` text
    with ``{marcador}`` filled, appended after the canary (never in the compiled hash)."""
    conteudo = compiled.conteudo
    if conteudo is None:
        return None, ""
    try:
        marcador = get_marcador_store(settings).garantir(r.definicao.org_id, r.versao.id)
    except Exception:  # noqa: BLE001 -- the tripwire is detective; losing it must be seen, never stop a lead's reply
        logger.exception("agents.channel.marcador_indisponivel version_id=%s", r.versao.id)
        return None, ""
    texto = conteudo.texto("seguranca.marcador_interno").strip()
    if not texto:
        raise TurnoRecusado(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.")
    return marcador, texto.replace("{marcador}", marcador)


def preparar(
    svc: ServicosCanal, org_id: UUID, agent: Any, *, versao: UUID | str = "ativa",
    specs: Mapping[str, str] | None = None,
) -> Preparado:
    """Everything a turn needs that does not depend on the lead. Raises :class:`TurnoRecusado` (409) BEFORE
    anything is persisted: ``no_active_version`` · ``qualificacao_indisponivel`` · ``conteudo_incompleto`` ·
    ``prompt_too_large``."""
    r, padrao, compiled = _compilar(svc, org_id, agent, versao=versao, specs=specs, tolerar_specs_faltando=True)
    if len(compiled.texto) > MAX_COMPILED_PROMPT_CHARS:
        raise TurnoRecusado(409, "prompt_too_large", "O prompt compilado passa do limite de tamanho.")
    try:  # proof of use (§A7), under the org that owns the version's rows; write-once, so once per process is enough
        if (r.definicao.org_id, compiled.hash) not in _PROMPTS_SALVOS:
            svc.studio_store.save_compiled_prompt(
                r.definicao.org_id, hash=compiled.hash, version_id=r.versao.id, client_id=None,
                texto=compiled.texto, manifest=compiled.manifest_json(),
            )
            _PROMPTS_SALVOS.add((r.definicao.org_id, compiled.hash))
            ESTATISTICAS["salvou_prompt"] += 1
    except Exception:  # noqa: BLE001 -- proof-of-use must not stop a lead's reply; it must be seen
        logger.exception("agents.channel.compiled_prompt_not_saved org_id=%s hash=%s", org_id, compiled.hash)
    marca = carimbo(svc.studio_store, svc.catalog, r, compiled=compiled)
    can = conf.canario(org_id, r.versao.id, segredo=getattr(settings, "encryption_key", "") or "")
    marcador, linha_marcador = _marcador_do_prompt(r, compiled)
    spec = AgentSpec(
        key=agent.key, provider=r.versao.provider, runtime="llm", model=r.versao.model, effort=r.versao.effort,
        # The canary rides with the prompt (never in the hash): a reply that contains it reproduced the prompt.
        prompt_append="\n\n".join(p for p in (compiled.texto, can, linha_marcador) if p), skills=(),
        # Structural (guardrails B6.7): the channel toolset (``make_channel_tools_factory``) is the ONLY toolset of a
        # lead-facing turn -- never web search, never knowledge, never a studio tool, whatever the version's policy says.
        tools=(),
        max_turns=r.versao.max_turns, prompt_mode="custom", toolset="studio", agent_id=agent.id,
        version_id=r.versao.id, compiled_hash=compiled.hash, web_search=False, knowledge=False, client_id=None,
        temperature=temperatura_da_versao(r.versao),
    )
    k = conf.shingle_tokens_da_regra(svc.conformidade.regras(org_id, agent.id).get("vazamento_prompt"))
    impressao = conf.garantir_impressao(svc.conformidade, r.definicao.org_id, r.versao.id, compiled, k)
    return Preparado(r, padrao, compiled, marca, spec, can, impressao, escopo_de(r.definicao), marcador)


# ── the result ──────────────────────────────────────────────────────────────


@dataclass
class ResultadoTurno:
    partes_texto: str = ""
    actions: list[dict[str, Any]] = field(default_factory=list)
    status: str = "silencio"
    usage: dict[str, Any] = field(default_factory=dict)
    participante_estado: str | None = None
    qualificacao: dict[str, Any] | None = None
    violacoes: list[Violacao] = field(default_factory=list)
    message_id: UUID | None = None
    #: A CPF / RG was registered in this turn (``registrar_identificacao`` -> ``registrado``): the response flag.
    identificacao_registrada: bool = False


@dataclass
class _Tentativa:
    textos: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    esgotou: bool = False
    tools_ms: dict[str, int] = field(default_factory=dict)


def _urls(texto: str) -> set[str]:
    return {u.rstrip(".,;:!?)]}\"'") for u in _URL.findall(texto)}


def _falas_do_lead(r: Any) -> list[str]:
    """What a stored lead row says in the lead's OWN words: the typed text, plus an AUDIO's transcription (the lead
    spoke it). An image / document / video text is not the lead speaking, so it never counts as their words."""
    meta = getattr(r, "meta", None) or {}
    if meta.get("encaminhada"):  # forwarded: not the lead's own words (no evidence, no qualification answer)
        return []
    midia = meta.get("midia") or {}
    falas = [r.texto] if r.texto else []
    if midia.get("tipo") == "audio" and midia.get("texto_extraido"):
        falas.append(midia["texto_extraido"])
    return falas


def _midia_da_mensagem(messages: Any, org_id: UUID, thread_id: UUID, provider_message_id: str) -> dict[str, Any] | None:
    """The ``midia`` of the INBOUND LEAD message ``provider_message_id`` of this thread (``{}`` when it carried
    none); ``None`` when no such lead message exists here (the id is recorded on the row at intake)."""
    for r in messages.list(org_id, thread_id, limite=500):
        meta = getattr(r, "meta", None) or {}
        if r.role == "user" and meta.get("provider_message_id") == provider_message_id:
            return dict(meta.get("midia") or {})
    return None


def ajustar_janela_historico(linhas: list[tuple[str, str]], max_tokens: int | None = None) -> tuple[tuple[str, str], ...]:
    """The labelled history within the model's token budget. A history that fits comes back UNCHANGED (the same
    lines, the same bytes: today's prompt); over budget the server drops the oldest turns (pure trimming, no model
    call, so no per-turn cost or latency)."""
    limite = max_tokens or int(getattr(settings, "llm_history_max_tokens", 40_000) or 40_000)
    return tuple(fit_history(linhas, max_tokens=limite).messages)


def _mensagens_do_lead(messages: Any, org_id: UUID, thread_id: UUID) -> tuple[list[str], int, list[str]]:
    """``(the lead's recent words, how many lead messages, the provenance tags of this thread's earlier turns)``."""
    rows = messages.list(org_id, thread_id, limite=500)
    lead = [f for r in rows if r.role == "user" for f in _falas_do_lead(r)]
    tags = [t for r in rows if r.role == "assistant" and (t := (getattr(r, "meta", None) or {}).get("tag"))]
    return lead[-_JANELA_LEAD:], len(lead), tags[-_JANELA_LEAD:]


def _inicio_do_dia(agora: datetime) -> datetime:
    return agora.astimezone(_SP).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def limite_atingido(svc: ServicosCanal, org_id: UUID, thread_id: UUID, agent_id: UUID, agora: datetime) -> str | None:
    """Per-chat abuse limits, in data (``canal_limites``), enforced under the turn lock: turns per window and per
    hour, turns and spend per day. Returns the limit that tripped (a code), or ``None``. ``turnos_janela`` /
    ``turnos_hora`` are the per-lead RATE limits (response status ``limite_taxa``, see :func:`status_do_limite`)."""
    lim = svc.conformidade.limites(org_id, agent_id)
    na_janela, _ = svc.messages.thread_usage_since(org_id, thread_id, agora - timedelta(seconds=lim.janela_segundos))
    if na_janela >= lim.max_turnos_janela:
        return "turnos_janela"
    na_hora, _ = svc.messages.thread_usage_since(org_id, thread_id, agora - timedelta(hours=1))
    if na_hora >= lim.max_turnos_hora:
        return "turnos_hora"
    no_dia, custo = svc.messages.thread_usage_since(org_id, thread_id, _inicio_do_dia(agora))
    if no_dia >= lim.max_turnos_dia:
        return "turnos_dia"
    if custo >= lim.max_custo_dia_usd:
        return "custo_dia"
    return None


#: The limits that are a RATE (a burst) rather than a daily quota: the response status SW routes on.
_LIMITES_TAXA = frozenset({"turnos_janela", "turnos_hora"})


def status_do_limite(limite: str) -> str:
    """The turn-response status of a tripped limit: ``limite_taxa`` for a rate, ``limite_atingido`` for a quota."""
    return "limite_taxa" if limite in _LIMITES_TAXA else "limite_atingido"


# ── execution ───────────────────────────────────────────────────────────────


def _textos_com_valor(turno: JuliaTurno, ct: Any, estado: Any, lote_lead: list[str], mensagens_lead: list[str]) -> list[str]:
    """Where a figure of a reply may come from (``valor_sem_ferramenta``): this turn's tool results, the lead's own
    words (never a forwarded message or media text), the agent's earlier replies in this thread, the dossier."""
    proprias = [i.texto for i in ct.mensagens if i.origem == "proprio"]
    do_lead = [i.texto for i in ct.mensagens if i.origem == "lead" and not getattr(i, "encaminhada", False)]
    dossie = [str(v) for v in getattr(estado, "valores", {}).values()]
    return [*turno.resultados_texto, *lote_lead, *mensagens_lead, *do_lead, *proprias, *dossie]


async def _rodar(runtime: Any, spec: AgentSpec, ctx: TurnContext, slot: Any, nome_evento: Any) -> _Tentativa:
    from app.routers.conversations_router import _apply_tool_event

    t = _Tentativa()
    async for event in runtime.run_turn(spec, ctx, "", None, slot=slot):
        kind, evt = event["event"], event["payload"]
        if kind == "message.new":
            t.textos.append(evt.get("texto", ""))
        elif kind in ("tool.started", "tool.finished"):
            t.blocks = _apply_tool_event(t.blocks, kind, evt)
        elif kind == "session.status":
            t.usage = {k: evt.get(k) for k in (
                "custo_usd", "tokens_entrada", "tokens_saida", "llm_ms", "tool_ms", "llm_calls", "prompt_bytes")}
            t.tools_ms = dict(evt.get("tools_ms") or {})
            t.esgotou = bool(evt.get("esgotou_loop"))
        else:
            logger.warning("agents.channel.turn.unknown_event kind=%s", kind)
    return t


def _somar(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if v is not None:
            out[k] = (out.get(k) or 0) + v
    return out


def _numerar(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The turn's actions in call order with ``seq`` 1..n; only the FIRST handoff and the first of each
    one-shot terminal action is kept."""
    out: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for a in raw:
        if a["type"] in ("handoff", "lead_pronto", "encerrar"):
            if a["type"] in vistos:
                continue
            vistos.add(a["type"])
        out.append({**a, "seq": len(out) + 1})
    return out


async def executar(
    *, origem: str = "canal", mensagem_entrada_id: UUID | None = None, entrada_em: datetime | None = None,
    **kw: Any,
) -> ResultadoTurno:
    """Run one turn (:func:`_executar`) and record its cost / speed / size in ``agents.turn_metrics`` (migration 066).

    The metrics row is written ONCE, after the turn, success or failure: a raising turn still books the money its
    priced events spent. A failed write is logged and never changes the turn's outcome (:func:`metricas.registrar_turno`).
    ``origem`` is ``canal`` for a real channel turn, ``eval`` for the eval / mechanism driver."""
    svc: ServicosCanal = kw["svc"]
    inicio = time.perf_counter()
    medida: dict[str, Any] = {}
    status, erro_classe, resultado = "ok", None, None
    with coletar_uso() as eventos:
        try:
            resultado = await _executar(medida=medida, **kw)
            return resultado
        except BaseException as exc:
            status, erro_classe = "erro", type(exc).__name__
            raise
        finally:
            _registrar_metricas(
                svc, kw, eventos, medida, resultado, status, erro_classe, origem=origem,
                mensagem_entrada_id=mensagem_entrada_id, entrada_em=entrada_em,
                turno_ms=int((time.perf_counter() - inicio) * 1000))


def _registrar_metricas(
    svc: ServicosCanal, kw: dict[str, Any], eventos: list[Any], medida: dict[str, Any], resultado: ResultadoTurno | None,
    status: str, erro_classe: str | None, *, origem: str, mensagem_entrada_id: UUID | None, entrada_em: datetime | None,
    turno_ms: int,
) -> None:
    if svc.metricas is None:
        return
    try:
        prep, agent, thread, agora = kw["prep"], kw["agent"], kw["thread"], kw["agora"]
        lote_entrada = kw.get("lote_entrada")
        lote = (kw.get("lote_lead") or []) if lote_entrada is None else lote_entrada
        usage = resultado.usage if resultado is not None else {}
        acoes = resultado.actions if resultado is not None else []
        entrada = sum(metricas.tamanho_bytes(t) for t in lote)
        resposta = metricas.tamanho_bytes(resultado.partes_texto) if resultado is not None else 0
        row = metricas.montar_registro(
            org_id=kw["org_id"], agent=agent, versao_id=prep.carimbo.definition_version_id,
            compiled_hash=prep.carimbo.compiled_hash, thread_id=thread.id, mensagem_entrada_id=mensagem_entrada_id,
            mensagem_resposta_id=resultado.message_id if resultado is not None else None, origem=origem,
            gatilho=kw.get("gatilho"), eventos=eventos,
            medida={**medida, **{k: usage.get(k) for k in ("llm_ms", "tool_ms", "prompt_bytes", "llm_calls")}},
            turno_ms=turno_ms,
            intake_ms=max(0, int((agora - entrada_em).total_seconds() * 1000)) if entrada_em is not None else None,
            inbound_bytes=entrada, reply_bytes=resposta,
            db_bytes=entrada + resposta + metricas.tamanho_bytes(medida.get("blocks")),
            status=status, erro_classe=erro_classe, turno_status=resultado.status if resultado is not None else None,
            handoff=any(a.get("type") == "handoff" for a in acoes), tools=medida.get("tools") or (),
        )
    except Exception:  # noqa: BLE001 -- building the row must not fail the turn either: seen in the log
        logger.exception("agents.turn_metrics.montagem_falhou")
        return
    metricas.registrar_turno(svc.metricas, row)


async def _executar(
    *, svc: ServicosCanal, prep: Preparado, agent: Any, org_id: UUID, thread: Any, runtime: Any, slot: Any,
    bus: Any, contexto: Any | None, gatilho: str, lote_lead: list[str], ultima_resposta_em: datetime | None,
    agora: datetime, lote_entrada: list[str] | None = None, nota_caso: str | None = None,
    medida: dict[str, Any] | None = None,
) -> ResultadoTurno:
    """Run the model for ``thread`` and settle everything the turn does. ``lote_lead`` are the texts of the
    batch just stored (empty for a re-engagement) that the lead SAID (typed + spoken); ``lote_entrada`` adds the text
    extracted from images / documents / video and captions, which only the input-side tripwires read."""
    lote_entrada = list(lote_lead) if lote_entrada is None else lote_entrada
    r, padrao = prep.r, prep.padrao
    conteudo = prep.compiled.conteudo
    if conteudo is None:  # a content-mode agent always has it; anything else cannot run on this path
        raise TurnoRecusado(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.")
    lead_ref_id = thread.lead_ref_id
    if lead_ref_id is None:  # aplicar_controles links every thread; reaching here is a bug to see
        raise RuntimeError("thread without a lead_ref")
    regras = svc.conformidade.regras(org_id, agent.id)
    limites = svc.conformidade.limites(org_id, agent.id)
    estado_sw = contexto.estado if contexto is not None else None
    ferramentas_sw = contexto.capacidades.ferramentas_sw if contexto is not None else True

    mensagens_lead, n_respostas, tags_anteriores = _mensagens_do_lead(svc.messages, org_id, thread.id)
    tag = prov.nova_tag()
    # input-side security signals (signal only, never block): an attempt to read the instructions, a claim of
    # identity. They feed ``escala_seguranca`` (reduce-only: a claim never grants anything).
    sinal = conf.sinal_extracao(lote_entrada, regras.get("tentativa_extracao"))
    alegacao = conf.sinal_alegacao(lote_entrada, regras.get("alegacao_identidade"))
    violacoes: list[Violacao] = [
        Violacao(nome, "sinal", d) for nome, d in (("tentativa_extracao", sinal), ("alegacao_identidade", alegacao)) if d
    ]
    previos = await asyncio.to_thread(
        svc.conformidade.contar_sinais, org_id, agent.id, thread.id, SINAIS_SEGURANCA, agora - timedelta(hours=24))
    nivel = conf.nivel_seguranca(regras.get("escala_seguranca"), previos + len(violacoes))
    if nivel != "normal":
        violacoes.append(Violacao("escala_seguranca", "registrar", {"nivel": nivel, "sinais": previos + len(violacoes)}))
    # leak tripwires on the input side (provenance tag echoed, canary / prompt run / honeytoken received)
    violacoes += _sinais_de_entrada(svc, prep, org_id, agent, thread, lote_entrada, tag, tags_anteriores)

    pediu_humano = _pediu_humano(svc, regras, org_id, thread.id, lote_lead)
    sinais = LeadSinais(
        ultima_resposta_em=ultima_resposta_em, respostas_count=n_respostas,
        eventos={"pediu_humano": 1} if pediu_humano else {},
    )
    fonte: SkillFonte = (
        svc.skills_factory(svc.studio_store, r.definicao.org_id, r.definicao.id, r.versao.id)
        if svc.skills_factory is not None
        else SkillsDaVersao(svc.studio_store, r.definicao.org_id, r.definicao.id, r.versao.id)
    )
    # skill texts resolved FOR THIS ORG ({{org.chave}}), the same resolver the compiled sections went through
    prep_specs = preparar_valores({d.chave: d.tipo for d in r.specs_declaradas}, r.valores, config_atual())
    #: allowlists are RULES: built only from values that passed the validator (report mode keeps an invalid value as
    #: data, it never lets it widen what a reply may link or cite)
    valores = prep_specs.limpos
    # a REQUIRED spec with no value reads ``[dado: chave]`` in a skill text too (the sentinel is in the prompt's data block)
    valores_skill, fenced_skill, _ = completar_indisponiveis(
        [d.chave for d in r.specs_declaradas if d.obrigatoria], prep_specs.valores, prep_specs.fenced)
    skills: SkillFonte | None = SkillsComSpecs(fonte, valores_skill, fenced_skill)
    sw = svc.sw if (svc.sw is not None and svc.sw.julia_tools_available(org_id)) else None
    leak = regras.get("vazamento_prompt")
    historico_previo = await asyncio.to_thread(lambda: svc.messages.list(org_id, thread.id, limite=500))
    dados_da_org = tuple(valores.values())
    ef = efetivo(svc.studio_store)  # 073: the version's effective skills (parent chain merged in)
    ativas = [x for x in ef.list_skills(r.definicao.org_id, r.versao.id) if x.ativo]
    arquivos = ef.list_version_skill_files(r.definicao.org_id, r.versao.id)
    #: every ACTIVE skill body and file of the version (the library's pinned skills join as they are loaded), 24-token window
    texto_skills = conf.texto_fonte_do_prompt(
        None, [x.corpo for x in ativas if getattr(x, "corpo", None)],
        [f.conteudo for f in arquivos if getattr(f, "conteudo", None)], so_skills=True)

    memo: dict[int, Any] = {}

    def _derivada() -> Any:
        n = len(turno.textos_derivados)  # recomputed only when a tool handed the model new skill text
        if n not in memo:
            memo[n] = conf.impressao_derivada([texto_skills, *turno.textos_derivados])
        return memo[n]

    def _vazou_texto(texto: str) -> bool:
        texto = conf.mascarar_dados_da_org(texto, dados_da_org)
        return conf.detectar_vazamento(texto, canario_do_prompt=prep.canario, impressao=prep.impressao) is not None or (
            conf.detectar_vazamento(
                texto, canario_do_prompt=None, impressao=_derivada()) is not None)

    turno = JuliaTurno(
        org_id=org_id, agent_id=agent.id, agent_key=agent.key, thread_id=thread.id, lead_ref_id=lead_ref_id,
        conteudo=conteudo, compiled_hash=prep.carimbo.compiled_hash, padrao=padrao, qual=svc.qual,
        threads=svc.threads, skills=skills, sw=sw, ident=svc.ident, handoff_destino=HandoffDestino.dono_da_org(),
        marcador=prep.marcador, limites=limites, mensagens_lead=mensagens_lead, sinais=sinais, escopo=prep.escopo, estado_sw=estado_sw,
        ferramentas_sw=ferramentas_sw, lote_lead=list(lote_lead), catalogo_fixo=svc.catalogo_fixo,
        chat_id=(getattr(thread, "channel_ref", None) or {}).get("chat_id"),
        opt_out=OptOutService(
            svc.threads, svc.notificacoes, agentes=lambda oid: mapa_agentes(svc.studio_store, oid)),
        modo_restrito=nivel != "normal",
        alertas=svc.alertas,
        specs_faltando=tuple(prep.compiled.specs_faltando),
        alertas_desde=max(
            (r.created_at for r in historico_previo if r.role == "assistant" and r.created_at is not None),
            default=None),
        midia_da_mensagem=lambda pmid: _midia_da_mensagem(svc.messages, org_id, thread.id, pmid),
        auditar=lambda codigo: svc.messages.add(
            org_id, thread.id, "evento", codigo, agent_id=agent.id, lead_ref_id=lead_ref_id),
        resumo_conversa=(
            svc.resumo_factory(
                runtime=runtime, versao=r.versao, conteudo=conteudo, messages=svc.messages, org_id=org_id,
                thread_id=thread.id)
            if svc.resumo_factory is not None else None),
        guarda_campos=(
            _vazou_texto
            if leak is not None and leak.ativo else None),
    )
    # Opt-out is JULIA's decision (owner, 2026-11-08: "it shouldn't be deterministic, Julia judges"): she calls ``encerrar``
    # (lead_pediu_parar) and the system does the rest. The stop-word list is only a SIGNAL: when a message of the batch IS one
    # of the words, the state block says so (optional text ``contexto.sinal_opt_out``) -- it never ends anything by itself.
    sinal_parar = (
        conf.palavra_de_parar(lote_lead, regras.get("opt_out_palavras")) if gatilho == "mensagem" else None)
    # loop / flood / echo breaker (guardrails B5): no model call -- the participant is paused, a person is told
    if gatilho == "mensagem":
        sinal_loop = await asyncio.to_thread(_loop_detectado, svc, org_id, thread.id, lote_lead, limites)
        if sinal_loop is not None:
            return await _parar_por_loop(svc, turno, prep, agent, org_id, thread, lead_ref_id, sinal_loop)
    estado0 = await asyncio.to_thread(svc.qual.avaliar, org_id, lead_ref_id, padrao.id, prep.escopo, sinais)

    # the thread context of THIS agent: dossier + last N labelled turns + the newest hand-off note
    n = runtime.history_messages
    ct = contexto_thread(svc.messages, svc.threads, mapa_agentes(svc.studio_store, org_id), org_id, thread.id, agent.id, n=n)
    historico = ajustar_janela_historico(rotular_historico(
        ct.mensagens, tag=tag, rotulo_midia=conteudo.texto("historico.rotulo_midia"),
        rotulo_truncado=conteudo.texto("historico.rotulo_truncado"),
        rotulo_encaminhada=conteudo.texto("historico.rotulo_encaminhada")))
    eventos = await asyncio.to_thread(svc.qual.eventos, org_id, lead_ref_id)
    dossie = _dossie(padrao, estado0, eventos, ct.handoff)
    contexto_system = render_contexto_system(
        conteudo, agora=(contexto.agora if contexto is not None else agora),
        fuso=(contexto.fuso if contexto is not None else "America/Sao_Paulo"), estado=estado_sw, dossie=dossie,
        tag=tag,
    )
    if sinal_parar:  # the lead's message looks like an opt-out request: a hint to JULIA, who decides (see above)
        dica = _texto_opcional(conteudo, "contexto.sinal_opt_out")
        if dica:
            contexto_system = f"{contexto_system}\n\n{dica}"
    if nota_caso:  # an eval case's situation lives in the state block, exactly where a real turn's facts live
        contexto_system = f"{contexto_system}\n\n{nota_caso.strip()}"
    ctx = TurnContext(
        org_id=org_id, conversation_id=thread.id, requested_by=service_principal_id(agent.id),
        instance_id="", sdk_session_id=None, contexto=contexto, julia=turno, contexto_system=contexto_system,
        historico=historico, resposta_fallback=conteudo.texto("runtime.resposta_fallback").strip(),
    )
    ctx = replace(ctx, instance_id=_instance_id())

    links_anteriores: set[str] = set()
    for item in ct.mensagens:
        if item.origem == "proprio":
            links_anteriores |= _urls(item.texto)

    campanha = getattr(getattr(estado_sw, "origem", None), "codigo_imovel_campanha", None)
    codigos_da_thread = {e.codigo_imovel.casefold() for e in eventos} | ({campanha.casefold()} if campanha else set())
    tentativas: list[_Tentativa] = []
    bloqueios: list[Violacao] = []
    if turno.specs_faltando:  # the org learns the agent is answering without a required spec
        await alertar_info_indisponivel(turno, "aviso")

    def _avaliar(t: _Tentativa) -> list[Violacao]:
        resposta = "\n\n".join(x for x in t.textos if x and x.strip())
        return _marcadores_da_resposta(resposta, prep.marcador, tag, regras) + conf.avaliar_resposta(conf.EntradaConformidade(
            resposta=resposta, mensagens_lead=lote_lead, regras=regras,
            canario=prep.canario, impressao=prep.impressao, dados_da_org=dados_da_org, impressao_derivada=_derivada(),
            codigos_permitidos=turno.codigos_vistos | codigos_da_thread,
            links_permitidos={*turno.links_vistos, *links_anteriores},
            participante_segue_ativo=not (turno.transferiu or turno.concluiu or turno.encerrou),
            encerrou_ou_transferiu=False,
            transferiu_no_turno=turno.transferiu,
            contato_garantido_no_turno=turno.transferiu or turno.concluiu or turno.visita_registrada,
            alertou_no_turno=bool(turno.alertas_tipos), encerrou_no_turno=turno.encerrou,
            alerta_ofertado=any(
                f.ferramenta == "sinalizar_alerta" for f in tools_ofertaveis(turno.conteudo, turno.capacidades())),
            criterio_perguntado=padrao.criterio(estado0.proximo_criterio.chave) if estado0.proximo_criterio else None,
            registrou_perfil=bool(estado0.proximo_criterio and estado0.proximo_criterio.chave in turno.registrou_criterios),
            criterios_preenchidos={
                k: padrao.criterio(k).rotulo for k in estado0.valores
                if padrao.criterio(k) is not None and padrao.criterio(k).tipo not in ("derivado", "identificacao")
            },
            registrados_no_turno=turno.registrou_criterios, esgotou_loop=t.esgotou,
            dominios_permitidos=conf.lista_de_spec(valores.get(conf.SPEC_DOMINIOS)),
            contatos_permitidos=conf.lista_de_spec(valores.get(conf.SPEC_CONTATOS)),
            cnpjs_proprios=conf.lista_de_spec(valores.get(conf.SPEC_CNPJ)),
            textos_com_valor=_textos_com_valor(turno, ct, estado0, lote_lead, mensagens_lead),
        ))

    try:
        async with asyncio.timeout(settings.channel_turn_timeout_seconds):
            await publish_event(thread.id, "session.status", {"status": "pensando"}, bus=bus)
            t1 = await _rodar(runtime, prep.spec, ctx, slot, None)
            if turno.parar in PARADAS_PROCEDURAIS:
                # a procedural / tool slip of the model is never the lead's problem: ONE silent re-run on fresh budgets
                # (the compliance re-run's twin); only a second slip reaches the settle block below
                violacoes.append(Violacao("parada_segura", "registrar", {"motivo": turno.parar, "tentativa": 1}))
                tentativas.append(t1)
                turno.reiniciar_tentativa()
                t1 = await _rodar(runtime, prep.spec, ctx, slot, None)
            tentativas.append(t1)
            violacoes += [Violacao(r, "sinal", d) for r, d in turno.sinais_ferramenta]
            achados = [] if turno.parar else _avaliar(t1)
            bl = conf.violacoes_bloqueantes(achados)
            violacoes += [replace(v, bloqueada=v in bl) for v in achados]
            texto_final = "\n\n".join(x for x in t1.textos if x and x.strip())
            if bl:
                correcao = " ".join(conteudo.texto(f"conformidade.correcao.{v.regra}").strip() for v in bl)
                # the thread keeps the CODE only: the wording is prompt text and travels in `mensagem_correcao` alone
                svc.messages.add(
                    org_id, thread.id, "evento", codigo_evento_correcao(bl), agent_id=agent.id, lead_ref_id=lead_ref_id)
                turno.reiniciar_tentativa()  # the corrected re-run starts with fresh refusal / call budgets and loaded skills
                t2 = await _rodar(runtime, prep.spec, replace(ctx, mensagem_correcao=correcao), slot, None)
                tentativas.append(t2)
                achados2 = [] if turno.parar else _avaliar(t2)
                bl2 = conf.violacoes_bloqueantes(achados2)
                violacoes += [replace(v, bloqueada=v in bl2) for v in achados2]
                if bl2:
                    texto_final = ""
                    bloqueios = bl2
                else:
                    texto_final = "\n\n".join(x for x in t2.textos if x and x.strip())
            if (not texto_final.strip() and not bloqueios
                    and not (turno.parar or turno.transferiu or turno.concluiu or turno.encerrou)):
                # A turn that ends on tool calls with NO message leaves the lead with nothing (the measured "silencio" of
                # the behaviour suite after sinalizar_alerta / registrar_intencao_visita). The model's slip is never the
                # lead's problem: ONE corrective re-run asks for the message. The wording is prompt text (an optional row,
                # ``conformidade.correcao.resposta_vazia``): without it the outcome stays silence, as before.
                correcao_vazia = _texto_opcional(conteudo, "conformidade.correcao.resposta_vazia")
                if correcao_vazia:
                    svc.messages.add(
                        org_id, thread.id, "evento", f"{_PREFIXO_EVENTO_CORRECAO}:resposta_vazia", agent_id=agent.id,
                        lead_ref_id=lead_ref_id)
                    turno.reiniciar_tentativa()
                    t3 = await _rodar(runtime, prep.spec, replace(ctx, mensagem_correcao=correcao_vazia), slot, None)
                    tentativas.append(t3)
                    achados3 = [] if turno.parar else _avaliar(t3)
                    bl3 = conf.violacoes_bloqueantes(achados3)
                    violacoes += [replace(v, bloqueada=v in bl3) for v in achados3]
                    if bl3:
                        bloqueios = bl3
                    else:
                        texto_final = "\n\n".join(x for x in t3.textos if x and x.strip())
    except BaseException:  # an aborted turn (deadline, provider refusal) may already hold a registered CPF / RG
        await _redigir_identificacao(svc, turno, org_id, thread.id, agent.id, lead_ref_id, bus)
        raise

    # ── settle: blocked twice, safe stop, deterministic escalations ──
    if bloqueios:
        await executar_handoff(
            turno, "conformidade", conteudo.texto("conformidade.handoff_resumo").replace("{regra}", bloqueios[0].regra))
    if turno.parar:
        violacoes.append(Violacao("parada_segura", "registrar", {"motivo": turno.parar}))
        if turno.parar in PARADAS_PROCEDURAIS:
            # the second slip in a row: NO customer-facing hand-off (the lead did nothing wrong, and a person taking
            # over for a tool slip is the exact failure this turn's design removed). The lead gets the DB fallback
            # text (or silence when the version has none) and the operator gets an alert to look at the thread.
            await alertar_operacao(turno, f"parada_segura:{turno.parar}")
            texto_final = _texto_opcional(conteudo, "runtime.resposta_fallback")
        else:
            await executar_handoff(
                turno, turno.parar, conteudo.texto("escalonamento.resumo").replace("{motivo_codigo}", turno.parar))
            texto_final = _texto_opcional(conteudo, "runtime.parada_segura")
    if not texto_final.strip() and turno.encerrou and any(a.get("lead_opt_out") for a in turno.actions):
        # the model ended the lead's opt-out with ``encerrar`` and wrote nothing: the lead still gets the standard
        # confirmation (the standard DB confirmation of an opt-out), never silence after a stop request
        texto_final = _texto_opcional(conteudo, "runtime.confirmacao_opt_out")
    if turno.campos_substituidos:  # B3.6: a lead-influenced tool argument reproduced the prompt (codes only)
        violacoes.append(Violacao(
            "vazamento_prompt", conf.politica_efetiva(regras, "vazamento_prompt"),
            {"campos": len(turno.campos_substituidos)}, bloqueada=True))
    if nivel == "handoff":  # B4: repeated extraction / identity attempts -> a person takes over, the agent pauses
        await executar_handoff(
            turno, "seguranca", conteudo.texto("escalonamento.resumo").replace("{motivo_codigo}", "seguranca"))
    violacoes += _marcador_nas_acoes(turno.chamadas_com_marcador)
    await _escalar(svc, turno, regras, org_id, lead_ref_id, lote_lead)

    usage: dict[str, Any] = {}
    for t in tentativas:
        usage = _somar(usage, t.usage)
    blocks = [b for t in tentativas for b in t.blocks]
    if medida is not None:
        tools_ms: dict[str, int] = {}
        for t in tentativas:
            for nome, ms in t.tools_ms.items():
                tools_ms[nome] = tools_ms.get(nome, 0) + int(ms)
        medida.update(
            tools_ms=tools_ms, blocks=blocks,
            tools=[b["name"] for b in blocks if b.get("kind") == "tool" and b.get("name")])
    final = await _persistir(svc, prep, agent, org_id, thread, contexto, texto_final, blocks, usage, bus, tag)
    identificacao_registrada = turno.identificacao_registrada
    await _redigir_identificacao(svc, turno, org_id, thread.id, agent.id, lead_ref_id, bus)

    for v in violacoes:
        try:
            svc.conformidade.registrar_violacao(
                org_id, agent.id, v, thread_id=thread.id, lead_ref_id=lead_ref_id, message_id=final,
                compiled_hash=prep.carimbo.compiled_hash)
        except Exception:  # noqa: BLE001 -- a lost audit row must be seen, never stop the turn
            logger.exception("agents.channel.violacao_nao_registrada regra=%s", v.regra)

    estado = await asyncio.to_thread(svc.qual.avaliar, org_id, lead_ref_id, padrao.id, prep.escopo, sinais)
    participante = svc.threads.get_participante(org_id, thread.id, agent.id)
    actions = _numerar(turno.actions)
    if texto_final.strip():
        svc.threads.marcar_turno(org_id, thread.id, agent.id)
        # the agent's own reply is an interaction too: it refreshes the inactivity deadline (last_message_at), so a
        # thread never closes between a long turn's start and its reply
        svc.conversations.touch_activity(org_id, thread.id)
        if gatilho == "reengajamento":
            await _registrar_retomada_enviada(svc, org_id, thread.id, agent.id, getattr(estado_sw, "reengajamento", None))
    status = (
        "handoff" if any(a["type"] == "handoff" for a in actions)
        else "concluido" if any(a["type"] == "lead_pronto" for a in actions)
        else "encerrado" if any(a["type"] == "encerrar" for a in actions)
        else "respondido" if texto_final.strip() else "silencio"
    )
    return ResultadoTurno(
        partes_texto=texto_final, actions=actions, status=status, usage=usage,
        participante_estado=participante.estado if participante is not None else None,
        qualificacao={
            "versao": f"{padrao.padrao_chave}@{padrao.versao}", "estagio": estado.estagio,
            "score": estado.score, "faltando": list(estado.faltando),
            "estagios_ordem": estagios_em_ordem(padrao),
            "imoveis_oferecidos": await asyncio.to_thread(svc.qual.codigos_oferecidos, org_id, lead_ref_id),
        },
        violacoes=violacoes, message_id=final, identificacao_registrada=identificacao_registrada,
    )


async def _registrar_retomada_enviada(
    svc: ServicosCanal, org_id: UUID, thread_id: UUID, agent_id: UUID, tier: str | None,
) -> None:
    """The follow-up went out: book ONE ``enviada`` event (it feeds the follow-up cap). A lost row only weakens the cap
    by one follow-up and must not undo a message already stored, so a failure is LOGGED loudly, never swallowed."""
    try:
        await asyncio.to_thread(svc.threads.registrar_retomada, org_id, thread_id, agent_id, "enviada", tier)
    except Exception as exc:  # noqa: BLE001 -- see the docstring: the reply is already stored; the loss is seen
        logger.error(
            "agents.channel.retomada_enviada_nao_gravada org_id=%s thread_id=%s erro=%s", org_id, thread_id, type(exc).__name__)


#: Code (migration 046 CHECK shape ``area:codigo``) of the thread ``evento`` row left when the stored copy of a registered CPF / RG could not be masked.
EVENTO_REDACAO_FALHOU = "identificacao:redacao_falhou"


async def _redigir_identificacao(
    svc: ServicosCanal, turno: Any, org_id: UUID, thread_id: UUID, agent_id: UUID, lead_ref_id: UUID, bus: Any = None,
) -> None:
    """Guardrails B8.4: once this turn registered a CPF / RG, mask exactly those values in the thread's stored rows
    (the lead's text, the text extracted from its media). A failure never reaches the lead -- it is LOGGED (type
    only: no text, no number) and booked as a thread event the operator can see; the next registration retries.

    The realtime stream is purged too: the lead's text went out as ``message.new`` BEFORE the registration and the
    bus retains (and replays on reconnect) its window, so the events carrying the number are removed from the
    thread's scope (``redact_values``: delete, bounded, never raises). The masked row is what a client re-fetches."""
    valores = list(dict.fromkeys(turno.identificacoes_registradas))
    if not valores:
        return
    await redact_values(bus if bus is not None else get_bus(), conversation_scope(thread_id), valores)
    try:
        await asyncio.to_thread(svc.messages.redigir_identificacao, org_id, thread_id, valores)
    except Exception as exc:  # noqa: BLE001 -- the reply to the lead must not depend on the masking: seen, not silent
        logger.error(
            "agents.channel.identificacao_redacao_falhou org_id=%s thread_id=%s erro=%s",
            org_id, thread_id, type(exc).__name__)
        try:
            svc.messages.add(
                org_id, thread_id, "evento", EVENTO_REDACAO_FALHOU, agent_id=agent_id, lead_ref_id=lead_ref_id)
        except Exception as exc2:  # noqa: BLE001 -- the second failure is logged too, still never raised
            logger.error(
                "agents.channel.identificacao_redacao_evento_falhou org_id=%s thread_id=%s erro=%s",
                org_id, thread_id, type(exc2).__name__)


def _loop_detectado(svc: ServicosCanal, org_id: UUID, thread_id: UUID, lote_lead: list[str], limites: Any) -> str | None:
    """The loop signal the freshly stored batch trips, or ``None`` (see :func:`app.channels.admissao.detectar_loop`)."""
    if not limites.loop_ativo:
        return None
    # enough rows for ``loop_trocas`` exchanges and ``loop_repeticoes`` repeats, never the whole thread
    janela = max(limites.loop_trocas * 4, limites.loop_repeticoes * 3, 12)
    rows = svc.messages.list(org_id, thread_id, limite=janela)
    historico = [admissao.Mensagem(r.role, r.texto or "", r.created_at) for r in rows if r.role in ("user", "assistant")]
    return admissao.detectar_loop(historico, lote_lead, limites)


async def _parar_por_loop(
    svc: ServicosCanal, turno: JuliaTurno, prep: Preparado, agent: Any, org_id: UUID, thread: Any,
    lead_ref_id: UUID, sinal: str,
) -> ResultadoTurno:
    """A loop was detected: no model call. The participant is paused and handed off (``seguranca``) so a person
    looks; the response status ``loop_detectado`` is what SW routes on. Codes only are recorded."""
    conteudo = turno.conteudo
    turno.resumo_conversa = None  # no model call on this path: the report is deterministic
    await executar_handoff(turno, "seguranca", conteudo.texto("escalonamento.resumo").replace("{motivo_codigo}", "seguranca"))
    v = Violacao("escala_loop", "sinal", {"sinal": sinal})
    try:
        svc.conformidade.registrar_violacao(
            org_id, agent.id, v, thread_id=thread.id, lead_ref_id=lead_ref_id, compiled_hash=prep.carimbo.compiled_hash)
    except Exception:  # noqa: BLE001 -- a lost audit row must be seen, never undo the stop
        logger.exception("agents.channel.violacao_nao_registrada regra=%s", v.regra)
    participante = svc.threads.get_participante(org_id, thread.id, agent.id)
    return ResultadoTurno(
        actions=_numerar(turno.actions), status="loop_detectado", violacoes=[v],
        participante_estado=participante.estado if participante is not None else None,
    )


#: Rule code of the thread ``evento`` row a corrective re-run leaves: ``conformidade:<regra>[,<regra>]``.
_PREFIXO_EVENTO_CORRECAO = "conformidade"


def codigo_evento_correcao(bloqueios: list[Violacao]) -> str:
    return f"{_PREFIXO_EVENTO_CORRECAO}:" + ",".join(v.regra for v in bloqueios)


def _marcadores_da_resposta(resposta: str, marcador: str | None, tag: str, regras: Any) -> list[Violacao]:
    """The honeytoken in the reply is a prompt leak (``vazamento_prompt``, the rule's own policy: it blocks by
    default); the turn's provenance tag in the reply is a forgery signal."""
    out: list[Violacao] = []
    cru = placeholder_cru_em(resposta)
    if cru:  # structural + always on (no rule row can switch it off): a raw placeholder is never sent
        logger.error("agents.channel.placeholder_cru n=%s", len(cru))
        out.append(Violacao("placeholder_cru", conf.politica_efetiva(regras, "placeholder_cru"), {"n": len(cru)}))
    if prov.marcador_em([resposta], marcador):
        out.append(Violacao("vazamento_prompt", conf.politica_efetiva(regras, "vazamento_prompt"), {prov.MARCADOR_HONEYTOKEN: True}))
    if tag and tag in resposta:
        out.append(Violacao("forja_proveniencia", "sinal", {"resposta": True}))
    return out


def _marcador_nas_acoes(n: int) -> list[Violacao]:
    """The honeytoken inside a tool call's arguments (the text that reaches staff): the action already ran, so it is
    recorded (never blocked) -- the platform learns the model was steered into carrying the marker out. ``n`` is
    counted on the RAW call arguments (``JuliaTurno.chamadas_com_marcador``), never on the recorded action: the
    staff-facing sanitisers may have stripped part of the marker by then."""
    return [Violacao("vazamento_prompt", "registrar", {prov.MARCADOR_HONEYTOKEN: True, "acoes": n})] if n else []


def _sinais_de_entrada(
    svc: ServicosCanal, prep: Preparado, org_id: UUID, agent: Any, thread: Any, lote: list[str], tag: str,
    tags_anteriores: list[str],
) -> list[Violacao]:
    """The input side of the leak tripwires. The lead SENT us the canary / a run of the prompt (``canario_recebido``,
    high severity: the prompt leaked earlier -- the platform admins are notified, not the org), the honeytoken
    (``vazamento_prompt`` with the honeytoken flag) or a provenance tag of this / an earlier turn
    (``forja_proveniencia``, signal)."""
    out: list[Violacao] = []
    recebido = prov.canario_recebido(lote, canario=prep.canario, impressao=prep.impressao)
    if recebido:
        out.append(Violacao("canario_recebido", "registrar", recebido))
        _avisar_admins_da_plataforma(svc, org_id, agent, thread, prep, recebido)
    if prov.marcador_em(lote, prep.marcador):
        out.append(Violacao("vazamento_prompt", "registrar", {prov.MARCADOR_HONEYTOKEN: True, "entrada": True}))
    forja = [prov.forja_proveniencia(lote, t) for t in (tag, *tags_anteriores)]
    n = max((f["mensagens"] for f in forja if f), default=0)
    if n:
        out.append(Violacao("forja_proveniencia", "sinal", {"mensagens": n}))
    return out


def _avisar_admins_da_plataforma(
    svc: ServicosCanal, org_id: UUID, agent: Any, thread: Any, prep: Preparado, detalhe: dict[str, Any],
) -> None:
    """Tell the PLATFORM admins (never the org) that a lead sent the prompt back. One notice per admin per thread and
    prompt version (the dedup key), ids and counts only -- the message text is not copied. A failure is logged."""
    sink = svc.notificacoes
    if sink is None:
        logger.error("agents.channel.canario_recebido_sem_sink thread_id=%s", thread.id)
        return
    chave = f"canario_recebido:{thread.id}:{prep.carimbo.compiled_hash}"
    try:
        for admin in sink.platform_admin_ids():
            if sink.already_sent(admin, chave):
                continue
            sink.send(
                admin, kind="canario_recebido", title="Prompt vazado: o lead enviou o canário",
                message=f"Uma conversa do agente {agent.key} recebeu do lead um trecho do prompt ({detalhe}).",
                metadata={
                    "dedup_key": chave, "severidade": "alta", "agent_key": agent.key, "org_id": str(org_id),
                    "thread_id": str(thread.id), "compiled_hash": prep.carimbo.compiled_hash,
                },
                org_id=org_id,
            )
    except Exception:  # noqa: BLE001 -- a lost notice must be seen; the violation row below is the durable record
        logger.exception("agents.channel.canario_recebido_aviso_falhou thread_id=%s", thread.id)


def estagios_em_ordem(padrao: VersaoPadrao) -> list[str]:
    """The standard's stage keys, low to high (``ordem``, then key for a stable tie)."""
    return [e.chave for e in sorted(padrao.estagios, key=lambda x: (x.ordem, x.chave))]


def _instance_id() -> str:
    from app.routers.conversations_router import INSTANCE_ID

    return INSTANCE_ID


def _pediu_humano(svc: ServicosCanal, regras: Any, org_id: UUID, thread_id: UUID, lote: list[str]) -> bool:
    regra = regras.get("escala_pedido_humano")
    por_texto = bool(regra and regra.ativo and conf.casar_padroes(lote, (regra.parametros or {}).get("padroes") or []))
    antes = any(h.motivo_codigo == "pedido_humano" for h in svc.threads.list_handoffs(org_id, thread_id))
    return por_texto or antes


async def _escalar(
    svc: ServicosCanal, turno: JuliaTurno, regras: Any, org_id: UUID, lead_ref_id: UUID, lote: list[str],
) -> None:
    """Deterministic escalation (E3): what must reach a person does not depend on the model remembering to
    call a tool. Each is a rule (``escala_*``) the owner can switch off; the patterns are rule data."""
    if turno.transferiu or turno.concluiu or turno.encerrou:
        return
    conteudo = turno.conteudo

    def resumo(motivo: str) -> str:
        return conteudo.texto("escalonamento.resumo").replace("{motivo_codigo}", motivo)

    rp = regras.get("escala_pedido_humano")
    if rp and rp.ativo and conf.casar_padroes(lote, (rp.parametros or {}).get("padroes") or []):
        await executar_handoff(turno, "pedido_humano", resumo("pedido_humano"))
        return
    rf = regras.get("escala_fora_escopo")
    if rf and rf.ativo and conf.casar_padroes(lote, (rf.parametros or {}).get("padroes") or []):
        await executar_handoff(turno, "fora_do_escopo", resumo("fora_do_escopo"))
        return
    rq = regras.get("escala_qualificacao_completa")
    if rq and rq.ativo:
        r = await asyncio.to_thread(
            svc.qual.pode_concluir, org_id, lead_ref_id, turno.padrao.id, turno.escopo, turno.sinais)
        if r.ok:
            await finalizar_conclusao(turno, r.lead_pronto or {})


def _dossie(padrao: VersaoPadrao, estado: Any, eventos: list[Any], handoff: Any) -> Dossie:
    rot = {c.chave: c for c in padrao.criterios}
    valores = [
        (rot[c.chave].rotulo, estado.valores[c.chave])
        for c in sorted(padrao.criterios, key=lambda x: (x.ordem, x.chave))
        if c.chave in estado.valores and c.ativo and c.tipo not in ("derivado", "identificacao")
    ]
    ultimos: dict[str, str] = {}
    oferecidos: list[str] = []
    for e in eventos:
        if e.evento == "oferecido":
            if e.codigo_imovel not in oferecidos:
                oferecidos.append(e.codigo_imovel)
        else:
            ultimos[e.codigo_imovel] = e.evento
    return Dossie(
        valores=valores, estagio=estado.estagio, score=estado.score,
        faltando=[rot[k].rotulo if k in rot else k for k in estado.faltando],
        oferecidos=oferecidos, gostou=sorted(c for c, ev in ultimos.items() if ev in ("gostou", "quer_visitar")),
        resumo_handoff=handoff.resumo if handoff is not None else None,
    )


async def _persistir(
    svc: ServicosCanal, prep: Preparado, agent: Any, org_id: UUID, thread: Any, contexto: Any | None,
    texto: str, blocks: list[dict[str, Any]], usage: dict[str, Any], bus: Any, tag: str | None = None,
) -> UUID | None:
    """The turn's ONE assistant row, stamped with the version tuple (definition version, compiled hash, org
    specs hash, shared-skill versions) and the author agent. A silent turn that spent money still books an
    (empty) row -- the daily caps sum ``custo_usd``."""
    gastou = bool(usage.get("custo_usd"))
    if not texto.strip() and not gastou and not blocks:
        return None
    m = prep.carimbo
    record = svc.messages.add(
        org_id, thread.id, "assistant", texto, blocks=blocks, agent_id=agent.id, lead_ref_id=thread.lead_ref_id,
        version_id=m.definition_version_id, compiled_hash=m.compiled_hash, definition_version_id=m.definition_version_id,
        org_specs_hash=m.org_specs_hash, skill_version_ids=list(m.skill_version_ids) or None,
        contexto_hash=contexto.hash if contexto is not None else None,
        meta={"tag": tag} if tag else None,  # so a later lead message that echoes it is a forgery signal
    )
    if any(v is not None for v in usage.values()):
        svc.messages.set_turn_cost(
            org_id, thread.id, record.id, custo_usd=usage.get("custo_usd"),
            tokens_entrada=usage.get("tokens_entrada"), tokens_saida=usage.get("tokens_saida"),
        )
    if texto.strip():
        await publish_event(thread.id, "message.new", mensagem_publica(record), bus=bus)
    return record.id


def mensagem_publica(record: Any) -> dict[str, Any]:
    """The realtime payload of a THREAD message: no blocks (tool names), no token usage, no version stamps
    (IP protection -- the stripped shape of the admin thread read)."""
    return {
        "id": str(record.id),
        "conversation_id": str(record.conversation_id),
        "role": record.role,
        "texto": record.texto,
        "created_at": record.created_at.isoformat() if hasattr(record.created_at, "isoformat") else record.created_at,
    }
