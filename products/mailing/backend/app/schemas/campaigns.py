"""Pydantic schemas for campaigns."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    template_id: str
    list_id: str
    assunto_override: Optional[str] = None
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None


class CampaignUpdate(BaseModel):
    nome: Optional[str] = None
    template_id: Optional[str] = None
    list_id: Optional[str] = None
    assunto_override: Optional[str] = None
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None


class CampaignSchedule(BaseModel):
    scheduled_at: datetime
