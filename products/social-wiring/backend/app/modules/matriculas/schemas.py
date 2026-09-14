"""Request bodies for the structured-matrícula routes (migration 109).

`StrictHttpModel` (house default) rejects unknown keys, so a typo'd field is a
422 naming it rather than a silently-ignored value.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class ExtracaoDeDocumentoBody(StrictHttpModel):
    """Transcribe a matrícula PDF already attached to an imóvel."""

    codigo: str = Field(min_length=1, max_length=64)
    imovel_documento_id: UUID


class SelecaoAtosBody(StrictHttpModel):
    """The acts a contract quotes, in the order they appear in it.

    Replaces the whole selection. An empty `ato_ids` clears it (and then
    `extracao_id` may be omitted); otherwise every id must belong to
    `extracao_id`.
    """

    extracao_id: Optional[UUID] = None
    ato_ids: list[UUID] = Field(default_factory=list, max_length=500)


class FontesMatriculaBody(StrictHttpModel):
    """The operator's choice of título aquisitivo / ônus source acts.

    Absence means "leave alone" (`model_fields_set`, never `is None`): `null`
    for the título, or `null` / `[]` for the ônus, clears that pointer. Writing
    a pointer IS the confirmation — the heuristic never writes one.
    """

    titulo_aquisitivo_ato_id: Optional[UUID] = None
    onus_ato_ids: Optional[list[UUID]] = Field(default=None, max_length=200)


__all__ = ["ExtracaoDeDocumentoBody", "FontesMatriculaBody", "SelecaoAtosBody"]
