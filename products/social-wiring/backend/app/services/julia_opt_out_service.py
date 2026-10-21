"""Julia > Opt-outs: SW's face of agents' lead-level opt-out (owner decisions 2026-10-21).

The opt-out is agents' record (per org: the leads are the org's, not the platform's). SW never keeps a copy of it and never
gates on a cached one: every read here goes to agents, and an unreadable state is reported as unreadable (never as "fine").
This module only composes what the pages need:

  * `historico`        -- agents' newest-first opt-out + reactivation history, enriched with the actor's NAME (core users)
                          and, for an opt-out record, whether it is still the lead's ACTIVE opt-out ("Reativar atendimento");
  * `estado_do_contato` / `estado_da_conversa` -- the consent state of a lead (the operator composer's warning, the badge);
                          `verificado=False` when agents cannot say, so the UI warns instead of staying silent;
  * `marcar_nao_contatar` / `reativar` / `renotificar` -- the human-triggered writes. The actor is always the signed-in user.

A human operator MAY message an opted-out lead (owner: "humans can message with a warning, not blocking"): nothing here
blocks a manual send. The AUTOMATED paths keep their gate (`julia_envio_gate`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import (
    AgentsClient, AgentsClientError, AgentsTokenInvalid, ConsentInfo, LeadDesconhecido, OptOutEvento, OptOutEventoNotFound,
    SemOptOutAtivo, reativacao_motivo,
)
from app.services import julia_contatos_service as contatos
from app.services import julia_eventos_service as eventos
from app.services.julia_agente_service import chat_aliases

logger = logging.getLogger(__name__)

T_CONTATOS = "julia_contatos"
LIMITE_PADRAO = 50
MOTIVO_MARCACAO_MAX = 500
_IN_LOTE = 200


# ── agents access + typed errors ────────────────────────────────────────────
def exigir_agents(client_factory: Callable[[Any], Optional[AgentsClient]], org_id: UUID | str) -> AgentsClient:
    agents = client_factory(org_id)
    if agents is None:
        raise AppException("agents_nao_configurado", "O agente não está configurado.", status_code=503)
    return agents


def traduzir(exc: AgentsClientError) -> AppException:
    """One typed code per failure of a call to agents; never the upstream detail."""
    if isinstance(exc, SemOptOutAtivo):
        return AppException("sem_opt_out_ativo", "Este lead não tem opt-out ativo.", status_code=409)
    if isinstance(exc, LeadDesconhecido):
        return AppException("lead_desconhecido", "O agente ainda não conhece este lead.", status_code=404)
    if isinstance(exc, OptOutEventoNotFound):
        return AppException("opt_out_nao_encontrado", "Registro de opt-out não encontrado.", status_code=404)
    if isinstance(exc, AgentsTokenInvalid):
        return AppException("agents_token_invalido", "O acesso ao agente é inválido.", status_code=502)
    logger.warning("julia: agents opt-out call failed (%s)", type(exc).__name__)
    return AppException("agents_indisponivel", "O agente está indisponível agora.", status_code=502)


# ── read: the history ───────────────────────────────────────────────────────
def nomes_dos_usuarios(core: Any, org_id: UUID | str, ids: set[str]) -> dict[str, str]:
    """`{user_id: nome}` for users of THIS org (a stale or foreign id has no name)."""
    lista = sorted(i for i in ids if i)
    out: dict[str, str] = {}
    for k in range(0, len(lista), _IN_LOTE):
        rows = core.table("noctus_users").select("id, nome, org_id").in_("id", lista[k:k + _IN_LOTE]).execute().data or []
        for r in rows:
            if str(r.get("org_id")) == str(org_id) and r.get("nome"):
                out[str(r["id"])] = str(r["nome"])
    return out


def evento_dict(e: OptOutEvento, *, ator_nome: Optional[str] = None, ativo: Optional[bool] = None) -> dict[str, Any]:
    return {
        "id": e.id, "tipo": e.tipo, "lead_ref": e.lead_ref, "lead_nome": e.lead_nome, "lead_telefone": e.lead_telefone,
        "thread_id": e.thread_id, "agent_id": e.agent_id, "agent_key": e.agent_key, "agent_nome": e.agent_nome,
        "ator_user_id": e.ator_user_id, "ator_nome": ator_nome, "origem": e.origem, "motivo": e.motivo,
        "mensagem_lead": e.mensagem_lead, "em": e.em, "participantes_encerrados": e.participantes_encerrados,
        "notificacao_status": e.notificacao_status, "notificacao_erro": e.notificacao_erro, "notificado_em": e.notificado_em,
        "ativo": ativo,
    }


async def _consentimento_ou_none(agents: AgentsClient, lead_ref: str) -> tuple[bool, Optional[ConsentInfo]]:
    """`(verificado, consent)`; a lead agents never saw is `(True, None)`; any failure is `(False, None)`."""
    try:
        return True, await agents.consentimento(lead_ref)
    except AgentsClientError as exc:
        logger.warning("julia: consent state unreadable lead=%s (%s)", lead_ref, type(exc).__name__)
        return False, None


async def historico(
    agents: AgentsClient, core: Any, org_id: UUID | str, *, limit: int = LIMITE_PADRAO, cursor: Optional[str] = None,
    lead_ref: Optional[str] = None,
) -> dict[str, Any]:
    try:
        pagina = await agents.listar_opt_outs(limit=limit, cursor=cursor, lead_ref=lead_ref)
    except AgentsClientError as exc:
        raise traduzir(exc) from exc
    refs = sorted({e.lead_ref for e in pagina.items if e.tipo == "opt_out"})
    estados = dict(zip(refs, await asyncio.gather(*(_consentimento_ou_none(agents, r) for r in refs))))
    atores = nomes_dos_usuarios(core, org_id, {e.ator_user_id for e in pagina.items if e.ator_user_id})
    itens = []
    for e in pagina.items:
        ativo: Optional[bool] = None
        if e.tipo == "opt_out":
            verificado, info = estados[e.lead_ref]
            if verificado:
                # THIS record is the lead's active opt-out only when agents says the lead is opted out AND names this event
                ativo = bool(info and info.opt_out_ativo and info.evento_id == e.id)
        else:
            ativo = False
        itens.append(evento_dict(e, ator_nome=atores.get(e.ator_user_id or ""), ativo=ativo))
    return {"items": itens, "next_cursor": pagina.next_cursor}


# ── read: the consent state of one lead (composer warning, badge) ───────────
def _estado(lead_ref: Optional[str], verificado: bool, info: Optional[ConsentInfo]) -> dict[str, Any]:
    return {
        "lead_ref": lead_ref, "verificado": verificado,
        "opt_out_ativo": bool(info and info.opt_out_ativo),
        "opt_out_em": info.opt_out_em if info and info.opt_out_ativo else None,
        "motivo": info.opt_out_motivo if info and info.opt_out_ativo else None,
        "origem": info.opt_out_origem if info and info.opt_out_ativo else None,
        "evento_id": info.evento_id if info and info.opt_out_ativo else None,
    }


async def estado_do_contato(agents: Optional[AgentsClient], contato_id: Optional[str]) -> dict[str, Any]:
    """Never raises for agents: an unreadable state is `verificado: false` (the UI warns and still lets a human send)."""
    if not contato_id:
        return _estado(None, True, None)  # no SW lead for this chat yet => nothing to have opted out of
    if agents is None:
        return _estado(contato_id, False, None)
    verificado, info = await _consentimento_ou_none(agents, contato_id)
    return _estado(contato_id, verificado, info)


def contato_da_conversa(client: Any, org_id: UUID | str, connection_id: UUID | str, chat_id: str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(T_CONTATOS).select("*").eq("org_id", str(org_id)).eq("connection_id", str(connection_id))
        .in_("chat_id", sorted(chat_aliases(chat_id))).limit(1).execute().data or []
    )
    return rows[0] if rows else None


async def estado_da_conversa(
    client: Any, agents: Optional[AgentsClient], org_id: UUID | str, connection_id: UUID | str, chat_id: str,
) -> dict[str, Any]:
    contato = contato_da_conversa(client, org_id, connection_id, chat_id)
    return await estado_do_contato(agents, str(contato["id"]) if contato else None)


# ── writes (human-triggered; the actor is the signed-in user) ───────────────
def motivo_obrigatorio(motivo: Optional[str], limite: int = MOTIVO_MARCACAO_MAX) -> str:
    limpo = (motivo or "").strip()
    if not limpo or len(limpo) > limite:
        raise AppException("motivo_obrigatorio", f"Informe o motivo (até {limite} caracteres).", status_code=422)
    return limpo


async def marcar_nao_contatar(
    client: Any, agents: AgentsClient, org_id: UUID | str, contato: dict[str, Any], *, motivo: str, ator_user_id: str,
) -> dict[str, Any]:
    """An operator marks the lead "do not contact": agents records it (origem `operador`, the actor, the reason) and ends
    every agent's participation + notifies the admins. SW stops its own queued follow-ups for the contato."""
    motivo = motivo_obrigatorio(motivo)
    try:
        info = await agents.opt_out(str(contato["id"]), origem="operador", motivo=motivo, ator_user_id=str(ator_user_id))
    except AgentsClientError as exc:
        raise traduzir(exc) from exc
    contatos.bump_gen(client, contato["id"])  # every queued re-engagement job of the contato is stale now
    eventos.emitir(client, org_id, "lead_opt_out", contato["id"], {"origem": "operador", "motivo": "marcado_por_operador"})
    return {"opt_out_ativo": info.opt_out_ativo, "opt_out_em": info.opt_out_em, "evento_id": info.evento_id,
            "participantes_encerrados": info.participantes_encerrados}


async def reativar(agents: AgentsClient, contato: dict[str, Any], *, motivo: str, ator_user_id: str) -> dict[str, Any]:
    """An authorised human puts the lead back into the agents flow (agents lifts the opt-out and re-opens the lead; the
    reason is required and recorded in the history)."""
    try:
        motivo = reativacao_motivo(motivo)
    except ValueError:
        raise AppException("motivo_obrigatorio", "Informe o motivo da reativação (até 500 caracteres).", status_code=422) from None
    try:
        res = await agents.reativar_lead(str(contato["id"]), motivo=motivo, ator_user_id=str(ator_user_id))
    except AgentsClientError as exc:
        raise traduzir(exc) from exc
    return {"opt_out_ativo": res.consent.opt_out_ativo, "evento": evento_dict(res.evento) if res.evento else None}


async def renotificar(agents: AgentsClient, core: Any, org_id: UUID | str, evento_id: str, *, ator_user_id: str) -> dict[str, Any]:
    try:
        evento = await agents.renotificar_opt_out(evento_id, ator_user_id=str(ator_user_id))
    except AgentsClientError as exc:
        raise traduzir(exc) from exc
    atores = nomes_dos_usuarios(core, org_id, {evento.ator_user_id} if evento.ator_user_id else set())
    return evento_dict(evento, ator_nome=atores.get(evento.ator_user_id or ""))


__all__ = [
    "estado_da_conversa", "estado_do_contato", "exigir_agents", "historico", "marcar_nao_contatar", "motivo_obrigatorio",
    "reativar", "renotificar", "traduzir",
]
