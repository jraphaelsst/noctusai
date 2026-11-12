"""skill-scout notices — the owner hears about a recommended skill on WhatsApp ONLY (never e-mail, never the bell).

Sent through the seed owner line (`notify_owner`): the switch on the Notificações page, the single owner number in core
and the send ledger all apply. The kind is declared in `app/notification_kinds.py` (`canais=("whatsapp",)`).
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.domain.notification_catalog import OwnerDispatch, notify_owner

from app.notification_kinds import KIND_SKILL_SCOUT_NOVO_SKILL, PRODUCT

_NOME_MAX = 120
_RESUMO_MAX = 400
_URL_MAX = 300


def _clip(value: Optional[str], limit: int) -> str:
    return " ".join((value or "").split())[:limit]


def montar_texto(*, nome: str, resumo: str, fonte_url: Optional[str]) -> str:
    linhas = ["🔎 skill-scout — skill nova encontrada", f"Skill: {_clip(nome, _NOME_MAX)}", f"Resumo: {_clip(resumo, _RESUMO_MAX)}"]
    if fonte_url:
        linhas.append(f"Fonte: {_clip(fonte_url, _URL_MAX)}")
    return "\n".join(linhas)


def avisar_novo_skill(
    *, nome: str, resumo: str, fonte_url: Optional[str], gate: Any = None, recipients: Any = None, transport: Any = None,
) -> OwnerDispatch:
    """One WhatsApp notice for one recommended skill. The seams (`gate`/`recipients`/`transport`) are the seed's own."""
    return notify_owner(
        PRODUCT, KIND_SKILL_SCOUT_NOVO_SKILL, montar_texto(nome=nome, resumo=resumo, fonte_url=fonte_url),
        gate=gate, recipients=recipients, transport=transport,
    )


__all__ = ["avisar_novo_skill", "montar_texto"]
