"""Julia's CONTENT is edited by NoctusAI only, for now (owner 2026-11-04): the specifications, the knowledge sections, the privacy
notice text and the document-reading prompt. An org admin keeps reading them; WRITING them is a platform-admin act. ONE gate, so
every such route refuses with the same strict 403 `edicao_restrita_plataforma` and the same pt-BR sentence."""
from __future__ import annotations

import logging
from typing import Any, Callable

from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)

CODIGO = "edicao_restrita_plataforma"
MENSAGEM = "Este conteúdo da Julia é configurado pela equipe NoctusAI. Para alterar, fale com o suporte."


def exigir_admin_da_plataforma(e_admin_da_plataforma: Callable[[str], bool], auth: tuple, o_que: str) -> None:
    """403 `edicao_restrita_plataforma` unless the caller is a NoctusAI platform admin (the trusted `noctus_users` read behind
    `get_platform_admin_check`, never `user_metadata`)."""
    user_id = str(getattr(auth[0], "id", "") or "")
    if not user_id or not e_admin_da_plataforma(user_id):
        logger.warning("julia: %s write refused -- not a platform admin (%s)", o_que, CODIGO)
        raise AppException(CODIGO, MENSAGEM, status_code=403)


__all__ = ["CODIGO", "MENSAGEM", "exigir_admin_da_plataforma"]
