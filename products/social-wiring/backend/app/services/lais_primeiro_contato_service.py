"""Meta lead-form lead -> Lais intake (reconstruction map #33 / wave 12 "Meta form leads first contact").

A lead that arrives from a Meta Lead Ads form is already a SW lead + funil card (the leadgen ingest owns that).
This module makes it ALSO enter the Lais pipeline exactly like a WhatsApp first contact does, when -- and only
when -- the org has Julia on (`whatsapp_connections.agente_leads_ativo` on at least one line):

  1. the `lais_contato` for the lead's phone on the org's Julia line (created on first sight) and an open
     `lais_interacao` -- the same rows a first inbound message creates, so the Lais > Leads list, the timeline and
     Julia's context all see the lead;
  2. Julia speaks first as the approved Cloud template "Abordagem comercial|neutra" (category `primeiro_contato`),
     through `lais_disparos_service.primeiro_contato_meta` -- the ONE first-contact sender. Cloud API only: while
     the line is not a configured Cloud one (pending Meta verification) NOTHING is sent -- never WAHA free text,
     never a mass send -- and the lead simply keeps flowing through the ordinary path;
  3. `ultimo_outbound_at` on the contato (so the re-engagement clock and "already talking" see the message) and
     one `primeiro_contato_meta` event recording the outcome (`status`), so a skipped first contact is visible.

Idempotent: a phone whose contato already has any activity (an inbound or an outbound) is never contacted again;
a second delivery of the same lead is therefore a no-op. The lead -> SW lead link is NOT re-done here: the wave-3
Envio (`lais_envio_service.enviar`) attaches the existing lead by phone when the conversation later qualifies, and
never duplicates it.

NEVER raises (the caller is a background leg after Meta's 200); every outcome is a returned status.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.whatsapp.mappers import chat_id_for_phone
from noctusai_lib.primitives.phone import normalize_phone

from app.modules.leads.services.meta_ingest_service import codigo_do_meta_lead
from app.services import (
    lais_contatos_service as contatos,
    lais_disparos_service,
    lais_eventos_service as eventos,
    lais_transporte,
)

logger = logging.getLogger(__name__)

ORIGEM = "meta_lead_ads"


def escolher_abordagem(lead: dict[str, Any]) -> str:
    """`comercial` when the lead asked about a specific listing (a code on the lead / the form's REF answer),
    else `neutra`.

    NOC-REMEDIATE[lais-meta-abordagem]: OWNER QUESTION -- the specs name the two first-contact templates
    ("Abordagem comercial" / "Abordagem neutra") but not WHEN each applies. This rule (a listing reference =>
    commercial pitch, otherwise neutral) is the working default; confirm it or give the intended criterion
    (per campaign? per org setting?) -- 2026-10-16"""
    return "comercial" if codigo_do_meta_lead(lead) else "neutra"


def _linhas_julia(store: Any, org_id: UUID | str) -> list[Any]:
    return [c for c in store.list_connections(org_id=org_id) if getattr(c, "agente_leads_ativo", False)]


def escolher_conexao(store: Any, org_id: UUID | str) -> Optional[Any]:
    """The org's Julia line: a configured Cloud one first (decrypted, ready to send), else the first Julia line.
    None = the org has Lais off (no line with `agente_leads_ativo`) -> the lead is not taken into Lais at all."""
    linhas = _linhas_julia(store, org_id)
    for c in linhas:
        if getattr(c, "transporte", None) == lais_transporte.TRANSPORTE_CLOUD:
            full = store.get_connection(connection_id=c.id, org_id=org_id, decrypt=True)
            if lais_transporte.cloud_configurada(full):
                return full
    return linhas[0] if linhas else None


def _registrar(client: Any, org_id: UUID | str, contato_id: Any, status: str, motivo: Optional[str] = None) -> None:
    eventos.emitir(client, org_id, "primeiro_contato_meta", contato_id,
                   {"status": status, "motivo": motivo, "origem": ORIGEM})


async def iniciar(
    client: Any, org_id: UUID | str, lead: dict[str, Any], *, store: Any,
    transporte_factory: Callable[[Any], lais_transporte.Transporte],
    contexto: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Take one freshly ingested Meta lead (`meta_ads_leads` row: `full_name`, `phone`, `answers`...) into Lais.

    Returns `{status, ...}`: `lais_desligada` | `sem_telefone` | `ja_em_atendimento` | `enviado` |
    `transporte_indisponivel` | `modelo_nao_aprovado` | `erro`."""
    try:
        conexao = escolher_conexao(store, org_id)
        if conexao is None:
            return {"status": "lais_desligada"}
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
        contatos.abrir_interacao(client, org_id, contato)

        resultado = await lais_disparos_service.primeiro_contato_meta(
            client, org_id, connection=conexao,
            transporte=transporte_factory(conexao) if lais_transporte.cloud_configurada(conexao) else None,
            telefone=telefone, nome=nome, abordagem=escolher_abordagem(lead), contexto=contexto,
        )
        if resultado.get("enviado"):
            contatos.registrar_outbound(client, contato["id"])
            _registrar(client, org_id, contato["id"], "enviado")
            return {"status": "enviado", "contato_id": contato["id"], "message_id": resultado.get("message_id")}
        motivo = str(resultado.get("motivo") or "transporte_indisponivel")
        _registrar(client, org_id, contato["id"], motivo)
        return {"status": motivo, "contato_id": contato["id"]}
    except Exception:
        logger.exception("lais: meta lead intake failed (org=%s) -- the lead is stored; Julia did not take it", org_id)
        return {"status": "erro"}


async def iniciar_com_padroes(org_id: UUID | str, lead: dict[str, Any]) -> dict[str, Any]:
    """`iniciar` wired to the production collaborators (connection store, schema-scoped client, the real transport
    factory, the persona + agency name for the template parameters). The leadgen webhook's background leg calls this;
    tests call `iniciar` with fakes (or inject another callable into `LeadgenWebhookService`). Never raises."""
    try:
        from app.config import settings
        from app.dependencies import coerce_org_uuid, get_admin_client, get_core_client, get_scoped_admin_client
        from app.services import lais_agente_service, lais_aviso_service, lais_conhecimento_service
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        org = coerce_org_uuid(org_id)
        store = build_whatsapp_connection_store(get_admin_client(), encryption_key=settings.encryption_key)
        nome_agente = await lais_agente_service.nome_do_agente(lais_agente_service.resolve_agents_client(org, cfg=settings))
        contexto = {
            "nome_lais": nome_agente or lais_conhecimento_service.PERSONA_NOME,
            "nome_imobiliaria": lais_aviso_service.nome_da_org(get_core_client(), org) or "",
        }
        return await iniciar(
            get_scoped_admin_client("social_wiring"), org, lead, store=store,
            transporte_factory=lais_transporte.transporte_da_conexao, contexto=contexto,
        )
    except Exception:
        logger.exception("lais: could not wire the meta lead intake (org=%s)", org_id)
        return {"status": "erro"}


__all__ = ["ORIGEM", "escolher_abordagem", "escolher_conexao", "iniciar", "iniciar_com_padroes"]
