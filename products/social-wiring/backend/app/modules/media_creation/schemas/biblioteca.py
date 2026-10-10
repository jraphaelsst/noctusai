"""Biblioteca + Minha Biblioteca -- request schemas and the handle normalizer.

Contract: ``projects/core-studio/specs/geracao-contract.md`` section 4.3 (endpoints 7-19) and 4.8
(response shapes, built as plain dicts by the service so they mirror ``src/types/geracao.ts``).
Strict at the HTTP boundary (``extra="forbid"``).
"""
from __future__ import annotations

import re
import uuid
from typing import Literal, Optional, Union

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
    marca_id: uuid.UUID
    handle: str = Field(min_length=1, max_length=200)
    conta_descoberta_id: Optional[uuid.UUID] = None

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
