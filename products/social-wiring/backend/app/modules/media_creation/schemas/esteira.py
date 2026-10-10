"""Esteira de reels — request schemas, strict at the HTTP boundary (esteira-contract.md 5.1 / 5.4).

Response shapes are the plain dicts of ``esteira_service`` (they mirror ``types/esteira.ts``).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

MAX_TITULO = 200
MAX_LEGENDA = 2200
MAX_HASHTAGS = 30
MAX_LINKS = 10
MAX_MOTIVO = 1000
MAX_LEMBRETE_MINUTOS = 60 * 24 * 365  # a year ahead is the most a reminder offset means
#: cs_posts_recorrencia_valid (migration 241)
Recorrencia = Literal["diaria", "semanal", "mensal", "anual"]
PERMALINK_RE = re.compile(r"^https://(www\.)?instagram\.com/")
#: Fields a PATCH must never carry (they have dedicated endpoints / are immutable).
CAMPOS_NAO_EDITAVEIS = frozenset({"etapa_id", "marca_id", "headline_id", "roteiro_id"})


def _strip(value: Optional[str]) -> Optional[str]:
    return value.strip() if isinstance(value, str) else value


def _permalink(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not PERMALINK_RE.match(value):
        raise ValueError("O permalink deve ser um link https do Instagram.")
    return value


class PostCreate(StrictHttpModel):
    marca_id: uuid.UUID
    titulo: Optional[str] = Field(default=None, max_length=MAX_TITULO)
    headline_id: Optional[uuid.UUID] = None
    etapa_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    conta_id: Optional[uuid.UUID] = None
    gravacao_em: Optional[date] = None
    data_entrega: Optional[datetime] = None

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: Optional[str]) -> Optional[str]:
        v = _strip(v)
        return v or None


class LinkProducao(StrictHttpModel):
    rotulo: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Os links de produção devem ser https.")
        return v


class PostUpdate(StrictHttpModel):
    titulo: Optional[str] = Field(default=None, min_length=1, max_length=MAX_TITULO)
    conta_id: Optional[uuid.UUID] = None
    gravacao_em: Optional[date] = None
    legenda: Optional[str] = Field(default=None, max_length=MAX_LEGENDA)
    hashtags: Optional[list[str]] = Field(default=None, max_length=MAX_HASHTAGS)
    primeiro_comentario: Optional[str] = Field(default=None, max_length=MAX_LEGENDA)
    links_producao: Optional[list[LinkProducao]] = Field(default=None, max_length=MAX_LINKS)
    permalink: Optional[str] = Field(default=None, max_length=500)
    ig_media_id: Optional[str] = Field(default=None, max_length=100)
    arquivado: Optional[bool] = None
    # The card hub's "Datas" columns (the seed hub has no Datas write route: they are written here).
    # `data_entrega` is "Postagem prevista". Validation mirrors the column types / CHECKs of 241.
    data_inicio: Optional[datetime] = None
    data_entrega: Optional[datetime] = None
    entrega_concluida: Optional[bool] = None
    lembrete_minutos_antes: Optional[int] = Field(default=None, ge=0, le=MAX_LEMBRETE_MINUTOS)
    recorrencia: Optional[Recorrencia] = None

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: Optional[str]) -> Optional[str]:
        v = _strip(v)
        if v is not None and not v:
            raise ValueError("O título não pode ser vazio.")
        return v

    @field_validator("permalink")
    @classmethod
    def _permalink_ok(cls, v: Optional[str]) -> Optional[str]:
        return _permalink(v)

    @field_validator("hashtags")
    @classmethod
    def _hashtags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        return [h.strip() for h in v if h and h.strip()]


class MoverEtapaRequest(StrictHttpModel):
    # A stage ID, never a name: stages are user-editable rows. An unknown id is a 404.
    para_etapa_id: str = Field(min_length=1, max_length=64)
    novo_indice: Optional[int] = Field(default=None, ge=0)
    motivo: Optional[str] = Field(default=None, max_length=MAX_MOTIVO)
    permalink: Optional[str] = Field(default=None, max_length=500)

    @field_validator("permalink")
    @classmethod
    def _permalink_ok(cls, v: Optional[str]) -> Optional[str]:
        return _permalink(v)


class HeadlineBind(StrictHttpModel):
    headline_id: Optional[uuid.UUID] = None
    texto: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _exatamente_um(self) -> "HeadlineBind":
        if self.texto is not None:
            self.texto = self.texto.strip()
        if (self.headline_id is None) == (not self.texto):
            raise ValueError("Informe headline_id ou texto (apenas um).")
        return self


class RoteiroBind(StrictHttpModel):
    roteiro_id: uuid.UUID
