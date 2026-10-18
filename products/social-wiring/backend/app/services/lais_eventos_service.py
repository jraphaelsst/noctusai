"""Lais event bus (`social_wiring.lais_eventos`, contract 2.2).

`emitir` appends one row; wave 6 renders the table as notifications (recipient
resolution + prefs live there, on top of this). Emitting NEVER raises into the caller:
an event is observability of a turn, so a failed insert is logged at ERROR and
reported as `None` -- it must not drop the reply to the lead.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

TABLE = "lais_eventos"

#: The closed vocabulary (contract 8: 10 notification types + handoff of page 0), plus the
#: engine's own diagnostics. A later wave appends here -- the DB CHECK only guards the
#: token shape, so adding a type needs no migration.
TIPOS_NOTIFICAVEIS: frozenset[str] = frozenset({
    "pre_agendamento_visita", "cobranca_atendimento", "relatorio", "remarketing", "captacao",
    "atualizacao_base_imoveis", "novo_lead", "novo_atendimento", "nova_mensagem",
    "avaliacao_google", "handoff",
})
TIPOS_DIAGNOSTICO: frozenset[str] = frozenset({"acao_sem_handler", "acao_falhou", "resumo_falhou"})
#: Wave 4 (reengajamento): `reengajamento` is the timeline system event ("Lead não respondeu mais...");
#: `regua_sem_transporte` records a template attempt skipped until wave 12's Cloud transport exists.
TIPOS_REENGAJAMENTO: frozenset[str] = frozenset({"reengajamento", "regua_sem_transporte"})
#: Wave 13 (credito): `credito_analisado` (payload `{analise_id, status}` only -- never financial data).
TIPOS_CREDITO: frozenset[str] = frozenset({"credito_analisado"})
#: Follow-up: `imovel_consultado` = Julia looked a listing up through a read tool (payload `{ferramenta, codigos,
#: interacao_id}` -- codes only, no personal data). Not notifiable; Relatorios folds it into "top imoveis".
TIPOS_CONSULTA: frozenset[str] = frozenset({"imovel_consultado"})
#: Meta lead-form intake into Lais: payload `{status, motivo?, origem}` -- the outcome of the first-contact attempt
#: (`enviado` | `transporte_indisponivel` | `modelo_nao_aprovado` | `ja_em_atendimento` | `sem_telefone` | `erro`).
TIPOS_PRIMEIRO_CONTATO: frozenset[str] = frozenset({"primeiro_contato_meta"})
#: The outbound gate (`lais_envio_gate`): `envio_bloqueado` = an automatic Julia send refused by a gate, payload
#: `{fluxo, motivo, connection_id}` -- the refuse-not-null record (never a silent skip). Not notifiable.
TIPOS_GATE: frozenset[str] = frozenset({"envio_bloqueado"})
TIPOS: frozenset[str] = (
    TIPOS_NOTIFICAVEIS | TIPOS_DIAGNOSTICO | TIPOS_REENGAJAMENTO | TIPOS_CREDITO | TIPOS_CONSULTA
    | TIPOS_PRIMEIRO_CONTATO | TIPOS_GATE
)

#: Post-insert sinks `(client, row) -> None` (wave 6 registers the notification fan-out). A seam, so no
#: emitting caller is edited; a failing sink is logged and never reaches the caller.
_SINKS: list[Callable[[Any, dict[str, Any]], None]] = []


def registrar_sink(fn: Callable[[Any, dict[str, Any]], None]) -> None:
    """Idempotent: registering the same callable twice keeps one."""
    if fn not in _SINKS:
        _SINKS.append(fn)


_TIPO_RE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")  # mirrors `lais_eventos_tipo_valido`


def emitir(
    client: Any,
    org_id: UUID | str,
    tipo: str,
    contato_id: UUID | str | None = None,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Insert one event; returns the stored row, or None when it could not be written.

    `client` is the schema-scoped service-role client (`get_scoped_admin_client("social_wiring")`).
    An unknown `tipo` is a programming error (logged, nothing written) -- the type list is the
    contract, a typo must not mint a new notification category."""
    if tipo not in TIPOS or not _TIPO_RE.match(tipo):
        logger.error("lais: refused to emit unknown event type %r (org=%s)", tipo, org_id)
        return None
    row = {
        "org_id": str(org_id),
        "tipo": tipo,
        "contato_id": str(contato_id) if contato_id else None,
        "payload": payload or {},
        "lido_por": [],
    }
    try:
        res = client.table(TABLE).insert(row).execute()
    except Exception:
        logger.exception("lais: could not write event %s (org=%s contato=%s)", tipo, org_id, contato_id)
        return None
    data = res.data or []
    stored = data[0] if data else row
    for sink in tuple(_SINKS):
        try:
            sink(client, stored)
        except Exception:
            logger.exception("lais: event sink %s failed for %s (org=%s)", getattr(sink, "__name__", sink), tipo, org_id)
    return stored


__all__ = ["TIPOS", "TIPOS_CONSULTA", "TIPOS_DIAGNOSTICO", "TIPOS_NOTIFICAVEIS", "emitir", "registrar_sink"]
