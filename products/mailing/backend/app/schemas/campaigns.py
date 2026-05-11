"""Pydantic schemas for campaigns."""
from typing import Optional
from datetime import datetime
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class CampaignCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=200)
    template_id: str
    list_id: str
    assunto_override: Optional[str] = None
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None


class CampaignUpdate(StrictHttpModel):
    nome: Optional[str] = None
    template_id: Optional[str] = None
    list_id: Optional[str] = None
    assunto_override: Optional[str] = None
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None


class CampaignSchedule(StrictHttpModel):
    scheduled_at: datetime
