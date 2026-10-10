"""Accent folding — single source of truth.

`fold_accents(text)`: NFKD-decompose, drop every combining mark. Case and
whitespace are untouched — callers compose `.upper()` / `.casefold()` /
whitespace collapsing on top, because those choices differ per use and are
not the fold's business. Replaces ~25 private copies (`_sem_acento`,
`_fold_accents`, `_deaccent_upper`, the documents parsers' `normalize`, ...).

`fold_accents_ascii(text)`: the same fold, then every remaining non-ASCII
codepoint dropped — the shape filename / slug builders need. Byte-identical
to the `unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()`
idiom it replaces (combining marks are non-ASCII, so dropping them first
changes nothing).

Deliberately NFKD, not NFD: compatibility characters fold too (`º` -> `o`,
`ª` -> `a`, `ﬁ` -> `fi`, full-width digits -> digits). The few call sites
that used NFD + `category == "Mn"` produce DIFFERENT output on exactly those
characters and were not migrated blind — see each site's parity test.
"""
from __future__ import annotations

import unicodedata


def fold_accents(text: str | None) -> str:
    """`text` with diacritics removed (NFKD, combining marks dropped). `None` -> `""`."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def fold_accents_ascii(text: str | None) -> str:
    """`fold_accents`, then any codepoint still outside ASCII dropped. `None` -> `""`."""
    return fold_accents(text).encode("ascii", "ignore").decode("ascii")


__all__ = ["fold_accents", "fold_accents_ascii"]
