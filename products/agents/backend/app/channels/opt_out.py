"""A lead asked to stop: record it, stop every agent, and TELL the owner (never a silent disengage).

Owner decision (2026-10-21). One service for every way an opt-out happens -- the model's ``encerrar`` tool
(``lead_pediu_parar``), an operator, the social-wiring integration -- so each of them leaves the same record:

1. :meth:`ThreadStore.registrar_opt_out_evento` -- ONE transaction: the lead-level ``opt_out_em``, every agent's
   participation in every thread of the lead ended, and the ``lead_opt_out_eventos`` row (who, why, what the lead
   said). Idempotent: an opt-out already in force records no second event.
2. :meth:`OptOutService.notificar` -- an in-app notice to the org's owners/admins, deduped on the event. Its
   outcome is written back on the event (``enviada`` / ``falhou`` + the error), so a notice that did not go out is
   a visible row and an error log, never a skipped step. A notification failure NEVER undoes or blocks the opt-out
   (the lead asked to stop; the stop stands).
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from app.notifications import NotificationSink
from app.stores.threads import OPT_OUT_MOTIVO_PADRAO, OptOutEventoRecord, OptOutResultado, ThreadStore

logger = logging.getLogger(__name__)

__all__ = ["KIND_LEAD_OPT_OUT", "OptOutService", "SemDestinatarios", "dedup_key"]

KIND_LEAD_OPT_OUT = "agents.lead_opt_out"
_TITULO = "Lead pediu para não ser mais contatado"
_ERRO_MAX = 500


class SemDestinatarios(Exception):
    """The org has no owner/admin to notify -- a failed notification (recorded), never a skipped one."""


def dedup_key(evento_id: UUID) -> str:
    return f"{KIND_LEAD_OPT_OUT}:{evento_id}"


class OptOutService:
    """``threads`` is the thread store; ``sink`` the notification seam (``None`` is a configuration error that is
    RECORDED as a failed notification); ``agentes`` maps ``org_id -> {agent_id: (key, nome)}`` for the message."""

    def __init__(
        self, threads: ThreadStore, sink: NotificationSink | None,
        agentes: Callable[[UUID], Mapping[UUID, tuple[str, str]]] | None = None,
    ) -> None:
        self._threads = threads
        self._sink = sink
        self._agentes = agentes

    def registrar(
        self, org_id: UUID, ref_externa: str, *, origem: str, motivo: str | None = None,
        mensagem_lead: str | None = None, agent_id: UUID | None = None, thread_id: UUID | None = None,
        ator_user_id: UUID | None = None, em: datetime | None = None,
    ) -> OptOutResultado:
        """Record the opt-out and, for a NEW event, notify. Returns the result with the event as it stands
        after the notification outcome was written back."""
        self._threads.upsert_lead_ref(org_id, ref_externa)
        res = self._threads.registrar_opt_out_evento(
            org_id, ref_externa, em=em, origem=origem, motivo=motivo, mensagem_lead=mensagem_lead,
            agent_id=agent_id, thread_id=thread_id, ator_user_id=ator_user_id,
        )
        if not res.encontrado or res.evento is None or not res.evento_novo:
            return res
        evento = self.notificar(org_id, res.evento, ref_externa)
        return OptOutResultado(res.encontrado, res.participantes_encerrados, evento, res.evento_novo)

    def notificar(self, org_id: UUID, evento: OptOutEventoRecord, ref_externa: str) -> OptOutEventoRecord:
        """Tell the org's owners/admins and write the outcome on the event. Never raises."""
        try:
            self._enviar(org_id, evento, ref_externa)
        except Exception as exc:  # noqa: BLE001 -- the opt-out stands; the failure is recorded + logged below
            erro = f"{type(exc).__name__}: {exc}"[:_ERRO_MAX]
            logger.error(
                "agents.lead_opt_out.notificacao_falhou org_id=%s evento_id=%s error=%s", org_id, evento.id, erro,
                exc_info=True,
            )
            return self._marcar(org_id, evento, "falhou", erro)
        return self._marcar(org_id, evento, "enviada", None)

    # ── internals ────────────────────────────────────────────────────────

    def _marcar(self, org_id: UUID, evento: OptOutEventoRecord, status: str, erro: str | None) -> OptOutEventoRecord:
        try:
            atual = self._threads.marcar_notificacao_opt_out(org_id, evento.id, status=status, erro=erro)
        except Exception:  # noqa: BLE001 -- losing the status write must be seen, never undo the opt-out
            logger.exception("agents.lead_opt_out.status_nao_gravado org_id=%s evento_id=%s", org_id, evento.id)
            return evento
        return atual or evento

    def _enviar(self, org_id: UUID, evento: OptOutEventoRecord, ref_externa: str) -> None:
        if self._sink is None:
            raise RuntimeError("notification sink not configured")
        admins = self._sink.org_admin_ids(org_id)
        if not admins:
            raise SemDestinatarios(f"no owner/admin to notify in org {org_id}")
        titulo, mensagem = self._texto(org_id, evento, ref_externa)
        chave = dedup_key(evento.id)
        metadata = {
            "evento_id": str(evento.id), "lead_ref": ref_externa,
            "thread_id": str(evento.thread_id) if evento.thread_id else None,
            "dedup_key": chave, "product": "agents",
        }
        for user_id in admins:
            if self._sink.already_sent(user_id, chave):
                continue
            self._sink.send(
                user_id, kind=KIND_LEAD_OPT_OUT, title=titulo, message=mensagem, metadata=metadata, org_id=org_id,
            )

    def _texto(self, org_id: UUID, evento: OptOutEventoRecord, ref_externa: str) -> tuple[str, str]:
        lead = self._threads.get_lead_ref(org_id, evento.lead_ref_id)
        nome = ((lead.contato or {}).get("nome") if lead is not None else None) or ref_externa
        if evento.origem == "agente":
            nome_agente = None
            if self._agentes is not None and evento.agent_id is not None:
                nome_agente = self._agentes(org_id).get(evento.agent_id, (None, None))[1]
            quem = f"pelo agente {nome_agente}" if nome_agente else "por um agente"
        elif evento.origem == "operador":
            quem = "por um operador"
        else:
            quem = "pela integração"
        motivo = "não informado" if evento.motivo == OPT_OUT_MOTIVO_PADRAO else evento.motivo
        mensagem = (
            f"{nome} pediu para parar de receber mensagens. Registrado {quem}; nenhum agente vai contatar "
            f"esse lead novamente. Motivo: {motivo}"
        )
        return _TITULO, mensagem
