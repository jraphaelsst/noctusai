"""THE one place that decides which characters are invisible/dangerous and how obfuscated text is flattened for the
security detectors (pure functions, stdlib only, no IO).

Three consumers, one definition:

* :func:`caractere_proibido` -- the universal "no control / zero-width / bidi / tag / private-use" rule of an org's
  spec VALUE (``studio/spec_formatos``). Rejects.
* :func:`limpar` -- the lead's inbound text at the channel schema boundary: the same invisible characters
  (Cf, the U+E0000-E007F tag block used for "ASCII smuggling", variation-selector tails, stray controls) are
  STRIPPED, so what is stored, shown to the model and scanned is what a human would read.
* :func:`esqueleto` -- a throw-away copy for the detectors ONLY (never stored, never shown): confusable
  letters mapped to Latin, accents/case folded, spaced-out letters/digits collapsed, "ponto com" style links and
  "arroba" e-mails rewritten, so ``i g n o r e``, ``reserva one ponto com ponto br`` and a Cyrillic ``о`` all meet
  the same patterns as the plain text.
* :func:`tem_caractere_oculto` -- the OUTPUT side: a reply carrying any of these characters is blocked.
"""
from __future__ import annotations

import re
import unicodedata

from noctusai_lib.primitives.accents import fold_accents

__all__ = ["caractere_proibido", "esqueleto", "limpar", "tem_caractere_oculto"]

#: Unicode categories a typed value may never carry (control, format = zero-width/bidi/tags, private-use,
#: surrogate, unassigned, line/paragraph separators).
CATEGORIAS_PROIBIDAS = frozenset({"Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"})

#: Mn/Me characters that smuggle data without being Cf: variation-selector supplement (U+E0100-E01EF) and the
#: plain variation selectors (U+FE00-FE0E; FE0F stays, it is the emoji presentation selector).
_SELETORES = re.compile("[\U000E0100-\U000E01EF︀-︎᠋-᠍͏]")
_ESPACOS_ESTRANHOS = re.compile("[   -   　]")


def caractere_proibido(ch: str, *, permite_quebra: bool = False) -> str | None:
    """The category when ``ch`` is a forbidden character (``\\n`` is tolerated when ``permite_quebra``)."""
    if ch == "\n" and permite_quebra:
        return None
    cat = unicodedata.category(ch)
    return cat if cat in CATEGORIAS_PROIBIDAS else None


def tem_caractere_oculto(texto: str) -> bool:
    """True when ``texto`` carries a format (Cf: zero-width, bidi, tag), private-use, selector or non-text control
    character -- nothing a human reads, so nothing a reply should contain."""
    for ch in texto:
        if ch in "\n\t\r":
            continue
        if unicodedata.category(ch) in CATEGORIAS_PROIBIDAS or _SELETORES.match(ch):
            return True
    return False


def limpar(texto: str) -> str:
    """``texto`` without invisible characters (Cf incl. the tag block, selectors, controls other than
    newline/tab); exotic spaces become a plain space. Visible characters are untouched."""
    if not texto:
        return texto
    base = _ESPACOS_ESTRANHOS.sub(" ", texto)
    return "".join(
        ch for ch in base
        if ch in "\n\t\r" or not (unicodedata.category(ch) in CATEGORIAS_PROIBIDAS or _SELETORES.match(ch))
    )


#: Lookalike letters (Cyrillic / Greek / a few Latin-extended) -> the Latin letter they imitate. Lowercase only:
#: the skeleton casefolds first.
_CONFUSAVEIS = str.maketrans({
    "а": "a", "в": "b", "г": "r", "е": "e", "ё": "e", "з": "3", "и": "u", "й": "u", "к": "k", "м": "m", "н": "h",
    "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "ь": "b", "і": "i", "ї": "i", "ј": "j", "ѕ": "s",
    "ԁ": "d", "ԛ": "q", "ԝ": "w", "ӏ": "l", "ѵ": "v", "ү": "y", "һ": "h", "ɡ": "g", "ɑ": "a", "ο": "o", "α": "a",
    "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "γ": "y", "ω": "w", "ı": "i",
    "ℓ": "l", "𝐚": "a", "ꭰ": "d", "ꮯ": "c",
})
_TLDS_SOLETRADOS = "com|br|net|org|io|me|ly|app|site|info|xyz|link|online|co|gov|edu|dev|store|shop|top|click|cc|tv"  # noc-allow: prompt-text-in-code -- TLD alternation of a detector regex, never read by a model
#: "ponto com", "dot br", "(.)": only before a TLD word, so "ponto de vista" is left alone.
_DOT = re.compile(
    rf"(?i)\s*[\(\[\{{<]?\s*\b(?:ponto|dot)\b\s*[\)\]\}}>]?\s*(?=(?:{_TLDS_SOLETRADOS})\b)|\s*[\(\[\{{]\s*\.\s*[\)\]\}}]\s*")
_ARROBA = re.compile(r"(?i)\s*[\(\[\{]?\s*\b(?:arroba|at)\b\s*[\)\]\}]?\s*(?=[a-z0-9-]+\s*(?:\.|ponto|dot))|\s*[\(\[]\s*@\s*[\)\]]\s*")
#: >= 4 single-character alphanumeric tokens separated by one space/dot/dash/underscore: "i g n o r e", "1 1 9 9 2".
_SOLETRADO = re.compile(r"(?<![^\W_])(?:[^\W_][ \t._\-]){3,}[^\W_](?![^\W_])")
_ESPACO_ANTES_DO_PONTO = re.compile(r"(?<=\w)[ \t]+\.[ \t]*(?=[a-z0-9])")


def esqueleto(texto: str) -> str:
    """The detector-only flattened copy of ``texto`` (see module doc). Idempotent; ``""`` for empty."""
    if not texto:
        return ""
    t = limpar(unicodedata.normalize("NFKC", texto)).casefold()
    t = t.translate(_CONFUSAVEIS)
    # strip accents AFTER the confusable map (NFD splits ç/ã/é; combining marks go, the base letter stays)
    t = fold_accents(t)
    t = _DOT.sub(".", t)
    t = _ARROBA.sub("@", t)
    t = _ESPACO_ANTES_DO_PONTO.sub(".", t)
    t = _SOLETRADO.sub(lambda m: re.sub(r"[ \t._\-]", "", m.group(0)), t)
    return t
