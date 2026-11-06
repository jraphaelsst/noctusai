"""Who may see a prompt, and the leak guard for the surfaces that are not a lead channel (Julia v2, owner round 2:
IP protection). A platform admin reads the compiled prompt anyway; everyone else -- an org member chatting in the
studio test chat, a ``studio:publish`` token reading eval results -- must never be handed it by the model."""
from __future__ import annotations

import logging
import re
from typing import Any

from app.channels.conformidade import SHINGLE_TOKENS, GuardaVazamento

logger = logging.getLogger(__name__)

__all__ = ["FiltroDeltas", "GuardaVazamento", "chamador_e_admin_da_plataforma"]


def chamador_e_admin_da_plataforma(ctx: Any) -> bool:
    """``public.noctus_users.role == 'admin'`` of the caller (never an org owner/admin: a different actor).
    A product token has no user. An unreadable role is NOT admin (fail closed: the guard stays on)."""
    if getattr(ctx, "user_id", None) is None:
        return False
    try:
        from app.dependencies import get_core_client
        from noctusai_lib.api.auth.platform import resolve_platform_admin_role

        return resolve_platform_admin_role(get_core_client(), ctx.user_id) == "admin"
    except Exception:  # noqa: BLE001 -- unknown means "not a platform admin"; the guard stays on, and it is logged
        logger.exception("agents.vazamento.papel_ilegivel")
        return False


_PALAVRA = re.compile(r"\S+")


class FiltroDeltas:
    """Streamed text may not outrun the leak guard (P1-C). The guard judges a whole reply, but ``message.delta``
    events reach the browser while it is still being written: a leaking reply would be on screen before the
    ``message.new`` check. So the filter accumulates each message's deltas, runs the guard on the accumulated
    text at every delta, and releases only what is older than ``retencao`` words. A 12-token run completes inside
    the last 12 tokens, so while the held-back tail is longer than that window (2x the shingle, because
    normalisation may split a word into several tokens) a run is detected before any of it is released. Once a
    message leaks, no further delta of it is released. The held-back tail is never flushed: ``message.new`` carries
    the full (guard-checked) text."""

    def __init__(self, guarda: GuardaVazamento, retencao: int = 2 * SHINGLE_TOKENS) -> None:
        self._guarda = guarda
        self._retencao = retencao
        self._acumulado: dict[str, str] = {}
        self._liberado: dict[str, int] = {}
        self._vazou: set[str] = set()

    def alimentar(self, message_temp_id: str, trecho: str) -> str | None:
        """The part of the stream that is safe to publish now, or ``None``."""
        if message_temp_id in self._vazou:
            return None
        texto = self._acumulado.get(message_temp_id, "") + trecho
        self._acumulado[message_temp_id] = texto
        if self._guarda.verificar(texto):
            self._vazou.add(message_temp_id)
            logger.warning("agents.turn.delta_vazamento_retido")
            return None
        palavras = list(_PALAVRA.finditer(texto))
        if len(palavras) <= self._retencao:
            return None
        corte = palavras[-self._retencao].start()
        ja = self._liberado.get(message_temp_id, 0)
        if corte <= ja:
            return None
        self._liberado[message_temp_id] = corte
        return texto[ja:corte]

    def mensagem_concluida(self) -> None:
        """A ``message.new`` landed: the streamed drafts are superseded by it."""
        self._acumulado.clear()
        self._liberado.clear()
        self._vazou.clear()
