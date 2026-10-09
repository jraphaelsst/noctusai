"""Minha Pesquisa — request schemas (strict at the HTTP boundary)."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel

MAX_CONTENT_CHARS = 500


class ItemsCreate(StrictHttpModel):
    marca_id: uuid.UUID
    variable_slug: str = Field(min_length=1, max_length=120)
    lines: list[str] = Field(min_length=1, max_length=200)

    @field_validator("lines")
    @classmethod
    def _clean(cls, lines: list[str]) -> list[str]:
        out = [ln.strip() for ln in lines if ln and ln.strip()]
        if not out:
            raise ValueError("informe ao menos uma linha")
        if any(len(ln) > MAX_CONTENT_CHARS for ln in out):
            raise ValueError(f"cada item aceita no máximo {MAX_CONTENT_CHARS} caracteres")
        return out


class ItemsClassify(StrictHttpModel):
    marca_id: uuid.UUID
    text: str = Field(min_length=1, max_length=20_000)


class ItemsBulk(StrictHttpModel):
    marca_id: uuid.UUID
    action: Literal["approve", "reject", "delete"]
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class ItemsEmpty(StrictHttpModel):
    marca_id: uuid.UUID
    confirm: Literal[True]
