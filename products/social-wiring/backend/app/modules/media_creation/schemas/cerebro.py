"""Segundo Cérebro — request schemas (strict at the HTTP boundary) and limits.

Contract: ``projects/core-studio/specs/cerebro-contract.md`` §4. Responses are
plain dicts built by :class:`~app.modules.media_creation.services.cerebro_service.CerebroService`
in the shape of the contract's TypeScript types.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel

#: Hard ceiling of ``cs_brains.content`` (table CHECK) and of every append.
MAX_CONTENT_CHARS = 200_000
MAX_ANSWER_CHARS = 10_000
MAX_BIO_CHARS = 5_000
MAX_NAME_CHARS = 80


def _clean_name(value: str) -> str:
    name = (value or "").strip()
    if not 1 <= len(name) <= MAX_NAME_CHARS:
        raise ValueError(f"informe um nome de 1 a {MAX_NAME_CHARS} caracteres")
    return name


class BrainCreate(StrictHttpModel):
    marca_id: uuid.UUID
    name: str

    _name = field_validator("name")(lambda cls, v: _clean_name(v))


class BrainRename(StrictHttpModel):
    name: str

    _name = field_validator("name")(lambda cls, v: _clean_name(v))


class ContentUpdate(StrictHttpModel):
    content: str = Field(max_length=MAX_CONTENT_CHARS)
    expected_version: int = Field(ge=0)


class AnswerUpdate(StrictHttpModel):
    text: str = Field(max_length=MAX_ANSWER_CHARS)


class AnswersReset(StrictHttpModel):
    confirm: Literal[True]


class ReviewRequest(StrictHttpModel):
    question_ids: Optional[list[str]] = Field(default=None, max_length=50)


class SuggestionAction(StrictHttpModel):
    action: Literal["accept", "dismiss"]


class SynthesizeRequest(StrictHttpModel):
    mode: Literal["replace", "append"]
    expected_version: int = Field(ge=0)


class PerfilUpdate(StrictHttpModel):
    marca_id: uuid.UUID
    bio: str = Field(max_length=MAX_BIO_CHARS)
