"""The Esteira's live stream (criacao-pipeline-contract 3): the shared realtime bus + the seed pipeline stream router.

One process-wide bus (``noctusai_lib.realtime``, Redis Streams, Fake in-process when no ``redis_url`` -- said loudly once).
The browser reads ``GET /api/media-creation/esteira/stream`` (SSE, tier org, org from the authenticated context only);
the writers publish ``pipeline.card_moved`` (seed ``move_card(publish=...)``) and ``pipeline.card_state`` (the progress bar).
"""
from __future__ import annotations

from noctusai_lib.realtime import RealtimeBus, get_shared_realtime_bus

from app.config import settings


def esteira_bus() -> RealtimeBus:
    return get_shared_realtime_bus(settings.redis_url, label="Esteira pipeline stream")


__all__ = ["esteira_bus"]
