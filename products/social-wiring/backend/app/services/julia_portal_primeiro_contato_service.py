"""Portal lead (OLX / ImovelWeb / ZAP...) -> Julia speaks first (Lais study S1, owner 2026-11-17).

Sibling of `julia_primeiro_contato_service` (the Meta lead-form opener). A portal lead is already a SW lead + funil card
(the portal ingest owns that). This module makes Julia open the conversation, when -- and only when -- every one of these holds:

  * the org has Julia on (a WAHA line with `agente_leads_ativo`) AND the per-org switch
    `julia_reengajamento_config.portal_primeiro_contato_ativo` is on (DEFAULT OFF; the owner enables it in Julia >
    Reengajamento) -- the outbound gate flow `primeiro_contato_portal`;
  * the lead is NEW: it reached us after go-live (`agente_leads_ativado_em`) and within `JANELA_CHEGADA`, so a drained /
    retried / re-ingested old event never opens a conversation;
  * the lead's phone has no conversation yet. A portal RE-ENTRY of the same person (a new portal lead id, same phone) finds
    the contato with activity, or a recorded opener, and is `reentrada` -- recorded, never a second opener;
  * it is business hours (08:00-19:59 America/Sao_Paulo, the same window as the hours re-engagement tier);
  * the lead did not opt out (agents' consent state, fail-closed) and the evaluation (testing) mode allows the number.

The opener is a normal WAHA first message -- NOT a Cloud template -- so it IS the disclosure bubble: the org's
`mensagem_inicial` (AI disclosure + the privacy-notice `{link}`), exactly the text Julia sends before her first reply to an
inbound lead. The WAHA client enforces the line's send policy (a shadow / read-only line refuses; recorded as `envio_recusado`).
The outbound is stored with `origem='julia'` and stamps `ultimo_outbound_at`, so its `fromMe` echo is never read as a human
takeover and the lead's reply continues the normal turn (which does not repeat the disclosure).

Every outcome is a returned status AND one `primeiro_contato_portal` event (`{status, motivo?, origem, origem_lead_id}`: ids
and codes only, no phone / name). NEVER raises -- the caller is a background leg after the vendor's 200 and after the lead is stored.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.whatsapp.mappers import chat_id_for_phone
from noctusai_lib.primitives.phone import normalize_phone

from app.clients.agents import AgentsClient
from app.services import (
    julia_avaliacao_service,
    julia_contatos_service as contatos,
    julia_envio_gate,
    julia_eventos_service as eventos,
    julia_origem_service,
    julia_reengajamento_service,
    julia_transporte,
)
from app.services.julia_agente_service import DEFAULT_AGENT_KEY, parse_instante

logger = logging.getLogger(__name__)

TIPO_EVENTO = "primeiro_contato_portal"
#: A portal lead older than this at the moment we act on it (retry drain, late replay) is not "new": no opener.
JANELA_CHEGADA = timedelta(hours=6)
#: One opener per lead per conversation window: a recorded opener inside this window blocks another, even when the contato's
#: activity stamps were reset.
JANELA_ABERTURA = timedelta(days=30)


def _linha_waha_da_julia(store: Any, org_id: UUID | str) -> tuple[Optional[Any], bool]:
    """`(linha, julia_ligada)`: the org's first Julia line that speaks WAHA free text. `julia_ligada` False = no line has
    Julia on at all (the org is simply not on Julia: nothing is recorded). A Julia line that is Cloud-only -> `(None, True)`."""
    linhas = [c for c in store.list_connections(org_id=org_id) if getattr(c, "agente_leads_ativo", False)]
    if not linhas:
        return None, False
    for c in linhas:
        if (getattr(c, "transporte", None) or julia_transporte.TRANSPORTE_WAHA) == julia_transporte.TRANSPORTE_WAHA:
            return store.get_connection(connection_id=c.id, org_id=org_id, decrypt=True), True
    return None, True


def _registrar(client: Any, org_id: UUID | str, contato_id: Any, lead: dict[str, Any], status: str,
               motivo: Optional[str] = None) -> None:
    eventos.emitir(client, org_id, TIPO_EVENTO, contato_id, {
        "status": status, "motivo": motivo, "origem": lead.get("origem"), "origem_lead_id": lead.get("origem_lead_id"),
    })


def _abertura_recente(client: Any, org_id: UUID | str, contato_id: Any, agora: datetime) -> bool:
    """A `primeiro_contato_portal` event with status `enviado` for this contato inside `JANELA_ABERTURA`."""
    rows = (
        client.table(eventos.TABLE).select("payload,created_at").eq("org_id", str(org_id)).eq("tipo", TIPO_EVENTO)
        .eq("contato_id", str(contato_id)).limit(50).execute().data or []
    )
    corte = agora - JANELA_ABERTURA
    for r in rows:
        if (r.get("payload") or {}).get("status") != "enviado":
            continue
        quando = parse_instante(r.get("created_at"))
        if quando is None or quando >= corte:
            return True  # unreadable time: assume recent (never a second opener on doubt)
    return False


async def iniciar(
    client: Any, org_id: UUID | str, lead: dict[str, Any], *, store: Any,
    transporte_factory: Callable[[Any], julia_transporte.Transporte] = julia_transporte.transporte_da_conexao,
    mensagem_inicial: Callable[[], Any], message_store_factory: Callable[[UUID | str], Any],
    agents: Optional[AgentsClient] = None, core: Any = None, agora: Optional[datetime] = None,
) -> dict[str, Any]:
    """Take one freshly ingested portal lead into Julia as its opener. `lead`: `{origem, origem_lead_id, phone, name,
    chegou_em}` (`chegou_em` = when WE received it). `mensagem_inicial()` returns the finished disclosure text (awaitable or
    plain; raising = not sent).

    Returns `{status, ...}`: `julia_desligada` | `sem_linha_waha` | `desativado` | `sem_telefone` | `anterior_ao_golive` |
    `lead_antigo` | `reentrada` | `fora_do_horario` | `restrito_avaliacao` | `avaliacao_indisponivel` | `bloqueado` (gate / opt-out,
    `motivo` says which) | `aviso_indisponivel` | `envio_recusado` | `enviado` | `erro`."""
    agora = agora or datetime.now(timezone.utc)
    try:
        conexao, julia_ligada = _linha_waha_da_julia(store, org_id)
        if not julia_ligada:
            return {"status": "julia_desligada"}
        if conexao is None:
            _registrar(client, org_id, None, lead, "sem_linha_waha")
            return {"status": "sem_linha_waha"}
        if julia_reengajamento_service.obter_config(client, org_id).get("portal_primeiro_contato_ativo") is not True:
            _registrar(client, org_id, None, lead, "desativado")
            return {"status": "desativado"}
        telefone = normalize_phone(lead.get("phone"))
        if not telefone:
            _registrar(client, org_id, None, lead, "sem_telefone")
            return {"status": "sem_telefone"}

        chegou = parse_instante(lead.get("chegou_em"))
        ativado = parse_instante(getattr(conexao, "agente_leads_ativado_em", None))
        if chegou is None or ativado is None or chegou < ativado:  # unreadable (either time) -> NO, fail closed
            _registrar(client, org_id, None, lead, "anterior_ao_golive")
            return {"status": "anterior_ao_golive"}
        if agora - chegou > JANELA_CHEGADA:
            _registrar(client, org_id, None, lead, "lead_antigo")
            return {"status": "lead_antigo"}

        chat_id = chat_id_for_phone(telefone)
        existente = contatos.buscar_contato(client, org_id, conexao.id, chat_id)
        if existente and (
            existente.get("ultimo_inbound_at") or existente.get("ultimo_outbound_at")
            or _abertura_recente(client, org_id, existente["id"], agora)
        ):
            _registrar(client, org_id, existente["id"], lead, "reentrada")
            return {"status": "reentrada", "contato_id": existente["id"]}
        if not julia_reengajamento_service.dentro_do_horario(agora):
            _registrar(client, org_id, existente["id"] if existente else None, lead, "fora_do_horario")
            return {"status": "fora_do_horario"}

        nome = (lead.get("name") or "").strip() or None
        contato = contatos.obter_ou_criar_contato(
            client, org_id=org_id, connection_id=conexao.id, chat_id=chat_id, telefone_e164=telefone, nome=nome,
            origem=lambda: julia_origem_service.resolver_origem(client, org_id, telefone=telefone),
        )
        contatos.abrir_interacao(client, org_id, contato)

        restrito = await julia_avaliacao_service.restricao_primeiro_contato(
            agents, core, org_id, getattr(conexao, "agente_leads_key", None) or DEFAULT_AGENT_KEY, telefone)
        if restrito is not None:
            _registrar(client, org_id, contato["id"], lead, restrito)
            return {"status": restrito, "contato_id": contato["id"]}

        fluxo = julia_envio_gate.Fluxo.PRIMEIRO_CONTATO_PORTAL
        try:
            liberacao = julia_envio_gate.exigir(client, org_id, conexao.id, fluxo, contato_id=contato["id"])
            await julia_envio_gate.exigir_sem_opt_out(
                client, org_id, conexao.id, fluxo, contato_id=contato["id"], agents=agents)
        except julia_envio_gate.EnvioBloqueado as exc:  # already logged + `envio_bloqueado` event by the gate
            _registrar(client, org_id, contato["id"], lead, "bloqueado", exc.motivo)
            return {"status": "bloqueado", "motivo": exc.motivo, "contato_id": contato["id"]}

        try:
            texto = mensagem_inicial()
            if asyncio.iscoroutine(texto):
                texto = await texto
        except Exception as exc:  # the disclosure must never go out with a hole in it
            logger.error("julia: portal opener -- cannot build the disclosure org=%s (%s)", org_id, type(exc).__name__)
            _registrar(client, org_id, contato["id"], lead, "aviso_indisponivel", type(exc).__name__)
            return {"status": "aviso_indisponivel", "contato_id": contato["id"]}

        julia_envio_gate.conferir(liberacao, conexao.id)
        try:
            resp = await transporte_factory(conexao).enviar_texto(telefone, texto)
        except Exception as exc:  # incl. the WAHA line policy refusing a shadow / read-only line
            logger.warning("julia: portal opener refused by the transport org=%s line=%s (%s)", org_id, conexao.id, type(exc).__name__)
            _registrar(client, org_id, contato["id"], lead, "envio_recusado", type(exc).__name__)
            return {"status": "envio_recusado", "contato_id": contato["id"]}

        _guardar_saida(message_store_factory, org_id, conexao, chat_id, texto, resp)
        contatos.registrar_outbound(client, contato["id"])
        _registrar(client, org_id, contato["id"], lead, "enviado")
        return {"status": "enviado", "contato_id": contato["id"]}
    except Exception as exc:
        logger.error("julia: portal lead intake failed (org=%s) -- the lead is stored; Julia did not take it (%s)", org_id, type(exc).__name__)
        return {"status": "erro"}


def _guardar_saida(factory: Callable[[UUID | str], Any], org_id: UUID | str, conexao: Any, chat_id: str, texto: str, resp: Any) -> None:
    """Store the opener as an own (`origem='julia'`) outbound so its `fromMe` echo is never read as a human takeover. Best-effort:
    the message already went out, so a failure is logged and the intake carries on."""
    from app.schemas.whatsapp import extract_waha_message_id
    from app.services.message_store import DuplicateMessage

    try:
        factory(org_id).record(
            session_id=chat_id, raw_sender=chat_id, direction="outbound", body=texto,
            provider_message_id=extract_waha_message_id(resp) if isinstance(resp, dict) else None, authorized=True,
            structured_payload={"origem": "julia"}, connection_id=conexao.id, chat_id=chat_id, origem="julia",
        )
    except DuplicateMessage:
        logger.info("julia: portal opener echo already recorded")
    except Exception as exc:
        logger.error("julia: portal opener outbound record failed org=%s (%s)", org_id, type(exc).__name__)


def lead_de_olx(lead: Any, chegou_em: Any) -> dict[str, Any]:
    return {"origem": "olx", "origem_lead_id": lead.origin_lead_id, "phone": lead.full_phone, "name": lead.name,
            "chegou_em": chegou_em}


def lead_de_imovelweb(lead: Any, chegou_em: Any) -> dict[str, Any]:
    return {"origem": "imovelweb", "origem_lead_id": lead.event_id, "phone": lead.full_phone, "name": lead.name,
            "chegou_em": chegou_em}


async def iniciar_com_padroes(org_id: UUID | str, lead: dict[str, Any]) -> dict[str, Any]:
    """`iniciar` wired to the production collaborators. Never raises."""
    try:
        from app.config import settings
        from app.dependencies import coerce_org_uuid, get_admin_client, get_core_client, get_scoped_admin_client
        from app.services import julia_agente_service, julia_aviso_service
        from app.services.message_store import MessageStore
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        org = coerce_org_uuid(org_id)
        scoped, core = get_scoped_admin_client("social_wiring"), get_core_client()
        agents = julia_agente_service.resolve_agents_client(org, cfg=settings)

        async def mensagem() -> str:
            nome_agente = await julia_agente_service.nome_do_agente(agents) if agents is not None else None
            return julia_agente_service.mensagem_inicial_pronta(
                julia_aviso_service.obter_ou_criar(scoped, core, org), nome_agente)

        return await iniciar(
            scoped, org, lead, store=build_whatsapp_connection_store(get_admin_client(), encryption_key=settings.encryption_key),
            mensagem_inicial=mensagem, message_store_factory=lambda o: MessageStore(admin_supabase=get_admin_client(), org_id=o),
            agents=agents, core=core,
        )
    except Exception as exc:
        logger.error("julia: could not wire the portal lead intake (org=%s) (%s)", org_id, type(exc).__name__)
        return {"status": "erro"}


def iniciar_em_background(org_id: UUID | str, lead: dict[str, Any], *, intake: Optional[Callable[..., Any]] = None) -> dict[str, Any]:
    """Sync entry for the portal webhook services (their `process_lead` runs in a worker thread, so it owns a loop). Never raises."""
    try:
        return asyncio.run((intake or iniciar_com_padroes)(org_id, lead))
    except Exception as exc:
        logger.error("julia: portal opener leg failed (org=%s) (%s)", org_id, type(exc).__name__)
        return {"status": "erro"}


__all__ = [
    "JANELA_ABERTURA", "JANELA_CHEGADA", "TIPO_EVENTO", "iniciar", "iniciar_com_padroes", "iniciar_em_background",
    "lead_de_imovelweb", "lead_de_olx",
]
