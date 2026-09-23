"""In-app notifications for the agency — rows in core's `public.notifications`.

The seed's standard `notificacoes` router (mounted in `app/main.py`) already
READS this table for the bell; this is the write half. Same row shape as
social-wiring's `modules/edicao_fotos/services/notifier.py::_write_in_app`.
"""
from __future__ import annotations

# NOC-REMEDIATE[in-app-notification-writer]: second product hand-writing
# public.notifications rows (social-wiring edicao_fotos is the first; N=2 ->
# triage); the third lifts a noctusai_lib.domain.notifications writer. — 2026-09-23

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

__all__ = ["notificar"]


def notificar(
    core_client: Any,
    *,
    org_id: str,
    user_ids: Iterable[Any],
    tipo: str,
    titulo: str,
    mensagem: str,
    metadata: dict | None = None,
) -> int:
    """Insert one notification per distinct recipient. Returns how many.

    Raises on a failed insert — the CALLER decides whether a notification
    failure may fail its operation. Zero recipients is logged at WARNING: an
    event nobody hears about is worth seeing in the logs.
    """
    destinatarios = sorted({str(u) for u in user_ids if u})
    if not destinatarios:
        logger.warning("notificação %s sem destinatários org=%s", tipo, org_id)
        return 0
    core_client.table("notifications").insert(
        [
            {
                "user_id": uid,
                "org_id": org_id,
                "type": tipo,
                "title": titulo,
                "message": mensagem,
                "metadata": metadata or {},
            }
            for uid in destinatarios
        ]
    ).execute()
    return len(destinatarios)
