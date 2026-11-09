"""Roteiro request bodies (CONTRACT roteiro-ciclo §3, R2/R3/R12).

A roteiro is born a `rascunho` and is saved on every edit (owner decision 2026-11-09), so NOTHING is required to
create one: `imoveis` may be empty (0-50) and `data_visita` may be absent. The date is required only to GERAR
(R8, enforced server-side by `roteiro_gerar`) and may not be nulled on a gerado roteiro (R3, enforced by
`roteiros_service.atualizar` — it depends on the stored status, which a body model cannot see).

Every body rejects unknown fields (`StrictHttpModel`, 422).
"""
from __future__ import annotations

from datetime import date, time
from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.modules.card_hub.roteiro_erros import MSG_SEM_DATA

#: Kept under the historical name: the sentence is part of the product's vocabulary.
MSG_DATA_OBRIGATORIA = MSG_SEM_DATA


class RoteiroCreateBodyV2(StrictHttpModel):
    #: The códigos IN VISITING ORDER — the array index becomes `visitas.ordem`. May be empty: a draft is created on
    #: the first meaningful edit, which is not always an imóvel.
    imoveis: list[str] = Field(default_factory=list, max_length=50)
    data_visita: Optional[date] = None
    titulo: Optional[str] = None
    atendimento_id: Optional[UUID] = None
    #: Optional time of the visit ("HH:MM"); makes the feedback prompt due from that time.
    hora_visita: Optional[time] = None


class RoteiroPatchBodyV2(StrictHttpModel):
    titulo: Optional[str] = None
    #: Explicit null clears the date on a DRAFT; on a gerado roteiro the service answers 422 `roteiro_sem_data`.
    data_visita: Optional[date] = None
    #: Explicit null clears the time.
    hora_visita: Optional[time] = None


class VisitaReagendarBody(StrictHttpModel):
    """R12 — the date/time of the NEW roteiro that replaces the rescheduled visita (both optional)."""

    data_visita: Optional[date] = None
    hora_visita: Optional[time] = None
