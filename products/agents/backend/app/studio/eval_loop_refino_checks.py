"""The content checks of the eval-loop refine step (red-team hardening, owner 2026-11-19). Pure, no IO.

Three families, all over text the MODEL wrote (and the model read hostile transcripts to write it):

* **addresses and contacts** (:func:`contem_endereco`, :func:`contem_arroba`): the text is NORMALISED first -- NFKC (fullwidth, ligatures),
  Unicode ``Cf`` format characters stripped (zero-width), a confusable skeleton (Cyrillic / Greek lookalikes to Latin), accents folded,
  every way of spelling a dot made a dot (``[.]``, ``(ponto)``, ``promo . com``, ``promo ponto com``) -- and then a GENERIC
  ``label.alpha{2,}`` domain pattern is applied (never a TLD list: ``oferta.ai`` is a domain), plus IPv4, ``@handle`` and "link na bio";
* **weakening** (:func:`enfraquece_protecao`): a sentence of the OLD text that holds a protective word and is gone (removed OR modified)
  in the new text;
* **forbidden instructions** (:func:`instrucao_proibida`): an ADDED sentence that makes an exception, a trigger or an obey-the-lead rule,
  or talks about payment.

A false positive here costs one recorded refusal; a false negative costs a lead-facing prompt. The checks lean to refuse.
"""
from __future__ import annotations

import re
import unicodedata

from noctusai_lib.primitives.accents import fold_accents_ascii

__all__ = [
    "normalizar_seguro", "contem_endereco", "contem_arroba", "id_frase", "frases", "frases_novas", "enfraquece_protecao",
    "instrucao_proibida",
]

# Cyrillic / Greek letters that render like a Latin one (a confusable skeleton, not the full Unicode table: the letters an attacker needs
# to spell an ASCII domain or handle), plus the dot look-alikes. Applied after case folding.
_CONFUSAVEIS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d", "ɡ": "g",
    "ӏ": "l", "к": "k", "м": "m", "н": "h", "т": "t", "в": "b", "ԛ": "q", "ԝ": "w", "ο": "o", "α": "a", "ν": "v", "ρ": "p", "ι": "i",
    "τ": "t", "κ": "k", "χ": "x", "ε": "e", "υ": "u", "η": "n", "μ": "u", "β": "b", "γ": "y", "ω": "w", "ѵ": "v", "ɑ": "a", "ᴠ": "v",
    "ᴡ": "w", "ᴢ": "z", "ꜱ": "s", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m",
    "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ʀ": "r", "ᴛ": "t", "ᴜ": "u", "ʏ": "y",
    "·": ".", "•": ".", "∙": ".", "⋅": ".", "。": ".", "｡": ".", "․": ".", "‧": ".", "﹒": ".",
})

_PONTO_COLCHETE = re.compile(r"[\[\(\{<]\s*(?:\.|dot|ponto)\s*[\]\)\}>]")
_PONTO_ESPACADO = re.compile(r"(?<=\w)\s+\.\s+(?=\w)|(?<=\w)\s+\.(?=[a-z]{2})")
_TLDS_FALADOS = r"com|net|org|br|io|ai|app|dev|co|me|xyz|link|site|online|shop|store|info|biz|tv|ly|top|club"  # noc-allow: prompt-text-in-code — a regex alternation, never read by a model
_PONTO_FALADO = re.compile(rf"(?<=\w)\s+(?:ponto|dot)\s+(?=(?:{_TLDS_FALADOS})\b)")
_ARROBA_FALADA = re.compile(r"[\[\(\{<]\s*(?:arroba|at)\s*[\]\)\}>]")

_URL = re.compile(r"\bh(?:tt|xx)ps?\s*:\s*/\s*/|\bftp\s*:\s*/\s*/|\bwww\s*\.")
_DOMINIO = re.compile(r"(?<![\w.@-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b(?!@)")
_IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
_LINK_NA_BIO = re.compile(
    r"\blink\s+(?:na|da|no|do|em|nos?)\s+(?:minha\s+|nossa\s+|nosso\s+|meu\s+)?bio\b|\blinktr\b|\blinktree\b|\bbio\.link\b")
_HANDLE = re.compile(r"(?<![\w@.])@[a-z0-9_][a-z0-9_.]{2,}")


def normalizar_seguro(texto: str) -> str:
    """NFKC, no Unicode ``Cf`` (zero-width, bidi, soft hyphen), confusables to Latin, accents folded, lower-case, every dot spelled as
    ``.``. The form the address / contact checks read -- never stored."""
    t = unicodedata.normalize("NFKC", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Cf")
    t = t.casefold().translate(_CONFUSAVEIS)
    t = fold_accents_ascii(t)
    t = _PONTO_COLCHETE.sub(".", t)
    t = _ARROBA_FALADA.sub("@", t)
    t = _PONTO_ESPACADO.sub(".", t)
    t = _PONTO_FALADO.sub(".", t)
    return t


def contem_endereco(texto: str) -> bool:
    """A URL, a domain (generic ``label.alpha{2,}``), an IPv4 or a "link na bio" once the text is normalised."""
    n = normalizar_seguro(texto)
    return bool(_URL.search(n) or _DOMINIO.search(n) or _IPV4.search(n) or _LINK_NA_BIO.search(n))


def contem_arroba(texto: str) -> bool:
    """An ``@handle`` (social handle / mention) once the text is normalised. (An e-mail is the PII guard's.)"""
    return _HANDLE.search(normalizar_seguro(texto)) is not None


# ── sentences ────────────────────────────────────────────────────────────────

_SENTENCAS = re.compile(r"(?<=[.!?])\s+|\n+")


def frases(texto: str) -> list[str]:
    return [x for x in _SENTENCAS.split(texto) if x.strip()]


def id_frase(frase: str) -> str:
    """The identity of a sentence: accent-folded, case-folded, whitespace-collapsed, without list bullets and end punctuation."""
    s = re.sub(r"\s+", " ", fold_accents_ascii(frase)).strip().casefold()
    return s.lstrip("-*•> ").rstrip(" .!?;:")


def frases_novas(antes: str, depois: str) -> list[str]:
    """The sentences of ``depois`` that ``antes`` did not have (a modified sentence counts as new)."""
    tinha = {id_frase(x) for x in frases(antes)}
    return [x for x in frases(depois) if id_frase(x) not in tinha]


# ── weakening of protective text ─────────────────────────────────────────────

_PROTETORAS = re.compile(
    r"\b(?:sair|saia|parar|pare|descadastr\w*|human\w*|equipe|transfer\w*|privacidade|dados|lgpd|ia|robo|nunca|jamais|nao|proibid\w*"
    r"|obrigatori\w*|sempre|deve\w*)\b")


def enfraquece_protecao(antes: str, depois: str) -> bool:
    """True when a sentence of ``antes`` that holds a protective word is missing from ``depois`` (removed or reworded): the edit touched
    text that tells the agent what it must never / always do."""
    ficou = {id_frase(x) for x in frases(depois)}
    for f in frases(antes):
        i = id_frase(f)
        if i and i not in ficou and _PROTETORAS.search(i):
            return True
    return False


# ── forbidden instructions in ADDED text ─────────────────────────────────────

_PROIBIDAS = re.compile(
    r"\bexceto\b|\ba menos que\b|\bsalvo\b|\bse o lead (?:pedir|disser|escrever|falar|mandar|insistir|solicitar|perguntar)\b"
    r"|\bignor\w*|\binstrucoes? d[oa]s? lead\b|\bpalavra[- ]?chave\b|\bcodigo\b|\bmodo\b"
    r"|\bpix\b|\bchave\b|\bconta\b|\bboleto\b|\bpagament\w*")


def instrucao_proibida(adicionado: str) -> bool:
    """True when ADDED text carries an exception / trigger / obey-the-lead pattern or a payment pattern."""
    return _PROIBIDAS.search(fold_accents_ascii(adicionado).casefold()) is not None
