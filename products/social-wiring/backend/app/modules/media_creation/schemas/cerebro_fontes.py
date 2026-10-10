"""Segundo Cérebro — sources slice request schemas (cerebro-contract.md §4,
endpoints 14, 15, 19-24). Strict at the HTTP boundary."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

from app.modules.media_creation.schemas.cerebro import MAX_CONTENT_CHARS

MAX_EXTRACTION_NAME_CHARS = 120
MAX_TARGETS = 20


def _clean_extraction_name(value: str) -> str:
    name = (value or "").strip()
    if not 1 <= len(name) <= MAX_EXTRACTION_NAME_CHARS:
        raise ValueError(f"informe um nome de 1 a {MAX_EXTRACTION_NAME_CHARS} caracteres")
    return name


class YoutubeImportRequest(StrictHttpModel):
    links: list[str] = Field(min_length=1, max_length=10)


class ExtractionCreate(StrictHttpModel):
    marca_id: uuid.UUID
    name: str
    brain_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_TARGETS)
    text: Optional[str] = Field(default=None, max_length=MAX_CONTENT_CHARS)
    url: Optional[str] = Field(default=None, max_length=2000)

    _name = field_validator("name")(lambda cls, v: _clean_extraction_name(v))

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "ExtractionCreate":
        if (self.text is None) == (self.url is None):
            raise ValueError("informe exatamente um entre texto e link")
        return self


class ExtractionUpdate(StrictHttpModel):
    name: Optional[str] = None
    transcript: Optional[str] = Field(default=None, max_length=MAX_CONTENT_CHARS)
    brain_ids: Optional[list[uuid.UUID]] = Field(default=None, min_length=1, max_length=MAX_TARGETS)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return None if v is None else _clean_extraction_name(v)


class ExtractionApply(StrictHttpModel):
    brain_ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=MAX_TARGETS)
