"""Biblioteca's side of the shared transcription layer (contract geracao 3.4, 9.3).

Registers the ``biblioteca_viral`` context (``contexto_ref = viral_id``) in the completion-hook
registry of :mod:`app.modules.transcricoes.hooks`:

* ``validar`` -- since migration 351 the library is platform-wide, so "the viral belongs to the caller's org" no longer
  protects anything: the user-facing ``POST /api/transcricoes`` accepts any ``contexto_tipo`` and would let ANY org attach
  a transcript to a library video (and ``aplicar`` would overwrite the video's text). The context is therefore
  SYSTEM-ONLY: the caller must be the platform ingestion org AND its system user (exactly what
  ``submit_sistema`` passes); anyone else gets the same 404 an unknown id gets.
* ``aplicar`` -- writes the finished transcript onto the viral (``transcricao_texto`` clipped to the
  column's 50 000-char CHECK, ``transcricao_status='concluida'``, the probed duration) and marks it
  ready for classification. The transcription layer runs it exactly once per transcription.

The ``biblioteca.classificar`` job is enqueued by the scheduler's pending sweep
(:mod:`app.modules.media_creation.biblioteca_scheduler`, every 10 minutes): the hook is synchronous and
the queue is async, so the sweep is the one delivery path instead of a fire-and-forget task that a
restart would lose. A viral whose transcription ends WITHOUT a hook call (failed / cancelled) is
settled by the same sweep.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.config import settings
from app.modules.media_creation.services import biblioteca_fonte
from app.modules.media_creation.services.biblioteca_service import CONTEXTO_TIPO, VIRAIS
from app.modules.transcricoes import hooks
from app.modules.transcricoes.errors import TranscricaoErro

logger = logging.getLogger(__name__)

MAX_TRANSCRICAO_CHARS = 50_000


def _ingestao_padrao() -> tuple[Optional[str], Optional[str]]:
    """``(org_id, user_id)`` of the platform ingestion lane: platform_settings first, then settings."""
    return (
        biblioteca_fonte.read_ingestao_org(default=settings.corestudio_biblioteca_org_id),
        biblioteca_fonte.read_ingestao_user(default=settings.corestudio_biblioteca_user_id),
    )


#: The ingestion-lane reader the hook checks against. A DI seam: ``register_contexto(ingestao=...)`` replaces it (tests).
_ingestao: Callable[[], tuple[Optional[str], Optional[str]]] = _ingestao_padrao


def validar(db: Any, org_id: str, user_id: str, ref: str) -> None:
    ingestao_org, ingestao_user = _ingestao()
    # Fail closed: an unconfigured lane accepts nobody (never "any org").
    if not ingestao_org or not ingestao_user or str(org_id) != ingestao_org or str(user_id) != ingestao_user:
        raise TranscricaoErro("nao_encontrada", status=404, mensagem="Vídeo não encontrado.")
    rows = db.table(VIRAIS).select("id").eq("id", str(ref)).execute().data
    if not rows:
        raise TranscricaoErro("nao_encontrada", status=404, mensagem="Vídeo não encontrado.")


def aplicar(db: Any, row: dict[str, Any]) -> None:
    viral_id = str(row["contexto_ref"])
    texto = (row.get("texto") or "").strip()
    found = db.table(VIRAIS).select("id").eq("id", viral_id).execute().data
    if not found:
        logger.warning("biblioteca voz: viral %s não existe mais; transcrição %s não aplicada", viral_id, row["id"])
        return
    if len(texto) > MAX_TRANSCRICAO_CHARS:
        logger.warning("biblioteca voz: transcrição %s cortada em %s caracteres", row["id"], MAX_TRANSCRICAO_CHARS)
        texto = texto[:MAX_TRANSCRICAO_CHARS]
    patch: dict[str, Any] = {
        "transcricao_texto": texto or None,
        "transcricao_status": "concluida",
        "transcricao_id": str(row["id"]),
    }
    if row.get("duracao_s") is not None:
        patch["duracao_s"] = float(row["duracao_s"])
    db.table(VIRAIS).update(patch).eq("id", viral_id).execute()


def register_contexto(*, ingestao: Optional[Callable[[], tuple[Optional[str], Optional[str]]]] = None) -> None:
    """Idempotent. ``ingestao`` replaces the ``(org_id, user_id)`` reader of the ingestion lane (default: settings)."""
    global _ingestao
    _ingestao = ingestao or _ingestao_padrao
    hooks.register_contexto(CONTEXTO_TIPO, validar=validar, aplicar=aplicar)


__all__ = ["CONTEXTO_TIPO", "aplicar", "register_contexto", "validar"]
