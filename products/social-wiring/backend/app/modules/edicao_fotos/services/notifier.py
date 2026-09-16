"""Batch-ready fan-out — the engine's `BatchReadyNotifier` port.

R1 ships the IN-APP channel only: one `public.notifications` row for the
batch's creator, which the seed `/api/notificacoes` proxy already serves.

Both switches the owner defined are honoured here, before anything is
written: the platform-wide `notificacoes_globais_ativas` and the org's
`notificacoes_ativas`. A switched-off notice is logged, not dropped
silently.

NOC-REMEDIATE[edicao-fotos-notify-channels]: email + WhatsApp channels and
the per-user agency-admin opt-in (plan §1 "Notifications") are not wired
yet — the creator's in-app row is the only delivery. — 2026-09-16
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from noctusai_lib.domain.photo_editing import BatchReadyNotice, PhotoEditingRepository

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "system"
FEATURE = "edicao_fotos.lote_pronto"


def batch_ready_message(notice: BatchReadyNotice) -> tuple[str, str]:
    """pt-BR title + body for a ready batch."""
    title = f"Lote pronto para revisão: {notice.nome}"
    body = f"{notice.aguardando_decisao} de {notice.total_fotos} foto(s) aguardam sua decisão."
    if notice.falhou:
        body += f" {notice.falhou} foto(s) falharam e podem ser retentadas."
    return title, body


class InAppBatchReadyNotifier:
    """Writes the creator's in-app notification through a `public`-scoped
    service-role client (the table lives in Core's schema)."""

    def __init__(
        self,
        *,
        core_client: Callable[[], Any],
        repo: PhotoEditingRepository,
    ) -> None:
        self._core_client = core_client
        self._repo = repo

    async def batch_ready(self, notice: BatchReadyNotice) -> None:
        platform = await self._repo.get_platform_settings()
        if not platform.notificacoes_globais_ativas:
            logger.info(
                "edicao_fotos: lote %s pronto — notificação desligada na plataforma",
                notice.lote_id,
            )
            return
        org = await self._repo.get_org_settings(notice.org_id)
        if org is not None and not org.notificacoes_ativas:
            logger.info(
                "edicao_fotos: lote %s pronto — notificação desligada pela organização %s",
                notice.lote_id,
                notice.org_id,
            )
            return
        title, body = batch_ready_message(notice)
        row = {
            "user_id": notice.criado_por,
            "org_id": notice.org_id,
            "type": NOTIFICATION_TYPE,
            "title": title,
            "message": body,
            "metadata": {
                "feature_key": FEATURE,
                "lote_id": notice.lote_id,
                "link": f"/edicao-fotos/lotes/{notice.lote_id}/revisao",
            },
        }
        client = self._core_client()
        # Raises on failure: the engine's `fotos.lote_pronto` handler is
        # at-least-once and retries a notice that did not land.
        await asyncio.to_thread(lambda: client.table("notifications").insert(row).execute())


__all__ = ["InAppBatchReadyNotifier", "batch_ready_message"]
