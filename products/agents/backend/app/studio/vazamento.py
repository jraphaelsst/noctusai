"""Who may see a prompt, and the leak guard for the surfaces that are not a lead channel (Julia v2, owner round 2:
IP protection). A platform admin reads the compiled prompt anyway; everyone else -- an org member chatting in the
studio test chat, a ``studio:publish`` token reading eval results -- must never be handed it by the model."""
from __future__ import annotations

import logging
from typing import Any

from app.channels.conformidade import GuardaVazamento

logger = logging.getLogger(__name__)

__all__ = ["GuardaVazamento", "chamador_e_admin_da_plataforma"]


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
