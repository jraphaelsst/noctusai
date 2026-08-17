from datetime import date, datetime, time
from typing import Literal, Optional

from pydantic import BaseModel

StatusCaptacao = Literal["agendado", "captado", "cancelado"]


class CaptacaoEquipamentoOut(BaseModel):
    id: str
    equipamento_id: str
    nome: Optional[str] = None
    categoria: Optional[str] = None
    conferido: bool


class CaptacaoCreate(BaseModel):
    negocio_id: Optional[str] = None
    cliente_id: Optional[str] = None
    imovel_id: Optional[str] = None
    data: date
    hora: time = time(9, 0)
    duracao_minutos: int = 120
    endereco: str
    maps_url: Optional[str] = None
    responsavel: Optional[str] = None
    observacoes: Optional[str] = None
    equipamento_ids: list[str] = []


class CaptacaoUpdate(BaseModel):
    negocio_id: Optional[str] = None
    cliente_id: Optional[str] = None
    imovel_id: Optional[str] = None
    data: Optional[date] = None
    hora: Optional[time] = None
    duracao_minutos: Optional[int] = None
    endereco: Optional[str] = None
    maps_url: Optional[str] = None
    responsavel: Optional[str] = None
    status: Optional[StatusCaptacao] = None
    observacoes: Optional[str] = None
    equipamento_ids: Optional[list[str]] = None


class ChecklistUpdate(BaseModel):
    """Marca/desmarca um item do checklist de equipamentos."""

    conferido: bool


class CaptacaoOut(BaseModel):
    id: str
    org_id: str
    negocio_id: Optional[str] = None
    cliente_id: Optional[str] = None
    imovel_id: Optional[str] = None
    data: date
    hora: time
    duracao_minutos: int
    endereco: str
    maps_url: Optional[str] = None
    responsavel: Optional[str] = None
    status: str
    observacoes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    cliente_nome: Optional[str] = None
    equipamentos: list[CaptacaoEquipamentoOut] = []
