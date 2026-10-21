"""SW's side of the shared lead thread (julia-v2 CONTRACT 5 / 6 / 8.2): everything SW does with agents' thread that is not
a turn.

Julia is HOSTED in agents. The thread, its participants and their states live there; the controls (ligado / drenando /
desligado, per-conversation pause) are agents', decided on every turn under agents' lock. SW therefore:

  * never gates on a cached copy -- `whatsapp_chats.agente_thread_id` / `agente_estado` / `agente_pausado` are a DISPLAY
    MIRROR written only from agents' answers (`espelhar`); the thread id is also used as a LOCATOR, never as permission;
  * forwards what a turn would not carry (Q5): a human attendant's outbound (typed in Conversas or on the phone) and a
    lead message agents declined to answer, via `POST /threads/{id}/mensagens` -- idempotent by `provider_message_id`.
    A lead agents never served has NO thread, so nothing is forwarded for it (agents never stores such a lead);
  * toggles one conversation through `PATCH /threads/{id}/participantes/{agent}` and shows the state agents reports.

Every forward is best-effort and never raises into the path that already delivered the message (the human's send is out,
the lead's message is stored): a failure is logged loudly and the row is simply not in the thread yet -- the same message id
can be forwarded again later without duplicating.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.services.identidade_mascara import ref as ref_log
from app.clients.agents import (
    MAX_MESSAGE_CHARS,
    AgentsClient,
    AgentsClientError,
    ParticipanteInfo,
    ParticipanteNotFound,
    ThreadInfo,
    ThreadNotFound,
    TransicaoInvalida,
)

logger = logging.getLogger(__name__)

#: Turn statuses after which the lead's message is forwarded to the thread (Q5): agents did not answer, but the thread
#: exists and must keep one end-to-end context. Idempotent: a message the turn already stored is `duplicado`.
STATUS_ANEXAR_LEAD = frozenset({
    "conversa_pausada", "conversa_com_outro_responsavel", "conversa_com_outro_agente", "agente_desligado",
    "limite_taxa", "loop_detectado",  # a thread exists; `novo_lead_limitado` has none (agents stored nothing)
})


def thread_id_do_estado(state: Optional[dict[str, Any]]) -> Optional[str]:
    """The thread id from the chat's mirror row (a LOCATOR: it names where to look, it permits nothing)."""
    if not state:
        return None
    return str(state.get("agente_thread_id") or state.get("agente_conversation_id") or "") or None


def espelhar(chat_store: Any, *, connection_id: UUID, chat_id: str, thread_id: Optional[str], estado: Optional[str]) -> None:
    """Write agents' answer onto the chat row (display mirror). Never raises."""
    if not thread_id and not estado:
        return
    try:
        chat_store.set_agente_espelho(connection_id=connection_id, chat_id=chat_id, thread_id=thread_id, estado=estado)
    except Exception as exc:
        logger.error("julia: could not mirror the agent state onto the chat conn=%s (agents has it) (%s)", connection_id, type(exc).__name__)


async def resolver_thread_id(
    client: Optional[AgentsClient], chat_store: Any, *, connection_id: UUID, chat_id: str,
) -> Optional[str]:
    """The agents thread of this chat: the mirror's id, else agents' own lookup by channel ref (None = agents has no
    thread, i.e. it never served this lead). A lookup failure is logged and reads as None."""
    try:
        state = chat_store.get_agente_state(connection_id=connection_id, chat_id=chat_id)
    except Exception as exc:
        logger.error("julia: chat state read failed conn=%s (%s)", connection_id, type(exc).__name__)
        state = None
    tid = thread_id_do_estado(state)
    if tid or client is None:
        return tid
    try:
        info = await client.buscar_thread(connection_id=str(connection_id), chat_id=chat_id)
    except AgentsClientError as exc:
        logger.warning("julia: thread lookup failed (%s) conn=%s", type(exc).__name__, connection_id)
        return None
    if info is None:
        return None
    espelhar(chat_store, connection_id=connection_id, chat_id=chat_id, thread_id=info.thread_id, estado=None)
    return info.thread_id


def _message_id(provider_message_id: Optional[str]) -> str:
    return (provider_message_id or "")[:256] or f"sw-{uuid.uuid4().hex}"


async def encaminhar_humano(
    client: Optional[AgentsClient], chat_store: Any, *, connection_id: UUID, chat_id: str, texto: str,
    provider_message_id: Optional[str], autor_user_id: Optional[str | UUID], at: Optional[datetime] = None,
    autor: Optional[dict[str, Any]] = None,
) -> str:
    """Forward a HUMAN attendant's outbound message to the thread (Q5). Returns `enviado` | `duplicado` | `sem_thread`
    | `sem_autor` | `sem_cliente` | `erro`; never raises.

    `autor` is `{nome, papel}` from the org STAFF list (`autor_para`): the ONLY route that may carry it is this staff append
    (agents' provenance slice rejects `autor` on a lead turn / lead append), so a lead can never claim a staff identity."""
    if client is None:
        return "sem_cliente"
    if not (texto or "").strip():
        return "sem_thread"
    if not autor_user_id:
        logger.error("julia: human message not forwarded conn=%s -- no author user to record", connection_id)
        return "sem_autor"
    tid = await resolver_thread_id(client, chat_store, connection_id=connection_id, chat_id=chat_id)
    if tid is None:
        return "sem_thread"  # a lead Julia never served is never stored (Q5)
    try:
        out = await client.anexar_mensagem(
            tid, role="humano", texto=texto[:MAX_MESSAGE_CHARS], provider_message_id=_message_id(provider_message_id),
            at=at or datetime.now(timezone.utc), autor_user_id=str(autor_user_id),
            autor={"nome": autor["nome"], "papel": autor["papel"]} if autor else None,
        )
    except AgentsClientError as exc:
        logger.error("julia: human message not forwarded (%s) conn=%s", type(exc).__name__, connection_id)
        return "erro"
    return "duplicado" if out.duplicado else "enviado"


async def encaminhar_lead(
    client: Optional[AgentsClient], *, thread_id: Optional[str], mensagens: list[tuple[str, str, Optional[datetime]]],
) -> int:
    """Forward the lead's messages of a batch agents did not answer (`mensagens` = `(texto, provider_message_id, at)`).
    Returns how many were newly appended; never raises. No thread id = agents stored nothing for this lead: nothing to do."""
    if client is None or not thread_id:
        return 0
    novas = 0
    for texto, pid, at in mensagens:
        try:
            out = await client.anexar_mensagem(thread_id, role="user", texto=texto[:MAX_MESSAGE_CHARS],
                                               provider_message_id=_message_id(pid), at=at)
        except AgentsClientError as exc:
            logger.error("julia: lead message not appended (%s) thread=%s", type(exc).__name__, thread_id)
            continue
        novas += 0 if out.duplicado else 1
    return novas


# ── a human takes the conversation over (typed on the phone / sent from the inbox) ──────────
def _candidatos_a_autor(scoped: Any, core: Any, connection: Any, chat_id: str) -> list[UUID]:
    """The users who may have typed a human line this chat: the attendant assigned to the contato, the line's configured hand-off
    target, the org owner, the line's owner (in that order)."""
    from app.services import julia_agente_service as julia
    from app.services import julia_contatos_service

    try:
        contato = julia_contatos_service.buscar_contato(scoped, connection.org_id, connection.id, chat_id)
    except Exception as exc:
        logger.error("julia: contato read failed while resolving the human author conn=%s (%s)", connection.id, type(exc).__name__)
        contato = None
    out: list[UUID] = []
    for cand in ((contato or {}).get("responsavel_user_id"), getattr(connection, "agente_handoff_notificar_user_id", None)):
        if cand:
            out.append(UUID(str(cand)))
    dono = julia.dono_da_org(core, connection.org_id)
    if dono is not None:
        out.append(dono)
    if getattr(connection, "user_id", None):
        out.append(UUID(str(connection.user_id)))
    return out


def autor_humano(
    scoped: Any, core: Any, connection: Any, chat_id: str,
) -> Optional[UUID]:
    """The SW user agents records as the author of a human message whose sender SW cannot see (typed on the phone): the
    attendant assigned to the contato, else the line's configured hand-off target, else the org owner, else the line's owner.
    All are real org users (agents requires an `autor_user_id`). None only when none resolves (logged by the caller)."""
    candidatos = _candidatos_a_autor(scoped, core, connection, chat_id)
    return candidatos[0] if candidatos else None


def autor_para(scoped: Any, core: Any, org_id: UUID | str, user_id: Optional[str | UUID]) -> Optional[dict[str, Any]]:
    """`{user_id, nome, papel}` of a SW user for the staff append: the org STAFF list first (its name and role), else the user's
    core role. None when the user is not a member of the org (then nothing is attributed)."""
    from app.services import julia_staff_service as staff

    try:
        return staff.autor_de_usuario(scoped, core, org_id, user_id)
    except Exception as exc:
        logger.error("julia: could not resolve the staff author org=%s (%s)", org_id, type(exc).__name__)
        return None


def autor_humano_info(scoped: Any, core: Any, connection: Any, chat_id: str) -> Optional[dict[str, Any]]:
    """`autor_humano` with the staff list applied: the first candidate that IS on the staff list wins (its registered name and
    role); otherwise the first candidate, described by its core role."""
    primeiro: Optional[dict[str, Any]] = None
    for cand in _candidatos_a_autor(scoped, core, connection, chat_id):
        info = autor_para(scoped, core, connection.org_id, cand)
        if info is None:
            continue
        if info.get("na_lista"):
            return info
        primeiro = primeiro or info
    return primeiro


async def tomada_humana(
    client: Optional[AgentsClient], chat_store: Any, *, connection_id: UUID, chat_id: str, agent_key: str, texto: str,
    provider_message_id: Optional[str], autor_user_id: Optional[str | UUID], autor: Optional[dict[str, Any]] = None,
) -> str:
    """A human attendant wrote in the chat (L3): append the message to the thread (Q5) and PAUSE the agent in that
    conversation through agents (the actor recorded), mirroring agents' answer. SW sets NO local pause. Returns
    `sem_cliente` | `sem_thread` | `sem_autor` | `pausado` | `ja_fora` | `erro`; never raises.

    `sem_thread`: agents never served this lead, so there is nothing to pause or append (a lead Julia never served is never
    stored). NOC-REMEDIATE[julia-v2-human-first-chat]: a chat a human starts BEFORE the lead ever wrote cannot be pre-paused
    (agents has no thread yet); needs an agents API to open a paused participation -- 2026-10-19"""
    if client is None:
        return "sem_cliente"
    tid = await resolver_thread_id(client, chat_store, connection_id=connection_id, chat_id=chat_id)
    if tid is None:
        return "sem_thread"
    if not autor_user_id:
        logger.error("julia: human takeover not recorded conn=%s -- no author user resolves", connection_id)
        return "sem_autor"
    await encaminhar_humano(
        client, chat_store, connection_id=connection_id, chat_id=chat_id, texto=texto,
        provider_message_id=provider_message_id, autor_user_id=autor_user_id, autor=autor,
    )
    try:
        part = await client.set_participante(
            tid, agent_key, estado="pausado", ator_user_id=str(autor_user_id), motivo="atendente_assumiu",
        )
    except (ParticipanteNotFound, TransicaoInvalida, ThreadNotFound) as exc:
        # already concluded / handed to a broker / not a participant: the human owns it, nothing to pause
        logger.info("julia: takeover found nothing to pause (%s) conn=%s", type(exc).__name__, connection_id)
        return "ja_fora"
    except AgentsClientError as exc:
        logger.error("julia: takeover pause failed at agents (%s) conn=%s", type(exc).__name__, connection_id)
        return "erro"
    espelhar(chat_store, connection_id=connection_id, chat_id=chat_id, thread_id=tid, estado=part.estado)
    return "pausado"


async def devolver_a_julia(
    client: Optional[AgentsClient], chat_store: Any, *, connection_id: UUID, chat_id: str, agent_key: str,
    ator_user_id: Optional[str | UUID],
) -> str:
    """An ARCHIVED contato wrote again: SW hands it back to the agent (un-archived locally by the inbound policy) and so
    RESUMES the agent in that conversation through agents (the pause lives there; the local mirror reset alone would leave
    her silent). Returns `retomado` | `sem_thread` | `sem_cliente` | `sem_autor` | `ja_fora` | `erro`; never raises."""
    if client is None:
        return "sem_cliente"
    tid = await resolver_thread_id(client, chat_store, connection_id=connection_id, chat_id=chat_id)
    if tid is None:
        return "sem_thread"
    if not ator_user_id:
        logger.error("julia: could not resume the agent for a returned contato conn=%s -- no actor user resolves", connection_id)
        return "sem_autor"
    try:
        part = await client.set_participante(tid, agent_key, estado="ativo", ator_user_id=str(ator_user_id), motivo="contato_devolvido")
    except (ParticipanteNotFound, TransicaoInvalida, ThreadNotFound) as exc:
        logger.info("julia: nothing to resume (%s) conn=%s", type(exc).__name__, connection_id)
        return "ja_fora"
    except AgentsClientError as exc:
        logger.error("julia: resume at agents failed (%s) conn=%s", type(exc).__name__, connection_id)
        return "erro"
    espelhar(chat_store, connection_id=connection_id, chat_id=chat_id, thread_id=tid, estado=part.estado)
    return "retomado"


# ── the per-conversation toggle (SW Conversas) ──────────────────────────────
class ConversaSemThread(LookupError):
    """agents has no thread for this chat: there is nothing to pause (a lead it never served)."""


async def alternar_conversa(
    client: AgentsClient, chat_store: Any, *, connection_id: UUID, chat_id: str, agent_key: str, pausado: bool,
    user_id: str | UUID, motivo: Optional[str] = None,
) -> ParticipanteInfo:
    """Pause / resume the agent in ONE conversation: `PATCH participantes` with the SW user as the actor, then mirror
    agents' answer. agents' errors propagate typed (`ParticipanteNotFound`, `TransicaoInvalida`, ...) -- the router maps
    them; SW never flips a local flag on its own."""
    tid = await resolver_thread_id(client, chat_store, connection_id=connection_id, chat_id=chat_id)
    if tid is None:
        raise ConversaSemThread(chat_id)
    try:
        part = await client.set_participante(
            tid, agent_key, estado="pausado" if pausado else "ativo", ator_user_id=str(user_id), motivo=motivo,
        )
    except ThreadNotFound as exc:
        raise ConversaSemThread(chat_id) from exc
    espelhar(chat_store, connection_id=connection_id, chat_id=chat_id, thread_id=tid, estado=part.estado)
    return part


async def estado_da_conversa(
    client: Optional[AgentsClient], chat_store: Any, *, connection_id: UUID, chat_id: str, agent_key: str,
) -> dict[str, Any]:
    """What Conversas shows for the toggle: the state agents REPORTS (`GET thread`), mirrored for the list chips.
    `{thread_id, estado, pausado, reengajamento_suprimido, motivo, fonte}`; `fonte` is `agents` when the read worked,
    `espelho` when it failed (the last mirrored value, flagged so the UI can say it is stale), `nenhuma` with no thread."""
    state = chat_store.get_agente_state(connection_id=connection_id, chat_id=chat_id) or {}
    tid = thread_id_do_estado(state)
    if client is not None:
        try:
            info: Optional[ThreadInfo] = (
                await client.obter_thread(tid) if tid
                else await client.buscar_thread(connection_id=str(connection_id), chat_id=chat_id)
            )
        except ThreadNotFound:
            info = None
        except AgentsClientError as exc:
            logger.warning("julia: thread read failed (%s) conn=%s -- showing the last mirrored state", type(exc).__name__, connection_id)
            return {"thread_id": tid, "estado": state.get("agente_estado"), "pausado": bool(state.get("agente_pausado")),
                    "reengajamento_suprimido": None, "motivo": None, "fonte": "espelho"}
        if info is not None:
            estado = info.estado_de(agent_key)
            espelhar(chat_store, connection_id=connection_id, chat_id=chat_id, thread_id=info.thread_id, estado=estado)
            return {"thread_id": info.thread_id, "estado": estado, "pausado": info.pausado(agent_key),
                    "reengajamento_suprimido": info.reengajamento_suprimido,
                    "motivo": info.reengajamento_suprimido_motivo, "fonte": "agents"}
    return {"thread_id": tid, "estado": None, "pausado": False, "reengajamento_suprimido": None, "motivo": None,
            "fonte": "nenhuma"}


__all__ = [
    "ConversaSemThread", "STATUS_ANEXAR_LEAD", "alternar_conversa", "autor_humano", "autor_humano_info", "autor_para", "devolver_a_julia", "encaminhar_humano",
    "encaminhar_lead", "espelhar", "estado_da_conversa", "resolver_thread_id", "thread_id_do_estado", "tomada_humana",
]
