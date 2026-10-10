"""Chat's side of the shared transcription layer: the ``chat_ditado`` context
(``specs/geracao-contract.md`` section 7.2 / 10 BE-6).

Mic dictation in the chat composer. ``contexto_ref`` is the **marca id** the conversation belongs to:

- ``validar``: the marca must belong to the caller's org (a foreign / unknown marca is a 404, same as
  every other id here), so a recording can never be attached to someone else's tenant.
- ``aplicar``: deliberately a no-op. The transcript is NOT written anywhere: the composer polls the
  shared ``transcricoes`` row and fills its textarea with ``texto`` -- it never auto-sends and no chat
  message is created by a voice upload. The layer still guarantees the (empty) hook runs exactly once.
"""
from __future__ import annotations

import logging
from typing import Any

from app.modules.transcricoes import hooks
from app.modules.transcricoes.errors import TranscricaoErro

logger = logging.getLogger(__name__)

CONTEXTO_TIPO = "chat_ditado"


def validar(db: Any, org_id: str, user_id: str, ref: str) -> None:
    ref = (ref or "").strip()
    rows = (
        db.table("marcas").select("id").eq("id", ref).eq("org_id", org_id).execute().data
    ) if ref else []
    if not rows:
        raise TranscricaoErro("nao_encontrada", status=404, mensagem="Marca não encontrada.")


def aplicar(db: Any, row: dict[str, Any]) -> None:
    logger.debug("chat ditado: transcrição %s concluída (o compositor lê o texto da própria transcrição)", row.get("id"))


def register_contexto() -> None:
    hooks.register_contexto(CONTEXTO_TIPO, validar=validar, aplicar=aplicar)


__all__ = ["CONTEXTO_TIPO", "aplicar", "register_contexto", "validar"]
