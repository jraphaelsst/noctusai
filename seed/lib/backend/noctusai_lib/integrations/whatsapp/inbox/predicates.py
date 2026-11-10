"""Ready-made PRE-STORE predicates for the ingest seam (``ingest_waha_event(should_store=...)``).

:func:`inbound_one_to_one_only` is the shadow-line input contract (the Assistant, D46): keep ONLY what a person
sent to the linked number in a 1:1 chat. Everything else is skipped BEFORE it is stored, published or notified, so
it never reaches a table, a realtime channel or an LLM. Skips carry a stable reason string.
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Optional

from noctusai_lib.integrations.whatsapp.inbox.ingest import ChatIdentity, ShouldStore, is_non_conversation_jid
from noctusai_lib.integrations.whatsapp.inbox.types import InboxMessage

SKIP_FROM_ME = "from_me"
SKIP_API_SOURCED = "api_sourced"
SKIP_GROUP = "group"
SKIP_BROADCAST = "broadcast"
SKIP_EXCLUDED = "excluded"

#: ``(message, chat) -> True | False | "<reason>"`` -- the exclusion hook has the same verdict shape as the seam.
ExclusionHook = Callable[[InboxMessage, ChatIdentity], "bool | str"]


def _digits(value: Optional[str]) -> str:
    return re.sub(r"\D", "", (value or "").split("@", 1)[0])


def inbound_one_to_one_only(
    excluded: Iterable[str] = (), *, exclusion_hook: Optional[ExclusionHook] = None
) -> ShouldStore:
    """Inbound only (drops ``from_me`` and API-sourced), 1:1 only (drops groups, status, broadcast/newsletter), minus
    an exclusion list (phones / chat ids, compared by digits) and an optional ``exclusion_hook`` that returns
    ``True`` to keep, or ``False`` / a reason string to exclude."""
    blocked = {d for d in (_digits(x) for x in excluded) if d}

    def should_store(message: InboxMessage, chat: ChatIdentity) -> "bool | str":
        if message.from_me:
            return SKIP_FROM_ME
        if message.source == "api":
            return SKIP_API_SOURCED
        if chat.is_group or message.chat_id.endswith("@g.us"):
            return SKIP_GROUP
        if is_non_conversation_jid(message.chat_id):
            return SKIP_BROADCAST
        if blocked and (_digits(chat.phone) in blocked or _digits(chat.chat_id) in blocked):
            return SKIP_EXCLUDED
        if exclusion_hook is not None:
            verdict = exclusion_hook(message, chat)
            if verdict is not True:
                return verdict if isinstance(verdict, str) and verdict else SKIP_EXCLUDED
        return True

    return should_store
