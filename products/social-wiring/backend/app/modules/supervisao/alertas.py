"""Visible alerts for supervision hooks that must not break the flow they observe (julia-v2 CONTRACT §7 G4).

The supervision hooks (handoff sink, block-boundary hook, first-response stamps, the accept path) wrap their work
in try/except so a bookkeeping failure never undoes a send, a move or an accept. That isolation used to END in a
log line nobody reads: the dashboard then read as clean while data was missing. `alertar` is what those `except`
blocks now call, in ADDITION to their ERROR log:

  1. logs ERROR with the context ids;
  2. writes a `julia_eventos` row tipo `supervisao_falha`, payload `{codigo, dia, ids}` (ids only, no PII) -- it
     shows in Notificacoes, and the notification fan-out (`julia_notificacoes_service`, owners only, one per
     `(org, codigo, dia)`) turns it into an in-app notification;
  3. the scorecard engine counts that day's `supervisao_falha` rows into `falhas_registro` and flags every
     scorecard of the org for that day `dados_incompletos=true` (`metricas.marcar_falhas`), and the nightly report
     says so.

`alertar` NEVER raises (its own failure logs CRITICAL): the observed flow is never undone. Nothing here sends
anything to a lead.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from app.services import julia_eventos_service as eventos
from app.services import julia_notificacoes_service as notificacoes

logger = logging.getLogger(__name__)

TIPO = "supervisao_falha"


def alertar(client: Any, org_id: Any, codigo: str, ids: Optional[Mapping[str, Any]] = None) -> bool:
    """Record one supervision failure. `codigo` is a closed, snake_case token naming the hook (e.g.
    `handoff_novo_lead`, `aceite_sem_ator`); `ids` are opaque ids only. True = the alert event was stored."""
    try:
        limpos = {str(k): str(v) for k, v in (ids or {}).items() if v is not None}
        logger.error("supervisao: ALERT %s org=%s ids=%s -- the observed flow stands, the supervision data for the day "
                     "is incomplete", codigo, org_id, limpos)
        evento = eventos.emitir(client, org_id, TIPO, None, {"codigo": codigo, "dia": notificacoes.dia_sp(), "ids": limpos})
        if evento is None:
            logger.critical("supervisao: the %s alert event could NOT be written (org=%s codigo=%s)", TIPO, org_id, codigo)
            return False
        return True
    except Exception:
        logger.critical("supervisao: alertar itself failed (org=%s codigo=%s)", org_id, codigo, exc_info=True)
        return False


__all__ = ["TIPO", "alertar"]
