"""E-mail normalisation + the suppression-list hash (sha256 of the normalised address)."""
from __future__ import annotations

import hashlib

from .types import InvalidEmailAddress


def normalize_email(email: str) -> str:
    """Trimmed + lower-cased. Raises ``InvalidEmailAddress`` unless it has one ``@`` with text on both sides."""
    value = (email or "").strip().lower()
    local, sep, domain = value.partition("@")
    if not sep or not local or not domain or "@" in domain or " " in value:
        raise InvalidEmailAddress("not an e-mail address")
    return value


def hash_email(email: str) -> str:
    """sha256 hex of the normalised address: the ONLY form the suppression list stores."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


__all__ = ["normalize_email", "hash_email"]
