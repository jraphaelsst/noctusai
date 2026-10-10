"""Assuntos Virais — request schemas (strict at the HTTP boundary).

Contract: projects/core-studio/specs/pesquisa-wave2-contract.md section 3.
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel

from app.modules.media_creation.pesquisa_wave2_constants import VIRAL_TOPIC_MAX_CHARS


class AssuntosCreate(StrictHttpModel):
    marca_id: uuid.UUID
    topics: list[str] = Field(min_length=1, max_length=100)

    @field_validator("topics")
    @classmethod
    def _clean(cls, topics: list[str]) -> list[str]:
        out = [t.strip() for t in topics if t and t.strip()]
        if not out:
            raise ValueError("informe ao menos um assunto")
        if any(len(t) > VIRAL_TOPIC_MAX_CHARS for t in out):
            raise ValueError(f"cada assunto aceita no máximo {VIRAL_TOPIC_MAX_CHARS} caracteres")
        return out


class AssuntosBulk(StrictHttpModel):
    marca_id: uuid.UUID
    action: Literal["approve", "reject", "delete"]
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class AssuntosEmpty(StrictHttpModel):
    marca_id: uuid.UUID
    status: Literal["approved", "pending"]
    confirm: Literal[True]
