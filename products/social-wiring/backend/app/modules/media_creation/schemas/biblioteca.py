"""Biblioteca + Minha Biblioteca -- request schemas and the handle normalizer.

Contract: ``projects/core-studio-build/specs/geracao-contract.md`` section 4.3 (endpoints 7-19) and 4.8
(response shapes, built as plain dicts by the service so they mirror ``src/types/geracao.ts``).
Strict at the HTTP boundary (``extra="forbid"``).

Since migration 351 the library (profiles, videos) is PLATFORM-WIDE: the profile writes below are admin-only
(``estruturas-contract.md`` section 4.2); ``marca_id`` on :class:`PerfilCreate` is accepted and ignored for one
release (the previous image's clients still send it).
"""
from __future__ import annotations

import re
import uuid
from typing import Literal, Optional, Union
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel

#: Reserved first path segments of instagram.com: a post/explore link, never a profile.
RESERVED_SEGMENTS = frozenset({
    "p", "reel", "reels", "tv", "explore", "stories", "accounts", "direct", "about",
    "tags", "locations", "web", "legal", "developer", "directory",
})
_URL_RE = re.compile(r"^(https?://)?(www\.)?instagram\.com/", re.IGNORECASE)
_HANDLE_RE = re.compile(r"^[a-zA-Z0-9._]{1,30}$")

MSG_HANDLE_VAZIO = "Informe o perfil do Instagram."
MSG_HANDLE_POST = "Informe o perfil, não o link de um post."
MSG_HANDLE_INVALIDO = "Perfil inválido. Use letras, números, ponto ou sublinhado (até 30)."

#: Per-request caps (section 4.3 #17) and the per-marca allow-list ceiling (keeps the pool filter's
#: id list inside a URL).
MAX_PERFIS_POR_REQUEST = 20
MAX_VIDEOS_POR_REQUEST = 50
MAX_REFERENCIAS_MARCA = 150
PAGE_SIZE = 24


class HandleInvalido(ValueError):
    """A handle that cannot be normalized (the message is pt-BR and user-facing)."""


def normalizar_handle(bruto: str) -> str:
    """Strip -> URL to handle -> reserved segments rejected -> ``^@?[a-zA-Z0-9._]{1,30}$``.
    Returns the lowercase handle without ``@`` (the stored form)."""
    s = (bruto or "").strip()
    if not s:
        raise HandleInvalido(MSG_HANDLE_VAZIO)
    if _URL_RE.match(s):
        s = _URL_RE.sub("", s, count=1)
        s = re.split(r"[/?#]", s, maxsplit=1)[0]
    s = s.lstrip("@")
    if s.lower() in RESERVED_SEGMENTS:
        raise HandleInvalido(MSG_HANDLE_POST)
    if not _HANDLE_RE.match(s):
        raise HandleInvalido(MSG_HANDLE_INVALIDO)
    return s.lower()


class PerfilCreate(StrictHttpModel):
    #: Accepted and ignored for one release (the admin adds a library profile, not a brand's).
    marca_id: Optional[uuid.UUID] = None
    handle: str = Field(min_length=1, max_length=200)
    conta_descoberta_id: Optional[uuid.UUID] = None
    #: False = a library-only profile (its videos are added by link / import; the daily sync skips it).
    monitorar: bool = True

    @field_validator("handle")
    @classmethod
    def _handle(cls, v: str) -> str:
        try:
            return normalizar_handle(v)
        except HandleInvalido as exc:
            raise ValueError(str(exc)) from None


class LinkInvalido(ValueError):
    """The pasted text is not an Instagram post link (the message is pt-BR and user-facing)."""


MSG_LINK_INVALIDO = "Informe o link de um post do Instagram (instagram.com/p/…, /reel/… ou /tv/…)."
_LINK_HOSTS = frozenset({"instagram.com", "www.instagram.com"})
_LINK_KINDS = {"p": "p", "reel": "reel", "reels": "reel", "tv": "tv"}
_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,30}$")
_LINK_USER_RE = re.compile(r"^[a-zA-Z0-9._]{1,30}$")
MAX_LINK_CHARS = 300


def extrair_shortcode(url: str) -> tuple[str, str]:
    """``(shortcode, canonical_url)`` of an Instagram post link, or :class:`LinkInvalido`.

    SSRF / abuse guard (contract section 12.5): only ``https://(www.)instagram.com`` is accepted (no userinfo, no port,
    no other host), the path must be ``/(p|reel|reels|tv)/<shortcode>/`` (an optional ``/<username>/`` precedes it, the
    form Instagram's share button produces), and the URL that is later handed to the scraper is RE-COMPOSED from the
    shortcode -- the pasted string (query, fragment, anything else) is never fetched."""
    raw = (url or "").strip()
    if not raw or len(raw) > MAX_LINK_CHARS:
        raise LinkInvalido(MSG_LINK_INVALIDO)
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        netloc_ok = parts.netloc.lower() == host  # no userinfo, no port
    except ValueError:
        raise LinkInvalido(MSG_LINK_INVALIDO) from None
    if parts.scheme.lower() != "https" or host not in _LINK_HOSTS or not netloc_ok:
        raise LinkInvalido(MSG_LINK_INVALIDO)
    segs = [x for x in parts.path.split("/") if x]
    if len(segs) == 3 and _LINK_USER_RE.match(segs[0]):
        segs = segs[1:]
    if len(segs) != 2 or segs[0].lower() not in _LINK_KINDS or not _SHORTCODE_RE.match(segs[1]):
        raise LinkInvalido(MSG_LINK_INVALIDO)
    kind, code = _LINK_KINDS[segs[0].lower()], segs[1]
    return code, f"https://www.instagram.com/{kind}/{code}/"


class PorLinkCreate(StrictHttpModel):
    url: str = Field(min_length=1, max_length=MAX_LINK_CHARS)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        try:
            extrair_shortcode(v)
        except LinkInvalido as exc:
            raise ValueError(str(exc)) from None
        return v.strip()


class OptoutCreate(StrictHttpModel):
    handle: str = Field(min_length=1, max_length=200)
    motivo: Optional[str] = Field(default=None, max_length=1000)
    origem: Literal["email", "dpo", "admin"]

    @field_validator("handle")
    @classmethod
    def _handle(cls, v: str) -> str:
        try:
            return normalizar_handle(v)
        except HandleInvalido as exc:
            raise ValueError(str(exc)) from None


class PerfilPatch(StrictHttpModel):
    status: Optional[Literal["ativo", "pausado"]] = None
    conta_descoberta_id: Optional[uuid.UUID] = None
    monitorar: Optional[bool] = None
    #: Display-name override (the profile's real name stays what the source served until an admin edits it).
    nome: Optional[str] = Field(default=None, min_length=1, max_length=120)


class ReferenciasPerfil(StrictHttpModel):
    marca_id: uuid.UUID
    modo: Literal["perfil"]
    perfil_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_PERFIS_POR_REQUEST)
    auto_atualizar: bool = True


class ReferenciasVideo(StrictHttpModel):
    marca_id: uuid.UUID
    modo: Literal["video"]
    viral_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_VIDEOS_POR_REQUEST)


ReferenciasCreate = Union[ReferenciasPerfil, ReferenciasVideo]


class ReferenciaPatch(StrictHttpModel):
    auto_atualizar: Optional[bool] = None
    #: ISO date; the empty string is not accepted (omit the field to leave it unchanged).
    posts_ate: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


__all__ = [
    "HandleInvalido",
    "LinkInvalido",
    "MSG_LINK_INVALIDO",
    "PorLinkCreate",
    "extrair_shortcode",
    "MAX_REFERENCIAS_MARCA",
    "PAGE_SIZE",
    "PerfilCreate",
    "PerfilPatch",
    "ReferenciaPatch",
    "ReferenciasCreate",
    "ReferenciasPerfil",
    "ReferenciasVideo",
    "normalizar_handle",
]
