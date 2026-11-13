"""Phone / chat-id helpers of the live reply. The number lives ONLY in flight (never in the database)."""
from __future__ import annotations

import re
from typing import Iterable, Optional

from noctusai_lib.primitives.phone import normalize_phone

#: Chat ids the Assistant never answers: groups, status, broadcast lists, channels.
_NAO_INDIVIDUAL = ("@g.us", "@broadcast", "@newsletter")


def eh_conversa_individual(chat_id: str) -> bool:
    """True only for a 1:1 chat (`...@c.us`, or an opaque `...@lid`). Anything else is never answered."""
    c = (chat_id or "").strip().lower()
    if not c or c.startswith("status@") or any(c.endswith(s) for s in _NAO_INDIVIDUAL):
        return False
    return c.endswith("@c.us") or c.endswith("@s.whatsapp.net") or c.endswith("@lid")


def digitos(valor: str) -> str:
    return re.sub(r"\D", "", (valor or "").split("@", 1)[0])


def canonico(valor: str) -> str:
    """Digits of a number, with the Brazilian mobile 9th digit normalised (55 + DDD + 9 + 8 digits), so
    `5511988887777` and `551188887777` are the same line."""
    d = digitos(valor)
    if d.startswith("55") and len(d) == 12 and d[4] in "6789":
        return d[:4] + "9" + d[4:]
    return d


def numero_do_chat(chat_id: str) -> Optional[str]:
    """E.164 digits (no `+`) of a `...@c.us` chat id; None for an opaque `@lid` (the number is unknown)."""
    c = (chat_id or "").strip().lower()
    if c.endswith("@lid"):
        return None
    d = digitos(c)
    return d or None


def numero_permitido(numero: Optional[str], lista: Iterable[str]) -> bool:
    """Allow-list decision. EMPTY list = every number is allowed (owner rule). A non-empty list allows only a number it
    names; an unknown number (opaque @lid) is never in a non-empty list."""
    permitidos = {canonico(x) for x in lista if canonico(x)}
    if not permitidos:
        return True
    return numero is not None and canonico(numero) in permitidos


def numeros_do_dono(bruto: str) -> frozenset[str]:
    """`ASSISTANT_OWNER_NUMBERS` (comma-separated, any spelling) -> canonical digit set via the platform phone normalizer.
    Unset/empty -> empty set (nobody is the owner). An entry that is not a phone is dropped, never guessed."""
    out = set()
    for item in (bruto or "").split(","):
        e164 = normalize_phone(item.strip()) if item.strip() else None
        if e164:
            out.add(canonico(e164))
    return frozenset(out)


def eh_dono(numero: Optional[str], donos: frozenset[str]) -> bool:
    """True only when the sender's number is known (not an opaque @lid) and is one of the owner's numbers."""
    return bool(donos) and numero is not None and canonico(numero) in donos
