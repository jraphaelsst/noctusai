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
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.channels import conformidade as conf
from app.channels.contexto import Dossie, render_contexto_system
from app.channels.opt_out import OptOutService
from app.channels.tool_registry import (
    JuliaTurno,
    SkillFonte,
    SkillsComSpecs,
    SkillsDaVersao,
    executar_handoff,
    finalizar_conclusao,
)
from app.config import settings
from app.qualificacao.models import LeadSinais, VersaoPadrao
from app.qualificacao.prompt import qualificacao_data
from app.realtime import publish_event
from app.runtime.llm_runtime import service_principal_id
from app.runtime.types import AgentSpec, TurnContext
from app.stores.conformidade import Impressao, Violacao
from app.stores.errors import NotFound
from app.stores.studio_definitions_conteudo import OrgSpecRecord
from app.stores.threads import HandoffDestino, contexto_thread, mapa_agentes, rotular_historico
from app.studio.plataforma import escopo_de, padrao_de
from app.studio.resolucao import AgenteResolvido, Carimbo, carimbo, compile_for_org, conteudo_status, resolve_agent_for_org
from app.studio.spec import MAX_COMPILED_PROMPT_CHARS
from app.studio.tools import studio_allowed_tools

logger = logging.getLogger(__name__)

__all__ = [
    "conteudo_completo",
    "estagios_em_ordem",
    "padrao_do_turno",
    "limite_atingido",
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


def padrao_do_turno(svc: ServicosCanal, r: AgenteResolvido) -> VersaoPadrao:
    """The pinned standard version of the agent version; unpinned = the newest PUBLISHED version of the
    agent's standard (its key is part of the platform definition)."""
    pin = getattr(r.versao, "qualificacao_versao_id", None)
    try:
        if pin is not None:
            return svc.padroes.obter_versao(pin)
        chave = padrao_de(r.definicao.key)
        if chave is None:
            raise TurnoRecusado(409, "qualificacao_indisponivel", "O agente não tem padrão de qualificação.")
        return svc.padroes.obter_versao_publicada(chave)
    except NotFound as exc:
        raise TurnoRecusado(409, "qualificacao_indisponivel", "O padrão de qualificação não está publicado.") from exc


def _compilar(
    svc: ServicosCanal, org_id: UUID, agent: Any, *, versao: UUID | str = "ativa",
    specs: Mapping[str, str] | None = None,
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
    compiled = compile_for_org(svc.studio_store, svc.catalog, r, qualificacao=qualificacao_data(padrao))
    status = conteudo_status(svc.studio_store, svc.catalog, r, compiled=compiled)
    if not status.completo:
        raise TurnoRecusado(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.")
    return r, padrao, compiled


def conteudo_completo(svc: ServicosCanal, org_id: UUID, agent: Any) -> bool:
    """Would a turn start? (``status.conteudo_completo`` for SW / Studio.)"""
    try:
        _compilar(svc, org_id, agent)
    except TurnoRecusado:
        return False
    return True


def preparar(
    svc: ServicosCanal, org_id: UUID, agent: Any, *, versao: UUID | str = "ativa",
    specs: Mapping[str, str] | None = None,
) -> Preparado:
    """Everything a turn needs that does not depend on the lead. Raises :class:`TurnoRecusado` (409) BEFORE
    anything is persisted: ``no_active_version`` · ``qualificacao_indisponivel`` · ``conteudo_incompleto`` ·
    ``prompt_too_large``."""
    r, padrao, compiled = _compilar(svc, org_id, agent, versao=versao, specs=specs)
    if len(compiled.texto) > MAX_COMPILED_PROMPT_CHARS:
        raise TurnoRecusado(409, "prompt_too_large", "O prompt compilado passa do limite de tamanho.")
    try:  # proof of use (§A7), under the org that owns the version's rows
        svc.studio_store.save_compiled_prompt(
            r.definicao.org_id, hash=compiled.hash, version_id=r.versao.id, client_id=None,
            texto=compiled.texto, manifest=compiled.manifest_json(),
        )
    except Exception:  # noqa: BLE001 -- proof-of-use must not stop a lead's reply; it must be seen
        logger.exception("agents.channel.compiled_prompt_not_saved org_id=%s hash=%s", org_id, compiled.hash)
    marca = carimbo(svc.studio_store, svc.catalog, r, compiled=compiled)
    policy = dict(r.versao.tool_policy or {})
    can = conf.canario(org_id, r.versao.id, segredo=getattr(settings, "encryption_key", "") or "")
    spec = AgentSpec(
        key=agent.key, provider=r.versao.provider, runtime="llm", model=r.versao.model, effort=r.versao.effort,
        # The canary rides with the prompt (never in the hash): a reply that contains it reproduced the prompt.
        prompt_append=f"{compiled.texto}\n\n{can}", skills=(),
        tools=studio_allowed_tools(knowledge=bool(policy.get("knowledge", True)), web_search=bool(policy.get("web_search", True))),
        max_turns=r.versao.max_turns, prompt_mode="custom", toolset="studio", agent_id=agent.id,
        version_id=r.versao.id, compiled_hash=compiled.hash, web_search=bool(policy.get("web_search", True)),
        knowledge=bool(policy.get("knowledge", True)), client_id=None,
    )
    k = conf.shingle_tokens_da_regra(svc.conformidade.regras(org_id, agent.id).get("vazamento_prompt"))
    impressao = conf.garantir_impressao(svc.conformidade, r.definicao.org_id, r.versao.id, compiled, k)
    return Preparado(r, padrao, compiled, marca, spec, can, impressao, escopo_de(r.definicao.key))


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


@dataclass
class _Tentativa:
    textos: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    esgotou: bool = False


def _urls(texto: str) -> set[str]:
    return {u.rstrip(".,;:!?)]}\"'") for u in _URL.findall(texto)}


def _mensagens_do_lead(messages: Any, org_id: UUID, thread_id: UUID) -> tuple[list[str], int]:
    rows = messages.list(org_id, thread_id, limite=500)
    lead = [r.texto for r in rows if r.role == "user" and r.texto]
    return lead[-_JANELA_LEAD:], len(lead)


def _inicio_do_dia(agora: datetime) -> datetime:
    return agora.astimezone(_SP).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def limite_atingido(svc: ServicosCanal, org_id: UUID, thread_id: UUID, agent_id: UUID, agora: datetime) -> str | None:
    """Per-chat abuse limits, in data (``canal_limites``), enforced under the turn lock: turns per window,
    turns and spend per day. Returns the limit that tripped (a code), or ``None``."""
    lim = svc.conformidade.limites(org_id, agent_id)
    na_janela, _ = svc.messages.thread_usage_since(org_id, thread_id, agora - timedelta(seconds=lim.janela_segundos))
    if na_janela >= lim.max_turnos_janela:
        return "turnos_janela"
    no_dia, custo = svc.messages.thread_usage_since(org_id, thread_id, _inicio_do_dia(agora))
    if no_dia >= lim.max_turnos_dia:
        return "turnos_dia"
    if custo >= lim.max_custo_dia_usd:
        return "custo_dia"
    return None


# ── execution ───────────────────────────────────────────────────────────────


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
            t.usage = {k: evt.get(k) for k in ("custo_usd", "tokens_entrada", "tokens_saida")}
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
    *, svc: ServicosCanal, prep: Preparado, agent: Any, org_id: UUID, thread: Any, runtime: Any, slot: Any,
    bus: Any, contexto: Any | None, gatilho: str, lote_lead: list[str], ultima_resposta_em: datetime | None,
    agora: datetime,
) -> ResultadoTurno:
    """Run the model for ``thread`` and settle everything the turn does. ``lote_lead`` are the texts of the
    batch just stored (empty for a re-engagement)."""
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

    mensagens_lead, n_respostas = _mensagens_do_lead(svc.messages, org_id, thread.id)
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
    skills: SkillFonte | None = SkillsComSpecs(fonte, r.valores)
    sw = svc.sw if (svc.sw is not None and svc.sw.julia_tools_available(org_id)) else None
    turno = JuliaTurno(
        org_id=org_id, agent_id=agent.id, agent_key=agent.key, thread_id=thread.id, lead_ref_id=lead_ref_id,
        conteudo=conteudo, compiled_hash=prep.carimbo.compiled_hash, padrao=padrao, qual=svc.qual,
        threads=svc.threads, skills=skills, sw=sw, ident=svc.ident, handoff_destino=HandoffDestino.dono_da_org(),
        limites=limites, mensagens_lead=mensagens_lead, sinais=sinais, escopo=prep.escopo, estado_sw=estado_sw,
        ferramentas_sw=ferramentas_sw, lote_lead=list(lote_lead),
        opt_out=OptOutService(
            svc.threads, svc.notificacoes, agentes=lambda oid: mapa_agentes(svc.studio_store, oid)),
    )
    estado0 = await asyncio.to_thread(svc.qual.avaliar, org_id, lead_ref_id, padrao.id, prep.escopo, sinais)

    # input-side extraction-attempt signal (signal only, never blocks)
    sinal = conf.sinal_extracao(lote_lead, regras.get("tentativa_extracao"))
    violacoes: list[Violacao] = [Violacao("tentativa_extracao", "sinal", sinal)] if sinal else []

    # the thread context of THIS agent: dossier + last N labelled turns + the newest hand-off note
    n = runtime.history_messages
    ct = contexto_thread(svc.messages, svc.threads, mapa_agentes(svc.studio_store, org_id), org_id, thread.id, agent.id, n=n)
    historico = tuple(rotular_historico(
        ct.mensagens, rotulo_agente=conteudo.texto("historico.rotulo_agente"),
        rotulo_humano=conteudo.texto("historico.rotulo_humano"), rotulo_evento=conteudo.texto("historico.rotulo_evento"),
    ))
    eventos = await asyncio.to_thread(svc.qual.eventos, org_id, lead_ref_id)
    dossie = _dossie(padrao, estado0, eventos, ct.handoff)
    contexto_system = render_contexto_system(
        conteudo, agora=(contexto.agora if contexto is not None else agora),
        fuso=(contexto.fuso if contexto is not None else "America/Sao_Paulo"), estado=estado_sw, dossie=dossie,
    )
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

    def _avaliar(t: _Tentativa) -> list[Violacao]:
        return conf.avaliar_resposta(conf.EntradaConformidade(
            resposta="\n\n".join(x for x in t.textos if x and x.strip()), mensagens_lead=lote_lead, regras=regras,
            canario=prep.canario, impressao=prep.impressao,
            codigos_permitidos=turno.codigos_vistos | codigos_da_thread,
            links_permitidos={*turno.links_vistos, *links_anteriores},
            participante_segue_ativo=not (turno.transferiu or turno.concluiu or turno.encerrou),
            encerrou_ou_transferiu=False,
            criterio_perguntado=padrao.criterio(estado0.proximo_criterio.chave) if estado0.proximo_criterio else None,
            registrou_perfil=bool(estado0.proximo_criterio and estado0.proximo_criterio.chave in turno.registrou_criterios),
            criterios_preenchidos={
                k: padrao.criterio(k).rotulo for k in estado0.valores
                if padrao.criterio(k) is not None and padrao.criterio(k).tipo not in ("derivado", "identificacao")
            },
            registrados_no_turno=turno.registrou_criterios, esgotou_loop=t.esgotou,
        ))

    async with asyncio.timeout(settings.channel_turn_timeout_seconds):
        await publish_event(thread.id, "session.status", {"status": "pensando"}, bus=bus)
        t1 = await _rodar(runtime, prep.spec, ctx, slot, None)
        tentativas.append(t1)
        achados = [] if turno.parar else _avaliar(t1)
        bl = conf.violacoes_bloqueantes(achados)
        violacoes += [replace(v, bloqueada=v in bl) for v in achados]
        texto_final = "\n\n".join(x for x in t1.textos if x and x.strip())
        if bl:
            correcao = " ".join(conteudo.texto(f"conformidade.correcao.{v.regra}").strip() for v in bl)
            svc.messages.add(org_id, thread.id, "evento", correcao, agent_id=agent.id, lead_ref_id=lead_ref_id)
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

    # ── settle: blocked twice, safe stop, deterministic escalations ──
    if bloqueios:
        await executar_handoff(
            turno, "conformidade", conteudo.texto("conformidade.handoff_resumo").replace("{regra}", bloqueios[0].regra))
    if turno.parar:
        violacoes.append(Violacao("parada_segura", "registrar", {"motivo": turno.parar}))
        await executar_handoff(
            turno, turno.parar, conteudo.texto("escalonamento.resumo").replace("{motivo_codigo}", turno.parar))
        texto_final = conteudo.texto("runtime.parada_segura").strip()
    await _escalar(svc, turno, regras, org_id, lead_ref_id, lote_lead)

    usage: dict[str, Any] = {}
    for t in tentativas:
        usage = _somar(usage, t.usage)
    blocks = [b for t in tentativas for b in t.blocks]
    final = await _persistir(svc, prep, agent, org_id, thread, contexto, texto_final, blocks, usage, bus)

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
        },
        violacoes=violacoes, message_id=final,
    )


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
    texto: str, blocks: list[dict[str, Any]], usage: dict[str, Any], bus: Any,
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
