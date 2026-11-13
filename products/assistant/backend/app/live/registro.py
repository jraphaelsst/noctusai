"""Persistence of the live reply: the intake outcome read + the append-only attempt event (migration 021).

LGPD: nothing here receives a phone, a message body or a reply text -- only ids, an enum and counts."""
from __future__ import annotations

from typing import Any, Callable, Optional

#: The closed outcome enum (mirrors the CHECK of `assistant.respostas_eventos`).
ENVIADA = "enviada"
ENVIADA_PARCIAL = "enviada_parcial"
RECUSADA_LISTA = "recusada_lista"
AGENTE_DESLIGADO = "agente_desligado"
CONTROLE_INDISPONIVEL = "controle_indisponivel"
SEM_ATENDIMENTO = "sem_atendimento"
ERRO_TURNO = "erro_turno"
ERRO_ENVIO = "erro_envio"
MENSAGEM_ANTIGA = "mensagem_antiga"
DESFECHOS = (
    ENVIADA, ENVIADA_PARCIAL, RECUSADA_LISTA, AGENTE_DESLIGADO, CONTROLE_INDISPONIVEL, SEM_ATENDIMENTO,
    ERRO_TURNO, ERRO_ENVIO, MENSAGEM_ANTIGA,
)

#: Intake outcomes that mean "this row was NOT taken in as a live message" (pre-pairing history, excluded, no text).
_NAO_RESPONDER = ("skipped", "skipped_excluded")


class RegistroResposta:
    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._client = client_factory

    def desfecho_do_intake(self, connection_id: str, waha_message_id: str) -> Optional[str]:
        """The intake row's outcome, or None when the row does not exist."""
        rows = (
            self._client().table("intake_messages").select("outcome")
            .eq("connection_id", connection_id).eq("waha_message_id", waha_message_id).limit(1).execute().data
        )
        return rows[0]["outcome"] if rows else None

    @staticmethod
    def intake_responsavel(desfecho: Optional[str]) -> bool:
        return desfecho is not None and desfecho not in _NAO_RESPONDER

    def registrar(
        self, *, org_id: str, connection_id: str, waha_message_id: str, desfecho: str, motivo: Optional[str] = None,
        dados: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Append the attempt's event. False = this message was already attempted (nothing written)."""
        if desfecho not in DESFECHOS:
            raise ValueError(f"desfecho desconhecido: {desfecho!r}")
        rows = self._client().rpc("registrar_resposta", {
            "p_org_id": org_id, "p_connection_id": connection_id, "p_waha_message_id": waha_message_id,
            "p_event_type": desfecho, "p_motivo": motivo, "p_dados": dados or {},
        }).execute().data
        return bool(rows)
