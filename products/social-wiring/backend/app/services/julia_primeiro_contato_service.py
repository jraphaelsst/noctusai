"""Meta lead-form lead -> Julia intake (reconstruction map #33 / wave 12 "Meta form leads first contact").

A lead that arrives from a Meta Lead Ads form is already a SW lead + funil card (the leadgen ingest owns that).
This module makes it ALSO enter the Julia pipeline exactly like a WhatsApp first contact does, when -- and only
when -- the org has Julia on (`whatsapp_connections.agente_leads_ativo` on at least one line):

  1. the `julia_contato` for the lead's phone on the org's Julia line (created on first sight) and an open
     `julia_interacao` -- the same rows a first inbound message creates, so the Julia > Leads list, the timeline and
     Julia's context all see the lead;
  2. Julia speaks first as the approved Cloud template "Abordagem comercial|neutra" (category `primeiro_contato`) --
     WHICH one is decided by the rule in agents' DB (`agent_version_decisoes`, key `abordagem-meta`, edited in the
     agents app; julia-v2 D13) -- SW sends the options and the lead's data, NEVER the rule, and holds no local rule --
     through `julia_disparos_service.primeiro_contato_meta` -- the ONE first-contact sender. Cloud API only: while
     the line is not a configured Cloud one (pending Meta verification) NOTHING is sent -- never WAHA free text,
     never a mass send -- and the lead simply keeps flowing through the ordinary path;
  3. `ultimo_outbound_at` on the contato (so the re-engagement clock and "already talking" see the message) and
     one `primeiro_contato_meta` event recording the outcome (`status`), so a skipped first contact is visible.

Idempotent: a phone whose contato already has any activity (an inbound or an outbound) is never contacted again;
a second delivery of the same lead is therefore a no-op. The lead -> SW lead link is NOT re-done here: the wave-3
Envio (`julia_envio_service.enviar`) attaches the existing lead by phone when the conversation later qualifies, and
never duplicates it.

NEVER raises (the caller is a background leg after Meta's 200); every outcome is a returned status.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.whatsapp.mappers import chat_id_for_phone
from noctusai_lib.primitives.phone import normalize_phone

from app.clients.agents import AgentsClient, AgentsClientError, DecisaoRequest
from app.modules.leads.services.meta_ingest_service import codigo_do_meta_lead
from app.services.julia_agente_service import DEFAULT_AGENT_KEY
from app.services import (
    julia_contatos_service as contatos,
    julia_disparos_service,
    julia_eventos_service as eventos,
    julia_transporte,
)

logger = logging.getLogger(__name__)

ORIGEM = "meta_lead_ads"


#: The decision key in agents: the rule lives in agents' DB (`agent_version_decisoes`), so the owner changes WHEN each
#: template applies by editing that decision in the agents app (julia-v2 D13). SW has NO local copy of the rule.
DECISAO_ABORDAGEM = "abordagem-meta"
ABORDAGENS = ("comercial", "neutra")


def dados_da_decisao(lead: dict[str, Any]) -> dict[str, Any]:
    """What the rule may look at -- campaign/form/ad names and the listing code. Never the lead's name or phone."""
    dados = {
        "codigo_imovel": codigo_do_meta_lead(lead),
        "campanha": lead.get("campaign_name"),
        "formulario": lead.get("form_name"),
        "anuncio": lead.get("ad_name"),
    }
    return {k: (str(v).strip()[:500] if v is not None else None) for k, v in dados.items()}


async def escolher_abordagem(lead: dict[str, Any], agents: Optional[AgentsClient]) -> dict[str, Any]:
    """`{abordagem, regra, motivo}`. `regra`: `versao` (the published version's rule decided) | `padrao_da_versao` (the
    option flagged `padrao` in agents' row) | `indisponivel` (agents cannot be asked: `abordagem` is None and NOTHING is
    sent -- the rule is not in SW, so SW must not invent one; the cause rides in `motivo` and the event records it)."""
    if agents is None:
        return {"abordagem": None, "regra": "indisponivel", "motivo": "agents_nao_configurado"}
    try:
        r = await agents.decidir(DEFAULT_AGENT_KEY, DECISAO_ABORDAGEM, DecisaoRequest(
            opcoes=ABORDAGENS, dados=dados_da_decisao(lead)))
    except AgentsClientError as exc:
        logger.warning("julia: abordagem decision unavailable (%s) -- no first contact sent", type(exc).__name__)
        return {"abordagem": None, "regra": "indisponivel", "motivo": type(exc).__name__}
    return {"abordagem": r.escolha, "regra": r.regra, "motivo": r.motivo}


def _linhas_julia(store: Any, org_id: UUID | str) -> list[Any]:
    return [c for c in store.list_connections(org_id=org_id) if getattr(c, "agente_leads_ativo", False)]


def escolher_conexao(store: Any, org_id: UUID | str) -> Optional[Any]:
    """The org's Julia line: a configured Cloud one first (decrypted, ready to send), else the first Julia line.
    None = the org has Julia off (no line with `agente_leads_ativo`) -> the lead is not taken into Julia at all."""
    linhas = _linhas_julia(store, org_id)
    for c in linhas:
        if getattr(c, "transporte", None) == julia_transporte.TRANSPORTE_CLOUD:
            full = store.get_connection(connection_id=c.id, org_id=org_id, decrypt=True)
            if julia_transporte.cloud_configurada(full):
                return full
    return linhas[0] if linhas else None


async def _registrar_opt_in(agents: Optional[AgentsClient], contato_id: Any) -> None:
    """The lead gave their number in a Meta lead form: the messaging-policy opt-in agents records (`formulario_meta`).
    Best-effort: a failure is logged and never stops the intake."""
    if agents is None:
        return
    try:
        await agents.opt_in(str(contato_id), origem="formulario_meta")
    except AgentsClientError as exc:
        logger.warning("julia: opt-in (formulario_meta) not recorded (%s) contato=%s", type(exc).__name__, contato_id)


def _registrar(client: Any, org_id: UUID | str, contato_id: Any, status: str, motivo: Optional[str] = None,
               decisao: Optional[dict[str, Any]] = None) -> None:
    payload = {"status": status, "motivo": motivo, "origem": ORIGEM}
    if decisao is not None:
        payload["abordagem"] = {"escolha": decisao["abordagem"], "regra": decisao["regra"],
                                "motivo": (decisao.get("motivo") or "")[:200]}
    eventos.emitir(client, org_id, "primeiro_contato_meta", contato_id, payload)


async def iniciar(
    client: Any, org_id: UUID | str, lead: dict[str, Any], *, store: Any,
    transporte_factory: Callable[[Any], julia_transporte.Transporte],
    contexto: Optional[dict[str, str]] = None, agents: Optional[AgentsClient] = None,
) -> dict[str, Any]:
    """Take one freshly ingested Meta lead (`meta_ads_leads` row: `full_name`, `phone`, `answers`...) into Julia.

    Returns `{status, ...}`: `julia_desligada` | `sem_telefone` | `ja_em_atendimento` | `enviado` |
    `transporte_indisponivel` | `modelo_nao_aprovado` | `decisao_indisponivel` | `erro`."""
    try:
        conexao = escolher_conexao(store, org_id)
        if conexao is None:
            return {"status": "julia_desligada"}
        telefone = normalize_phone(lead.get("phone"))
        if not telefone:
            _registrar(client, org_id, None, "sem_telefone")
            return {"status": "sem_telefone"}
        chat_id = chat_id_for_phone(telefone)
        existente = contatos.buscar_contato(client, org_id, conexao.id, chat_id)
        if existente and (existente.get("ultimo_inbound_at") or existente.get("ultimo_outbound_at")):
            return {"status": "ja_em_atendimento", "contato_id": existente["id"]}

        nome = (lead.get("full_name") or "").strip() or None
        contato = contatos.obter_ou_criar_contato(
            client, org_id=org_id, connection_id=conexao.id, chat_id=chat_id, telefone_e164=telefone, nome=nome,
        )
        codigo = codigo_do_meta_lead(lead)
        if codigo:  # the campaign listing, as DATA for the agent (`contexto.operacional.origem.codigo_imovel_campanha`)
            contatos.atualizar_contato(client, contato["id"], {"codigo_imovel_campanha": str(codigo)[:40]})
        contatos.abrir_interacao(client, org_id, contato)
        await _registrar_opt_in(agents, contato["id"])

        cloud = julia_transporte.cloud_configurada(conexao)
        # Ask the agent's rule only when a template can actually go out (no model spend while the line waits for Meta).
        decisao = (await escolher_abordagem(lead, agents) if cloud
                   else {"abordagem": None, "regra": "indisponivel", "motivo": "sem_cloud"})
        if cloud and decisao["abordagem"] is None:  # agents cannot decide and SW holds no rule: the lead is stored, not contacted
            _registrar(client, org_id, contato["id"], "decisao_indisponivel", decisao["motivo"], decisao=decisao)
            return {"status": "decisao_indisponivel", "contato_id": contato["id"]}
        resultado = await julia_disparos_service.primeiro_contato_meta(
            client, org_id, connection=conexao,
            transporte=transporte_factory(conexao) if cloud else None,
            telefone=telefone, nome=nome, abordagem=decisao["abordagem"], contexto=contexto, contato_id=contato["id"],
        )
        if resultado.get("enviado"):
            contatos.registrar_outbound(client, contato["id"])
            _registrar(client, org_id, contato["id"], "enviado", decisao=decisao)
            return {"status": "enviado", "contato_id": contato["id"], "message_id": resultado.get("message_id")}
        motivo = str(resultado.get("motivo") or "transporte_indisponivel")
        _registrar(client, org_id, contato["id"], motivo, decisao=decisao)
        return {"status": motivo, "contato_id": contato["id"]}
    except Exception:
        logger.exception("julia: meta lead intake failed (org=%s) -- the lead is stored; Julia did not take it", org_id)
        return {"status": "erro"}


async def iniciar_com_padroes(org_id: UUID | str, lead: dict[str, Any]) -> dict[str, Any]:
    """`iniciar` wired to the production collaborators (connection store, schema-scoped client, the real transport
    factory, the persona + agency name for the template parameters). The leadgen webhook's background leg calls this;
    tests call `iniciar` with fakes (or inject another callable into `LeadgenWebhookService`). Never raises."""
    try:
        from app.config import settings
        from app.dependencies import coerce_org_uuid, get_admin_client, get_core_client, get_scoped_admin_client
        from app.services import julia_agente_service, julia_aviso_service, julia_conhecimento_service
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        org = coerce_org_uuid(org_id)
        store = build_whatsapp_connection_store(get_admin_client(), encryption_key=settings.encryption_key)
        agents = julia_agente_service.resolve_agents_client(org, cfg=settings)
        nome_agente = await julia_agente_service.nome_do_agente(agents)
        contexto = {
            "nome_julia": nome_agente or julia_conhecimento_service.PERSONA_NOME,
            "nome_imobiliaria": julia_aviso_service.nome_da_org(get_core_client(), org) or "",
        }
        return await iniciar(
            get_scoped_admin_client("social_wiring"), org, lead, store=store,
            transporte_factory=julia_transporte.transporte_da_conexao, contexto=contexto, agents=agents,
        )
    except Exception:
        logger.exception("julia: could not wire the meta lead intake (org=%s)", org_id)
        return {"status": "erro"}


__all__ = [
    "ABORDAGENS", "DECISAO_ABORDAGEM", "ORIGEM", "dados_da_decisao", "escolher_abordagem",
    "escolher_conexao", "iniciar", "iniciar_com_padroes",
]
