"""Schemas for ``cs_post_publicacoes`` (CoreStudio post axes, migration 342)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

Rede = Literal["instagram", "facebook", "youtube"]
Formato = Literal["feed", "carrossel", "reel", "story", "short", "video_longo"]
PublicacaoStatus = Literal["agendado", "publicado", "falhou", "cancelado"]


class PublicacaoCriar(StrictHttpModel):
    rede: Rede
    formato: Formato
    conta_id: str = Field(min_length=1, max_length=64)
    publicar_em: datetime


class PublicacaoAtualizar(StrictHttpModel):
    """Reschedule and/or cancel. Publication outcomes (publicado/falhou) belong to the publisher (slice S4)."""

    publicar_em: Optional[datetime] = None
    status: Optional[Literal["cancelado"]] = None
