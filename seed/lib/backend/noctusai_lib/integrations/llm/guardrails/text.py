"""Text helpers shared by the guardrail detectors (pure, stdlib + accent fold)."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from noctusai_lib.primitives.accents import fold_accents

from .obfuscation import esqueleto

__all__ = ["normalizar", "skeleton_targets", "strip_trailing_decoration", "termina_com_pergunta"]

_NAO_ALFANUM = re.compile(r"[^0-9a-z]+")


def normalizar(texto: str) -> str:
    return _NAO_ALFANUM.sub(" ", fold_accents(texto).casefold()).strip()


def strip_trailing_decoration(texto: str) -> str:
    """The text without trailing whitespace, emoji, symbols and closing quotes/brackets."""
    t = texto.rstrip()
    while t:
        c = t[-1]
        cat = unicodedata.category(c)
        if c.isspace() or cat.startswith(("S", "M", "C")) or c in "\"')]}»”’*_~":
            t = t[:-1]
            continue
        break
    return t


def termina_com_pergunta(texto: str) -> bool:
    return strip_trailing_decoration(texto).endswith("?")


def skeleton_targets(textos: Iterable[str]) -> list[str]:
    """Each text as written (NFKC) AND its de-obfuscated skeleton (zero-width, confusables, spaced letters, accents):
    a pattern meets both, so an obfuscated phrasing is no way around it."""
    out: list[str] = []
    for t in textos:
        plano = unicodedata.normalize("NFKC", t)
        out.append(plano)
        sk = esqueleto(t)
        if sk != plano.casefold():
            out.append(sk)
    return out
