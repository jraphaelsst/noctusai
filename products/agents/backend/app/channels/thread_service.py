"""Thread service — the operations on the shared lead thread that more than one route
(or the turn route, once rewired) needs (Julia v2, contract §6 / §8.2):

* :func:`anexar_mensagens` — append the lead's / a human attendant's messages to the thread
  WITHOUT a turn (the off / paused / draining cases of the decision table, and
  ``POST /api/channels/threads/{id}/mensagens``). Idempotent through the ``channel_inbound``
  ledger, exactly like a turn: a replay of an id is a no-op, the same id with other text is a 409.
* :func:`alterar_estado_humano` — a person pauses / resumes the agent in ONE thread (SW toggle,
  Studio Conversas). The transition table is closed; every change is audited (participant event +
  ``agent_audit_log``).
* :func:`apagar_lead` — LGPD delete-by-lead across EVERY thread of every agent (§6.4).
* :func:`progresso_dreno` — the drain progress shown in the Controles card (open threads + ages).
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.stores.errors import Conflict, NotFound, TurnInProgress
from app.stores.messages import MessageRecord
from app.stores.threads import ParticipanteRecord, ThreadAberto

logger = logging.getLogger(__name__)

__all__ = [
    "AnexoResultado",
    "IdempotencyConflict",
    "MensagemEntrada",
    "TransicaoInvalida",
    "alterar_estado_humano",
    "anexar_mensagens",
    "apagar_lead",
    "progresso_dreno",
]

#: Roles a message appended outside a turn may have: the lead (``user``) or a human attendant.
ROLES_ANEXAVEIS = ("user", "humano")


class IdempotencyConflict(Conflict):
    """A known ``provider_message_id`` arrived with other text / for another thread."""

    code = "idempotency_conflict"


class TransicaoInvalida(Conflict):
    """The requested participant state change is not allowed from the current state."""

    code = "transicao_invalida"

    def __init__(self, de: str, para: str) -> None:
        super().__init__(f"participant {de} -> {para} is not allowed")
        self.de, self.para = de, para


@dataclass(frozen=True)
class MensagemEntrada:
    texto: str
    provider_message_id: str
    role: str = "user"
    autor_user_id: UUID | None = None


@dataclass(frozen=True)
class AnexoResultado:
    novas: list[MessageRecord] = field(default_factory=list)
    #: ``provider_message_id`` already in the ledger with the same text (a retry): not appended again.
    duplicadas: list[str] = field(default_factory=list)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _connection_id(thread: Any) -> UUID:
    ref = thread.channel_ref or {}
    try:
        return UUID(str(ref["connection_id"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("thread channel_ref has no connection_id") from exc


def anexar_mensagens(
    *,
    org_id: UUID,
    thread: Any,
    mensagens: Sequence[MensagemEntrada],
    conversations: Any,
    messages: Any,
    inbound: Any,
) -> AnexoResultado:
    """Append ``mensagens`` to ``thread`` (no reply, no model). The caller holds the thread's turn
    lock (an append must not interleave with a running turn). A lead message stamps the thread's
    last-lead-message clock (the drain-idle clock); a human one only its activity clock."""
    for m in mensagens:
        if m.role not in ROLES_ANEXAVEIS:
            raise ValueError(f"role must be one of {ROLES_ANEXAVEIS}; got {m.role!r}")
        if m.role == "humano" and m.autor_user_id is None:
            raise ValueError("a human message needs autor_user_id")
    connection_id = _connection_id(thread)
    known = inbound.find(org_id, connection_id, [m.provider_message_id for m in mensagens])
    novas: list[MessageRecord] = []
    duplicadas: list[str] = []
    for m in mensagens:
        rec = known.get(m.provider_message_id)
        if rec is not None:
            if rec.texto_sha256 != _sha(m.texto) or rec.conversation_id != thread.id:
                raise IdempotencyConflict(f"{m.provider_message_id!r} already received with other content")
            duplicadas.append(m.provider_message_id)
            continue
        novas.append(messages.add(
            org_id, thread.id, m.role, m.texto,
            lead_ref_id=thread.lead_ref_id, autor_user_id=m.autor_user_id,
        ))
        inbound.add(org_id, connection_id, thread.id, m.provider_message_id, _sha(m.texto))
    if any(n.role == "user" for n in novas):
        conversations.touch_lead_message(org_id, thread.id)
    elif novas:
        conversations.touch_activity(org_id, thread.id)
    return AnexoResultado(novas=novas, duplicadas=duplicadas)


#: ``para`` -> the states a person may move the participant FROM. Closed table: a person pauses an
#: active agent and resumes a paused (or ended) one; a ``concluido`` / ``transferido`` thread is the
#: broker's and is never reopened by a toggle.
_DE_HUMANO: dict[str, tuple[str, ...]] = {
    "pausado": ("ativo",),
    "ativo": ("pausado", "encerrado"),
}


def alterar_estado_humano(
    *,
    org_id: UUID,
    thread_id: UUID,
    agent_id: UUID,
    para: str,
    ator_user_id: UUID,
    motivo: str | None,
    threads: Any,
    ate: datetime | None = None,
) -> ParticipanteRecord:
    """A person moves the agent's participant to ``para`` (``pausado`` / ``ativo``), audited with the
    actor, reason and the optional ``ate`` (a timed pause: past it the agent counts as active again).
    Idempotent (already there -> returned unchanged). Raises :class:`NotFound` (the agent does
    not take part in the thread), :class:`TransicaoInvalida` (e.g. resuming a ``concluido``), and
    :class:`~app.stores.threads.OutroAgenteAtivo` (resuming while another agent is active)."""
    if para not in _DE_HUMANO:
        raise ValueError(f"para must be one of {tuple(_DE_HUMANO)}; got {para!r}")
    atual = threads.get_participante(org_id, thread_id, agent_id)
    if atual is None:
        raise NotFound(f"agent {agent_id} does not take part in thread {thread_id}")
    if atual.estado == para:
        return atual
    if atual.estado not in _DE_HUMANO[para]:
        raise TransicaoInvalida(atual.estado, para)
    moved = threads.transicionar(
        org_id, thread_id, agent_id, de=_DE_HUMANO[para], para=para,
        ator_tipo="usuario", ator_id=ator_user_id, motivo=motivo, ate=ate if para == "pausado" else None,
    )
    novo = threads.get_participante(org_id, thread_id, agent_id)
    if not moved:
        # Somebody moved it between our read and the compare-and-set: succeed only if it landed where asked.
        if novo is not None and novo.estado == para:
            return novo
        raise TransicaoInvalida(novo.estado if novo is not None else atual.estado, para)
    assert novo is not None  # the participant exists (the compare-and-set just moved it)
    return novo


def apagar_lead(
    *,
    org_id: UUID,
    ref_externa: str,
    threads: Any,
    conversations: Any,
    retention: Any,
    instance_id: str,
    ttl_seconds: int,
    qualificacao: Any = None,
) -> bool:
    """LGPD delete-by-lead: erase the lead's every thread across all agents (messages, idempotency
    rows, participants, qualification through the lead_ref cascade) and the lead_ref itself, in ONE
    transaction (``agents.apagar_lead``). Idempotent (``False`` = the lead was unknown). Every
    thread's turn lock is taken first — erasing under a running turn would orphan what it writes:
    one held lock aborts with :class:`~app.stores.errors.TurnInProgress` and releases the rest."""
    lead = threads.get_lead_ref_by_externa(org_id, ref_externa)
    if lead is None:
        return False
    held: list[UUID] = []
    try:
        for thread in conversations.list_threads_for_lead(org_id, lead.id):
            if not conversations.try_acquire_turn(org_id, thread.id, instance_id, ttl_seconds):
                raise TurnInProgress(f"thread {thread.id} has a turn in progress")
            held.append(thread.id)
        if qualificacao is not None:
            # The records / events / state / identity of the lead, explicitly (idempotent): the lead_ref FK
            # cascade (037) would erase them too, but the call is the contract -- and the Fake needs it.
            qualificacao.apagar_por_lead(org_id, lead.id)
        erased = retention.delete_lead(org_id, ref_externa)
    except BaseException:
        for thread_id in held:
            conversations.release_turn(org_id, thread_id, instance_id)
        raise
    logger.info("agents.channel.lead_deleted org_id=%s threads=%s found=%s", org_id, len(held), erased)
    return erased


#: The longest age list the drain progress returns (a card, not an export).
_IDADES_MAX = 200


def progresso_dreno(abertos: Sequence[ThreadAberto], dreno_inatividade_dias: int, agora: datetime) -> dict[str, Any]:
    """How far the drain is: an open thread idle for ``dreno_inatividade_dias`` days (since its last LEAD
    message — the participant's entry when the lead never wrote) counts as closed (owner answer Q3), so
    the drain is done once no ACTIVE-and-recent thread is left."""
    limite = timedelta(days=dreno_inatividade_dias)
    idades = sorted(
        ((agora - (t.ultima_mensagem_lead_em or t.entrou_em)) for t in abertos), reverse=True
    )
    ociosas = sum(1 for i in idades if i >= limite)
    efetivas = len(idades) - ociosas
    return {
        "abertas": len(idades),
        "ociosas": ociosas,
        "efetivas": efetivas,
        "concluida": efetivas == 0,
        "idade_max_dias": max((i.days for i in idades), default=0),
        "idades_dias": [i.days for i in idades[:_IDADES_MAX]],
    }
