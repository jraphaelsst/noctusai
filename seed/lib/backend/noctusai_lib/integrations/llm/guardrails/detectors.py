"""Reply detectors of the LLM guardrails (moved verbatim from agents ``channels/conformidade``).

Each detector is a pure function ``(reply, ...) -> detail | None`` (``None`` = clean). A detail carries CODES and COUNTS
only -- never the reply, the lead's words or a prompt fragment. What is DATA (allowed hosts/contacts, own company ids,
forbidden patterns, size limits) is passed in by the product; nothing here knows a tenant.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from noctusai_lib.primitives.identificador import cnpj_dv_valido, cpf_dv_valido

from .obfuscation import esqueleto, tem_caractere_oculto
from .text import skeleton_targets

logger = logging.getLogger(__name__)

__all__ = [
    "CNPJ_PATTERN", "CPF_PATTERN", "LINK_PATTERN", "PIX_PATTERN",
    "contar_padroes", "contato_nao_permitido", "formato_suspeito", "link_nao_permitido", "lista_de_spec",
    "padroes_proibidos", "pii_na_resposta",
]

_TRAILING_URL = ".,;:!?)]}\"'"

_TLDS = "|".join(("com", "br", "net", "org", "io", "me", "ly", "app", "site", "info", "xyz", "link", "online",
                      "co", "gov", "edu", "dev", "store", "shop", "top", "click", "cc", "tv"))
#: A URL, a ``www.`` host, a shortener / messenger host, or a bare domain on a common TLD. A bare domain glued to
#: an ``@`` is an e-mail address (``contato_nao_permitido``'s), not a link.
_LINK = re.compile(
    r"(?<![@\w.-])(?:https?://[^\s<>\"')\]]+|(?:www\.)[^\s<>\"')\]]+|(?:wa\.me|t\.me|bit\.ly|tinyurl\.com)/?[^\s<>\"')\]]*"
    r"|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:" + _TLDS + r")(?![a-z0-9-])(?:/[^\s<>\"')\]]*)?)",
    re.IGNORECASE,
)
_PREFIXO_URL = re.compile(r"^(?:https?://)?(?:www\.)?", re.IGNORECASE)


def _host(url: str) -> str:
    sem = _PREFIXO_URL.sub("", url.strip().rstrip(_TRAILING_URL))
    return re.split(r"[/?#:]", sem, maxsplit=1)[0].casefold()


def lista_de_spec(valor: str | None) -> list[str]:
    """An org-spec value holding a list (one item per line, ``,`` or ``;``) as clean items."""
    return [p.strip() for p in re.split(r"[\n,;]+", valor or "") if p.strip()]


def link_nao_permitido(
    resposta: str, links_permitidos: Iterable[str], dominios_permitidos: Iterable[str],
) -> dict[str, Any] | None:
    """Every URL **or bare domain** of the reply whose host is neither the host of a link a tool returned /
    Julia already sent, nor the agency's own domain (``dominios_permitidos``, an org spec; a subdomain of an
    own domain is own). ``detalhe`` holds the count of foreign hosts."""
    ok_hosts = {_host(l) for l in links_permitidos} | {_host(d) for d in dominios_permitidos}
    ok_hosts.discard("")
    fora: set[str] = set()
    for m in _LINK.finditer(unicodedata.normalize("NFKC", resposta)):
        h = _host(m.group(0))
        if not h or "." not in h:
            continue
        if any(h == ok or h.endswith("." + ok) for ok in ok_hosts):
            continue
        fora.add(h)
    return {"links": len(fora)} if fora else None


_EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", re.IGNORECASE)
# Word-bounded on both sides: a digit run INSIDE an alphanumeric token (a hex canary, a hash, a listing code
# like ONE12345678901) is not a phone number.
_TELEFONE = re.compile(r"(?<![\w.])(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\w|[.,]\d)")
_PIX = re.compile(
    r"\bchave\s+pix\b|\bpix\s*(?:copia\s+e\s+cola|:)|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_CONTA = re.compile(
    r"\b(?:ag[eê]ncia|ag\.|c/c|conta\s+corrente|conta\s+poupan[cç]a|conta)\s*(?:n[ºo°.]\s*)?:?\s*\d[\d.\-]{2,}",
    re.IGNORECASE,
)
_BOLETO = re.compile(r"(?<!\d)(?:\d[\s.\-]?){46,47}\d(?!\d)")


def _digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _mesmo_telefone(a: str, b: str) -> bool:
    """Two phone numbers are the same when one's digits are the other's suffix (+55 / DDD optional), >= 8 digits."""
    da, db = _digitos(a), _digitos(b)
    return len(da) >= 8 and len(db) >= 8 and (da.endswith(db) or db.endswith(da))


def contato_nao_permitido(
    resposta: str, contatos_permitidos: Iterable[str], mensagens_lead: Iterable[str] = (),
) -> dict[str, Any] | None:
    """Phones, e-mails, PIX keys, bank account/agency and boleto lines in the reply. Allowed only when equal to an
    org-official contact (``contatos_oficiais`` spec) or a value the LEAD typed itself in this thread."""
    oficiais = [c for c in contatos_permitidos if c and c.strip()]
    do_lead = " \n ".join(mensagens_lead)
    emails_ok = {e.casefold() for c in oficiais for e in _EMAIL.findall(c)} | {e.casefold() for e in _EMAIL.findall(do_lead)}
    fones_ok = [m.group(0) for c in oficiais for m in _TELEFONE.finditer(c)] + [m.group(0) for m in _TELEFONE.finditer(do_lead)]
    texto = unicodedata.normalize("NFKC", resposta)
    achado: dict[str, int] = {}
    emails = {e.casefold() for e in _EMAIL.findall(texto)} - emails_ok
    if emails:
        achado["emails"] = len(emails)
    fones = {m.group(0) for m in _TELEFONE.finditer(texto) if not _BOLETO.fullmatch(m.group(0))}
    fones = {f for f in fones if not any(_mesmo_telefone(f, ok) for ok in fones_ok)}
    if fones:
        achado["telefones"] = len(fones)
    if _PIX.search(texto):
        achado["pix"] = len(_PIX.findall(texto))
    if _CONTA.search(texto):
        achado["conta"] = len(_CONTA.findall(texto))
    if _BOLETO.search(texto):
        achado["boleto"] = len(_BOLETO.findall(texto))
    return achado or None


_CPF = re.compile(r"(?<![\d.])\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}(?![\d])")
_CNPJ = re.compile(r"(?<![\d.])\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}(?![\d])")
_RG = re.compile(r"\brg\b\s*(?:n[ºo°.]\s*)?:?\s*\d[\d.\-xX]{5,}|(?<![\d.])\d{1,2}\.\d{3}\.\d{3}-[\dxX](?![\d])", re.IGNORECASE)


def pii_na_resposta(resposta: str, cnpjs_proprios: Iterable[str] = ()) -> dict[str, Any] | None:
    """A CPF with valid check digits (never echoed, not even the lead's own), an RG-shaped value, or a CNPJ that
    is not the agency's own."""
    texto = unicodedata.normalize("NFKC", resposta)
    proprios = {_digitos(c) for c in cnpjs_proprios if c}
    achado: dict[str, int] = {}
    cpfs = [m for m in _CPF.finditer(texto) if cpf_dv_valido(_digitos(m.group(0)))]
    if cpfs:
        achado["cpf"] = len(cpfs)
    cnpjs = [m for m in _CNPJ.finditer(texto)
             if cnpj_dv_valido(_digitos(m.group(0))) and _digitos(m.group(0)) not in proprios]
    if cnpjs:
        achado["cnpj"] = len(cnpjs)
    rgs = _RG.findall(texto)
    if rgs:
        achado["rg"] = len(rgs)
    return achado or None


_B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])")
_HEX = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{40,}(?![0-9A-Fa-f])")
_TITULO_MD = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
_JSON = re.compile(r"[{\[]\s*\"[^\"\n]{1,60}\"\s*:|^\s*\[\s*[{\[\"]", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+\S", re.MULTILINE)
#: Function words that tell the languages apart (a heuristic floor, not content): words shared with Portuguese
#: are left out of the foreign sets.
_STOP_PT = frozenset("de da do das dos em no na nos nas um uma uns para por com que não nao se os as o a e é ou mais mas como você voce está esta já ja também tambem muito quando onde ele ela eu meu minha seu sua nós".split())
_STOP_EN = frozenset("the and is are you your of to in that this it for with on as be at have not or but what was were will would can could which their there from by about".split())
_STOP_ES = frozenset("el los las y es son usted tu tus del al lo con una unos para por pero qué como está están tiene tienen muy también cuando donde yo mi sus nosotros hay".split())


def formato_suspeito(resposta: str, max_chars: int = 1200, max_bullets: int = 6) -> dict[str, Any] | None:
    """Encoded or structured output that carries data out past the shingle check: base64 / hex runs of 40+,
    code fences, markdown headings, JSON, more than ``max_bullets`` bullet lines, a reply over ``max_chars``
    or one mostly in another language. ``detalhe`` holds the shape codes, never a fragment."""
    if not resposta or not resposta.strip():
        return None
    achado: dict[str, Any] = {}
    if tem_caractere_oculto(resposta):  # zero-width / bidi / tag characters: nothing a person reads, a channel for data
        achado["caractere_oculto"] = True
    if _B64.search(resposta) or _HEX.search(resposta):
        achado["codificado"] = True
    if "```" in resposta or "~~~" in resposta:
        achado["bloco_codigo"] = True
    if _TITULO_MD.search(resposta):
        achado["titulo"] = True
    if _JSON.search(resposta):
        achado["json"] = True
    if len(_BULLET.findall(resposta)) > max_bullets:
        achado["lista_longa"] = True
    if len(resposta) > max_chars:
        achado["longo"] = True
    palavras = re.findall(r"[a-zà-ú']+", resposta.casefold())
    if len(palavras) >= 12:
        pt = sum(1 for w in palavras if w in _STOP_PT)
        fora = max(sum(1 for w in palavras if w in _STOP_EN), sum(1 for w in palavras if w in _STOP_ES))
        if fora >= 4 and fora > pt:
            achado["outro_idioma"] = True
    return achado or None


def contar_padroes(textos: Iterable[str], padroes: Iterable[str]) -> int:
    """How many DISTINCT regexes of ``padroes`` match any of ``textos`` (broken patterns logged + skipped)."""
    alvos = skeleton_targets(textos)
    n = 0
    for p in padroes:
        try:
            rx = re.compile(p, re.IGNORECASE)
        except re.error:
            logger.error("noctusai_lib.llm.guardrails.invalid_pattern")
            continue
        if any(rx.search(a) for a in alvos):
            n += 1
    return n


def padroes_proibidos(resposta: str, padroes: Iterable[str]) -> dict[str, Any] | None:
    """The generic matcher: the rule's ``parametros.padroes`` (DATA -- financing promises, guarantees,
    verification codes, payment requests, protected traits) found in the reply. Counts only."""
    n = contar_padroes([resposta], padroes)
    return {"padroes": n} if n else None


#: The compiled shapes themselves, public for consumers that REDACT instead of detect (agents ``texto_seguro``).
LINK_PATTERN = _LINK
PIX_PATTERN = _PIX
CPF_PATTERN = _CPF
CNPJ_PATTERN = _CNPJ
