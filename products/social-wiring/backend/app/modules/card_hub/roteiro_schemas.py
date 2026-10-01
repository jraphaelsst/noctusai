"""Roteiro request bodies for the atendimento-partes-imoveis project (CONTRACT §5.1).

Lives beside `roteiros_service` rather than in `schemas.py` because that file
has no owner in Wave B; they are the bodies of the roteiro create/patch routes
(CONTRACT §10 item 3).

`data_visita` is required on create and may never be nulled on patch. Both
refusals carry the SAME message — `"Informe a data da visita."` — raised from a
`mode="before"` validator, because Pydantic's own "Field required" would not
distinguish a missing key from an explicit null and neither reads as a sentence
a corretor can act on. Past dates are accepted (CONTRACT §11, provisional).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

MSG_DATA_OBRIGATORIA = "Informe a data da visita."


class RoteiroCreateBodyV2(StrictHttpModel):
    #: The códigos IN VISITING ORDER — the array index becomes `visitas.ordem`.
    imoveis: list[str] = Field(min_length=1, max_length=50)
    data_visita: date
    titulo: Optional[str] = None
    atendimento_id: Optional[UUID] = None

    @model_validator(mode="before")
    @classmethod
    def _data_obrigatoria(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("data_visita") in (None, ""):
            raise ValueError(MSG_DATA_OBRIGATORIA)
        return data


class RoteiroPatchBodyV2(StrictHttpModel):
    titulo: Optional[str] = None
    data_visita: Optional[date] = None

    @model_validator(mode="before")
    @classmethod
    def _data_nao_anulavel(cls, data: Any) -> Any:
        # Absent is fine (field untouched); PRESENT-but-null is the refusal.
        if isinstance(data, dict) and "data_visita" in data and data["data_visita"] in (None, ""):
            raise ValueError(MSG_DATA_OBRIGATORIA)
        return data
