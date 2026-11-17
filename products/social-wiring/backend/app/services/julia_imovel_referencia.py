"""Julia > resolve a listing from what the lead pasted (Lais study S5, owner 2026-11-17): a URL, a portal code or the portal's
own "stock text" ("Olá, tenho interesse no imóvel ... Cód. 12345").

A lead that comes from a portal or a shared link rarely types our listing code: it sends the portal's link, the portal's
ad reference or the pre-filled message the portal generated. This module turns that text into an ORDERED, BOUNDED list of
candidate codes (`candidatos`, pure, no I/O) and walks them through the org's catalog (`resolver`, the catalog seam of
`julia_catalogo_service`), returning the first PUBLISHED listing. It never invents: nothing found = `encontrado=False`.

Candidate sources, strongest first:
  url      the org's own listing URL (`.../imovel/<codigo>`, `?codigo=`) and portal URLs that end in the portal's numeric ad id
           (`...-id-2712345678/`, `...-1234567.html`)
  rotulo   a labelled code in free text (`Cód.`, `Código`, `Ref.`, `Referência`, `ID`, `Anúncio`)
  solto    the whole message is one code-shaped token (`AP0042`)

The portal ad id is a CANDIDATE, not a fact: it only resolves when the org's catalog carries that code (portal ids are
often mirrored into the CRM code). It is looked up, never trusted. At most `CANDIDATOS_MAX` lookups per call (a live-Vista
catalog pays a request per lookup).
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

CANDIDATOS_MAX = 4
TEXTO_MAX = 2000
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_PROPRIO_RE = re.compile(r"/im[oó]ve(?:l|is)/([A-Za-z0-9][A-Za-z0-9_-]{1,39})/?$", re.IGNORECASE)
_PORTAL_ID_RE = re.compile(r"(?:-id-|-)(\d{5,15})(?:/|\.html?)?$", re.IGNORECASE)
_ROTULO_RE = re.compile(
    r"\b(?:c[oó]d(?:igo)?|ref(?:er[eê]ncia)?|id|an[uú]ncio)\b\.?\s*(?:do\s+(?:im[oó]vel|an[uú]ncio)\s*)?[:#\-]?\s*([A-Za-z]{0,4}[-]?\d[A-Za-z0-9-]{0,19})",
    re.IGNORECASE,
)
_SOLTO_RE = re.compile(r"^[A-Za-z]{1,4}-?\d{1,12}$")


def _limpo(c: str) -> Optional[str]:
    c = c.strip().strip(".,;:!?)").upper()
    return c if 2 <= len(c) <= 40 else None


def candidatos(texto: str) -> list[tuple[str, str]]:
    """`[(codigo, via)]` in priority order, de-duplicated, at most `CANDIDATOS_MAX`. `via` is `url` | `rotulo` | `solto`."""
    texto = (texto or "")[:TEXTO_MAX]
    out: list[tuple[str, str]] = []

    def _add(cod: Optional[str], via: str) -> None:
        if cod and cod not in {c for c, _ in out}:
            out.append((cod, via))

    for bruta in _URL_RE.findall(texto):
        url = urlparse(bruta.rstrip(".,;:!?)"))
        for chave in ("codigo", "cod", "ref", "id"):
            for v in parse_qs(url.query).get(chave, []):
                _add(_limpo(v), "url")
        caminho = url.path
        m = _PROPRIO_RE.search(caminho)
        if m:
            _add(_limpo(m.group(1)), "url")
        m = _PORTAL_ID_RE.search(caminho)
        if m:
            _add(_limpo(m.group(1)), "url")
    sem_urls = _URL_RE.sub(" ", texto)
    for m in _ROTULO_RE.finditer(sem_urls):
        _add(_limpo(m.group(1)), "rotulo")
    corpo = sem_urls.strip()
    if _SOLTO_RE.match(corpo):
        _add(_limpo(corpo), "solto")
    return out[:CANDIDATOS_MAX]


def resolver(catalogo: Any, texto: str) -> dict[str, Any]:
    """Walk the candidates through the catalog; `{encontrado, via?, codigo?, linha?, candidatos}` (`linha` is the catalog row,
    the caller builds the card). Candidates are listing codes only -- safe to echo."""
    achados = candidatos(texto)
    for codigo, via in achados:
        linha = catalogo.um(codigo)
        if linha is not None:
            return {"encontrado": True, "via": via, "codigo": codigo, "linha": linha, "candidatos": [c for c, _ in achados]}
    return {"encontrado": False, "candidatos": [c for c, _ in achados]}


__all__ = ["CANDIDATOS_MAX", "candidatos", "resolver"]
