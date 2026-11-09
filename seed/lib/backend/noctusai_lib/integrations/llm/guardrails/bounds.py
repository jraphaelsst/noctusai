"""Structural bounds of a model answer (pure): word band, enumerated values, retrieved-source grounding.

The deterministic leg of an output post-filter whose lexicons are DATA (see agents ``public_ask/postfilter``).
"""
from __future__ import annotations

import re
from collections.abc import Collection, Sequence

__all__ = ["count_words", "outside_enum", "outside_word_band", "unretrieved_sources"]

_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


def count_words(text: str) -> int:
    return len(_WORD.findall(text))


def outside_word_band(text: str, minimum: int, maximum: int) -> bool:
    return not minimum <= count_words(text) <= maximum


def outside_enum(values: Sequence[str], allowed: Collection[str]) -> bool:
    """True when any of ``values`` is not in ``allowed``."""
    return any(v not in allowed for v in values)


def unretrieved_sources(cited: Sequence[str], retrieved: Collection[str]) -> bool:
    """True when the answer cites a source id that retrieval never returned (an invented source)."""
    got = set(retrieved)
    return any(c not in got for c in cited)
