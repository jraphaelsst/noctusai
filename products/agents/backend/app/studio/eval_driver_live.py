"""The live :class:`~app.studio.eval_driver.EvalTurnDriver`: the REAL channel turn path over a synthetic thread
(Julia v2 A-RT2; CONTRACT 3.5 E4, 10.3).

What is real: the agent DEFINITION's current DRAFT (compiled for a synthetic org, with the pinned standard), the
turn machinery of :mod:`app.channels.turno` (controls, abuse limits, conformance, the corrective re-run, safe
stop, deterministic escalations), the channel tools of :mod:`app.channels.tool_registry`, the qualification
engine over the pinned standard, and the provider-neutral runtime (``LlmToolRuntime``) calling the real model
with the org's own key.

What is synthetic and isolated: every PER-THREAD store (conversation, messages, shared thread, controls,
conformance, lead qualification, identity) is an in-memory Fake rebuilt for each execution, so an eval run
writes nothing about any lead and cannot touch a tenant's data; social-wiring is replaced by
:class:`FixtureSwClient`, a Fake tools client answering from the roteiro's synthetic catalogue; org specs are the
roteiro's synthetic values (any required one left unset gets a neutral token).

``tipo`` is ``"live"`` ONLY when no provider seam was injected, i.e. the real model produced the turns. A
driver built over a scripted provider (CI) reports ``"fake"`` and can never open the publish gate.

Everything crossing back to the runner is data about WHAT HAPPENED (tool names/args, actions, codes) -- never
the compiled prompt (CONTRACT 0.4).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from cryptography.fernet import Fernet

from app.channels import turno as turno_mod
from app.channels.controles import LeadIdentidade, aplicar_controles
from app.channels.tool_registry import make_channel_tools_factory
from app.config import settings
from app.qualificacao.ident_store import FakeIdentificacaoStore
from app.qualificacao.identificacao import IdentCipher, IdentificacaoService
from app.qualificacao.lead_store import FakeLeadQualificacaoStore
from app.qualificacao.models import EventoImovel, Registro
from app.qualificacao.service import QualificacaoService
from app.runtime.llm_runtime import LlmToolRuntime, LlmTurnLimiter, LlmToolset, make_budget_guard
from app.stores.agent_controles import FakeAgentControleStore
from app.stores.conformidade import FakeConformidadeStore
from app.stores.conversations import FakeConversationStore
from app.stores.messages import FakeMessageStore
from app.stores.threads import FakeThreadStore
from app.studio.eval_driver import (
    Estado,
    Handoff,
    ThreadState,
    ToolCall,
    TurnOutcome,
    Violation,
)
from noctusai_lib.integrations.llm import ToolResult
from noctusai_lib.realtime import FakeRealtimeBus

logger = logging.getLogger(__name__)

__all__ = ["FixtureSwClient", "LiveEvalTurnDriver", "make_live_eval_driver_factory"]

#: A required org spec the roteiro did not provide gets this neutral value (the eval world is synthetic).
_SPEC_NEUTRA = "exemplo"
_CANAL = "whatsapp"


# ── the fixture social-wiring ───────────────────────────────────────────────


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _casa(item: Mapping[str, Any], args: Mapping[str, Any]) -> bool:
    """Does a synthetic catalogue item satisfy the search args? A filter applies only to a field the item HAS:
    a fixture describes what it needs, the rest is not constrained."""
    for campo in ("operacao", "tipo", "cidade"):
        if args.get(campo) and campo in item and str(item[campo]).casefold() != str(args[campo]).casefold():
            return False
    if args.get("bairros") and "bairro" in item:
        if str(item["bairro"]).casefold() not in {str(b).casefold() for b in args["bairros"]}:
            return False
    preco = _num(item.get("preco"))
    if preco is not None:
        if args.get("preco_min") is not None and preco < float(args["preco_min"]):
            return False
        if args.get("preco_max") is not None and preco > float(args["preco_max"]):
            return False
    for campo, arg in (("quartos", "quartos_min"), ("vagas", "vagas_min")):
        valor = _num(item.get(campo))
        if valor is not None and args.get(arg) is not None and valor < float(args[arg]):
            return False
    return True


class FixtureSwClient:
    """The Fake social-wiring tools client of the eval world, fed by the roteiro's synthetic catalogue. Same
    answer shapes as the real ``/api/julia/ferramentas/{nome}`` (CONTRACT 8.3): ``{"data": [...]}`` /
    ``{"data": {...}}``, ``{"erro": ...}`` when unavailable. Records every call (``chamadas``)."""

    def __init__(self, catalogo: tuple[Mapping[str, Any], ...] = ()) -> None:
        self._catalogo = [dict(i) for i in catalogo]
        self.chamadas: list[tuple[str, dict[str, Any]]] = []

    def julia_tools_available(self, org_id: UUID) -> bool:
        return True

    async def julia_ferramenta(self, org_id: UUID, nome: str, args: dict[str, Any]) -> dict[str, Any]:
        self.chamadas.append((nome, dict(args)))
        if nome == "buscar_imoveis":
            excluir = {str(c) for c in (args.get("excluir_codigos") or [])}
            limite = max(1, int(args.get("limite") or 3))
            todos = [i for i in self._catalogo if str(i.get("codigo")) not in excluir and _casa(i, args)]
            return {"data": todos[:limite], "restantes_estimados": max(0, len(todos) - limite)}
        if nome in ("imovel_campanha", "detalhes_imovel"):
            achado = next((i for i in self._catalogo if str(i.get("codigo")) == str(args.get("codigo"))), None)
            return {"data": achado} if achado is not None else {"erro": "nao_encontrado"}
        if nome == "consultar_empreendimento":
            alvo = str(args.get("nome") or "").casefold()
            return {"data": [i for i in self._catalogo if alvo and alvo in str(i.get("empreendimento") or "").casefold()]}
        return {"erro": "ferramenta_desconhecida"}


# ── the call journal ────────────────────────────────────────────────────────


class _Diario:
    """What the toolset was asked to do in the current turn (the runtime's tool events carry no arguments)."""

    def __init__(self) -> None:
        self.chamadas: list[ToolCall] = []

    def limpar(self) -> None:
        self.chamadas = []


def _com_diario(inner_factory: Callable[[Any, Any], LlmToolset | None], diario: _Diario):
    def factory(spec: Any, ctx: Any) -> LlmToolset | None:
        toolset = inner_factory(spec, ctx)
        if toolset is None:
            return None
        handler = toolset.handler

        async def _registrando(call: Any) -> ToolResult:
            res = handler(call)
            if hasattr(res, "__await__"):
                res = await res
            ok = not res.is_error
            try:
                corpo = json.loads(res.content)
                if isinstance(corpo, dict) and corpo.get("ok") is False:
                    ok = False
            except (TypeError, ValueError):
                pass
            diario.chamadas.append(ToolCall(call.name, dict(call.arguments or {}), ok))
            return res

        return replace(toolset, handler=_registrando)

    return factory


# ── the world of one execution ──────────────────────────────────────────────


@dataclass
class _Mundo:
    org_id: UUID
    agent: Any
    version_id: UUID
    specs: dict[str, str]
    svc: turno_mod.ServicosCanal
    runtime: LlmToolRuntime
    bus: FakeRealtimeBus
    sw: FixtureSwClient
    diario: _Diario
    messages: FakeMessageStore
    conversations: FakeConversationStore
    threads: FakeThreadStore
    controles: FakeAgentControleStore
    leads: FakeLeadQualificacaoStore
    lead_externo: str
    channel_ref: dict[str, Any]
    lead_ref_id: UUID | None = None
    concluido: bool = False
    turnos: int = 0


class LiveEvalTurnDriver:
    """Runs ONE inbound lead message at a time through the real turn path of the agent's current DRAFT.

    ``studio_store`` / ``catalog`` / ``padroes`` are the READ side (the definition, its knowledge index and the
    qualification standard); every per-thread store is created here, in memory, per execution.
    ``provider_impl`` (the seed's ``FakeProvider``) is the CI seam: with it the driver is ``fake``.
    ``key_resolver`` defaults to this org's own key only (``make_org_llm_key_resolver``): the eval org is the
    platform org that owns the definition, so that org needs its provider key.
    """

    def __init__(
        self, *, studio_store: Any, catalog: Any, padroes: Any, agent_key: str = "julia",
        key_resolver: Callable[[str, UUID], str | None] | None = None, provider_impl: Any | None = None,
        skills_factory: Any | None = None, tools_factory: Callable[[Any, Any], Any] | None = None,
        daily_cap_usd: float = 0.0, conformidade: Any | None = None,
    ) -> None:
        self._studio = studio_store
        self._catalog = catalog
        self._padroes = padroes
        self._agent_key = agent_key
        self._key_resolver = key_resolver
        self._provider_impl = provider_impl
        self._skills_factory = skills_factory
        self._tools_factory = tools_factory or make_channel_tools_factory()
        self._daily_cap = daily_cap_usd
        #: READ side of the conformance config (rules + abuse limits of the definition's row); copied into the
        #: per-execution Fake so the suite runs under the rules that run in production. ``None`` = code defaults.
        self._conformidade = conformidade
        self._mundo: _Mundo | None = None

    @property
    def tipo(self) -> str:
        return "live" if self._provider_impl is None else "fake"

    def nova_execucao(self) -> None:
        """A fresh thread: drop the whole in-memory world."""
        self._mundo = None

    # ── world construction ──

    def _montar(self, thread: ThreadState) -> _Mundo:
        key = str(thread.fixture.get("agent_key") or self._agent_key)
        definicao = self._studio.get_platform_definition(key)
        if definicao is None:
            raise turno_mod.TurnoRecusado(409, "agente_nao_encontrado", "O agente da avaliação não existe.")
        org_id = definicao.org_id
        draft = self._studio.get_draft(org_id, definicao.id)
        if draft is None:
            raise turno_mod.TurnoRecusado(409, "no_draft", "O agente não tem rascunho para avaliar.")
        declaradas = self._studio.list_spec_defs(org_id, draft.id)
        dados = dict(thread.fixture.get("specs") or {})
        specs = {d.chave: str(dados.get(d.chave) or (d.exemplo or _SPEC_NEUTRA)) for d in declaradas}
        messages, conversations = FakeMessageStore(), FakeConversationStore()
        threads, controles = FakeThreadStore(conversations), FakeAgentControleStore()
        leads = FakeLeadQualificacaoStore()
        ident = IdentificacaoService(FakeIdentificacaoStore(), IdentCipher(Fernet.generate_key()))
        qual = QualificacaoService(self._padroes, leads, identificacao=ident)
        sw = FixtureSwClient(thread.catalogo)
        diario = _Diario()
        runtime = LlmToolRuntime(
            messages=messages,
            key_resolver=self._key_resolver or _chave_do_org(),
            limiter=LlmTurnLimiter(2),
            budget_guard=make_budget_guard(messages=messages, daily_cap_usd=self._daily_cap),
            tools_factory=_com_diario(self._tools_factory, diario),
            provider_impl=self._provider_impl,
            history_messages=int(getattr(settings, "llm_history_messages", 20) or 20),
            max_iterations=int(getattr(settings, "llm_max_tool_iterations", 6) or 6),
        )
        conformidade = self._conformidade_do_mundo(org_id, definicao.id)
        svc = turno_mod.ServicosCanal(
            studio_store=self._studio, catalog=self._catalog, conversations=conversations, messages=messages,
            threads=threads, controles=controles, conformidade=conformidade, qual=qual,
            padroes=self._padroes, ident=ident, sw=sw, skills_factory=self._skills_factory,
        )
        controles.set(org_id, definicao.id, modo=str(thread.fixture.get("modo") or "ligado"))
        externo = f"eval-{uuid4()}"
        return _Mundo(
            org_id=org_id, agent=definicao, version_id=draft.id, specs=specs, svc=svc, runtime=runtime,
            bus=FakeRealtimeBus(), sw=sw, diario=diario, messages=messages, conversations=conversations,
            threads=threads, controles=controles, leads=leads, lead_externo=externo,
            channel_ref={"connection_id": str(UUID(int=1)), "chat_id": externo},
        )

    def _conformidade_do_mundo(self, org_id: UUID, agent_id: UUID) -> FakeConformidadeStore:
        """A per-execution Fake carrying the REAL rules (active, policy, parameters, correction text key) and abuse
        limits configured for the definition's row. A real-store read that fails is not hidden behind defaults:
        the suite would then test rules that do not run in production, so the error propagates (run -> ``erro``)."""
        fake = FakeConformidadeStore()
        if self._conformidade is None:
            return fake
        for regra, cfg in self._conformidade.regras(org_id, agent_id).items():
            fake.definir_regra(
                org_id, agent_id, regra, ativo=cfg.ativo, politica=cfg.politica,
                mensagem_correcao_texto_chave=cfg.mensagem_correcao_texto_chave, parametros=dict(cfg.parametros))
        lim = self._conformidade.limites(org_id, agent_id)
        fake.definir_limites(org_id, agent_id, **{f: getattr(lim, f) for f in lim.__dataclass_fields__})
        return fake

    def _semear(self, m: _Mundo, estado: Estado) -> None:
        """The roteiro's starting estado (criteria already recorded, offer batches already made) into the lead
        store, so the real engine sees it. The first turn creates the thread; the lead ref exists by now."""
        if not estado.criterios and not estado.lotes:
            return
        padrao = turno_mod.padrao_do_turno(m.svc, turno_mod.resolve_agent_for_org(
            m.svc.studio_store, m.org_id, m.agent.key, versao=m.version_id))
        if estado.criterios:
            m.leads.adicionar_registros(
                m.org_id, m.lead_ref_id, agent_id=m.agent.id, versao_id=padrao.id, thread_id=None, message_id=None,
                registros=[Registro(k, v, "migracao") for k, v in estado.criterios.items()])
        for n, lote in enumerate(estado.lotes, start=1):
            for codigo in lote:
                m.leads.adicionar_evento(
                    m.org_id, m.lead_ref_id, agent_id=m.agent.id, thread_id=None,
                    evento=EventoImovel(codigo, "oferecido", "similar", lote=n))

    # ── one turn ──

    async def executar_turno(self, thread: ThreadState, mensagem_lead: str) -> TurnOutcome:
        if self._mundo is None:
            self._mundo = self._montar(thread)
        m = self._mundo
        agora = datetime.now(timezone.utc)
        m.diario.limpar()

        ctl = aplicar_controles(
            org_id=m.org_id, agent_id=m.agent.id, gatilho="mensagem", channel=_CANAL, channel_ref=m.channel_ref,
            controles=m.controles, conversations=m.conversations, threads=m.threads,
            lead=LeadIdentidade(ref=m.lead_externo), contact={"display_name": "Lead de teste"},
            version_id=m.version_id, messages=m.messages, agora=agora)
        th = ctl.thread
        if th is not None and m.lead_ref_id is None:
            m.lead_ref_id = th.lead_ref_id
            self._semear(m, thread.estado)
        if not ctl.prosseguir or th is None:
            return TurnOutcome(estado=self._estado(m), violacoes=(Violation("sem_turno", ctl.status),))

        m.messages.add(m.org_id, th.id, "user", mensagem_lead, lead_ref_id=th.lead_ref_id)
        m.conversations.touch_lead_message(m.org_id, th.id)
        tripped = turno_mod.limite_atingido(m.svc, m.org_id, th.id, m.agent.id, agora)
        if tripped is not None:
            return TurnOutcome(estado=self._estado(m), violacoes=(Violation("limite_atingido", tripped),))

        prep = turno_mod.preparar(m.svc, m.org_id, m.agent, versao=m.version_id, specs=m.specs)
        await m.runtime.preflight(prep.spec.provider, m.org_id)
        slot = m.runtime.try_reserve()
        if slot is None:
            raise turno_mod.TurnoRecusado(429, "capacidade", "Capacidade esgotada.")
        try:
            res = await turno_mod.executar(
                svc=m.svc, prep=prep, agent=m.agent, org_id=m.org_id, thread=th, runtime=m.runtime, slot=slot,
                bus=m.bus, contexto=None, gatilho="mensagem", lote_lead=[mensagem_lead], ultima_resposta_em=agora,
                agora=agora)
        finally:
            await slot.release()
        m.turnos += 1
        m.concluido = m.concluido or any(a["type"] == "lead_pronto" for a in res.actions)
        handoffs = m.threads.list_handoffs(m.org_id, th.id)
        h = handoffs[-1] if handoffs else None
        return TurnOutcome(
            bolhas=tuple(_bolhas(res.partes_texto)),
            ferramentas=tuple(m.diario.chamadas),
            acoes=tuple(a["type"] for a in res.actions),
            estado=self._estado(m),
            handoff=(
                Handoff(para=h.para.papel or str(h.para.agent_id or h.para.user_id), tipo=h.para.tipo)
                if h is not None else None),
            violacoes=tuple(Violation(v.regra, "bloqueada" if v.bloqueada else v.politica) for v in res.violacoes),
            custo_usd=res.usage.get("custo_usd"),
        )

    def _estado(self, m: _Mundo) -> Estado:
        """The estado AFTER the turn, read from the engine's stores (never from what the model said)."""
        if m.lead_ref_id is None:
            return Estado()
        r = turno_mod.resolve_agent_for_org(m.svc.studio_store, m.org_id, m.agent.key, versao=m.version_id)
        padrao = turno_mod.padrao_do_turno(m.svc, r)
        e = m.svc.qual.avaliar(
            m.org_id, m.lead_ref_id, padrao.id, turno_mod.escopo_de(m.agent.key), turno_mod.LeadSinais())
        lotes: dict[int, list[str]] = {}
        for ev in m.svc.qual.eventos(m.org_id, m.lead_ref_id):
            if ev.evento == "oferecido" and ev.lote is not None:
                lotes.setdefault(ev.lote, []).append(ev.codigo_imovel)
        return Estado(
            estagio=e.estagio,
            criterios={k: v for k, v in e.valores.items()},
            lotes=tuple(tuple(lotes[n]) for n in sorted(lotes)),
            identificacao_faltando=tuple(e.identificacao_faltando),
            concluido=m.concluido,
        )


def _bolhas(texto: str) -> list[str]:
    from app.channels.bubbles import split_into_bubbles

    return split_into_bubbles(texto) if texto.strip() else []


def _chave_do_org():
    from app.credentials.org_keys import make_org_llm_key_resolver

    return make_org_llm_key_resolver()


def make_live_eval_driver_factory(
    *, studio_store: Any = None, catalog: Any = None, padroes: Any = None, **kw: Any,
) -> Callable[[], LiveEvalTurnDriver]:
    """The nullary factory ``configure_eval_turn_driver`` takes. Collaborators default to the product's
    production factories, resolved at call time (never at import)."""

    def _factory() -> LiveEvalTurnDriver:
        from app.qualificacao.store import get_padrao_store
        from app.stores.conformidade import get_conformidade_store
        from app.stores.studio_definitions import get_studio_definition_store
        from app.stores.studio_knowledge import get_studio_knowledge_store
        from app.studio.catalog import StoreKnowledgeCatalog

        return LiveEvalTurnDriver(
            studio_store=studio_store or get_studio_definition_store(settings),
            catalog=catalog or StoreKnowledgeCatalog(get_studio_knowledge_store(settings)),
            padroes=padroes or get_padrao_store(settings),
            **{"conformidade": get_conformidade_store(settings), **kw},
        )

    return _factory
