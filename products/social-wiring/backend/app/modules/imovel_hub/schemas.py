"""Request bodies for `/api/imoveis/{codigo}/...`.

`StrictHttpModel` (house default) rejects unknown keys, so a typo'd field is
a 422 naming it rather than a silently-ignored value.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class ImovelDadosPatchBody(StrictHttpModel):
    """The cartório fields a human may set.

    Every field is Optional AND nullable, and absence is what means "leave
    alone" — `None` is a real value, because clearing a wrongly-typed
    matrícula number has to be possible. `model_fields_set` is what the
    service reads, never `is None`.
    """

    numero_matricula: Optional[str] = Field(default=None, max_length=64)
    numero_registro_imoveis: Optional[str] = Field(default=None, max_length=64)
    prefeitura_cadastro_imobiliario: Optional[str] = Field(
        default=None, max_length=200
    )
    #: 🔴 A user id, never a name. The 5% captação slice (migration 076) is
    #: attributed to whoever brought the property in, and free text cannot be
    #: aggregated: two spellings become two people and "what did I earn this
    #: month" stops being answerable.
    captador_user_id: Optional[UUID] = None


__all__ = ["ImovelDadosPatchBody"]
