"""Meu Perfil + Treinamentos request schemas (geracao-contract.md §4.1/§4.2).

Responses are plain dicts built by the services; they mirror the TS types in
``src/types/geracao.ts`` (``PerfilCriacao``, ``Taxonomias``, ``Treinamento``).
The "at most 3" rule is enforced by the service (so the 422 carries the contract's
pt-BR message) AND by the DB CHECK; here only the length caps live.
"""
import uuid
from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

MAX_BIO_CHARS = 5_000
MAX_TEXTO_CHARS = 3_000


class PerfilCriacaoUpdate(StrictHttpModel):
    """PATCH semantics: only the fields present in the body are written."""

    marca_id: uuid.UUID
    bio: Optional[str] = Field(default=None, max_length=MAX_BIO_CHARS)
    nichos: Optional[list[int]] = None
    profissoes: Optional[list[int]] = None
    apresentacao_magnetica: Optional[str] = Field(default=None, max_length=MAX_TEXTO_CHARS)
    ctas: Optional[str] = Field(default=None, max_length=MAX_TEXTO_CHARS)


class TreinamentoCreate(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=160)
    descricao: str = Field(default="", max_length=1_000)
    video_url: Optional[str] = Field(default=None, max_length=2_000)
    ativo: bool = True
    ordem: Optional[int] = Field(default=None, ge=0)


class TreinamentoUpdate(StrictHttpModel):
    """PATCH semantics; an explicit ``video_url: null`` clears the video."""

    titulo: Optional[str] = Field(default=None, min_length=1, max_length=160)
    descricao: Optional[str] = Field(default=None, max_length=1_000)
    video_url: Optional[str] = Field(default=None, max_length=2_000)
    ativo: Optional[bool] = None
    ordem: Optional[int] = Field(default=None, ge=0)
