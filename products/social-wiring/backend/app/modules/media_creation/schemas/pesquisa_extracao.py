"""Pesquisa Extrair — request schemas (strict at the HTTP boundary).

Contract: projects/core-studio/specs/pesquisa-wave2-contract.md section 3.
The upper bound on ``posts`` is the config knob
``pesquisa_extracao_max_posts_por_job`` (checked by the service → 422), not a
hard-coded number here.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

from app.modules.media_creation.pesquisa_wave2_constants import EXTRACAO_TIPOS_MAX

FonteKindLit = Literal["instagram_media", "youtube_video", "mc_post"]
TipoLit = Literal["pesquisa", "assuntos_virais"]


class PostRef(StrictHttpModel):
    kind: FonteKindLit
    account_id: Optional[uuid.UUID] = None
    id: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _account_required(self) -> "PostRef":
        if self.kind != "mc_post" and self.account_id is None:
            raise ValueError("account_id é obrigatório para posts do Instagram e do YouTube")
        return self


class ExtracaoCreate(StrictHttpModel):
    marca_id: uuid.UUID
    tipos: list[TipoLit] = Field(min_length=1, max_length=EXTRACAO_TIPOS_MAX)
    posts: list[PostRef] = Field(min_length=1)
    reextrair: bool = False

    @model_validator(mode="after")
    def _unique_tipos(self) -> "ExtracaoCreate":
        if len(set(self.tipos)) != len(self.tipos):
            raise ValueError("tipos repetidos")
        return self
