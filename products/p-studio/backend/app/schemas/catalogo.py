"""Serviços e equipamentos — os dois catálogos do estúdio.

Compartilham o módulo porque compartilham a forma (item de catálogo com
`ativo` para soft-delete) e porque nenhum dos dois tem regra de negócio
própria: são cadastros que alimentam negócios e captações.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

CategoriaEquipamento = Literal[
    "camera", "lente", "drone", "microfone", "gimbal",
    "bateria", "cartao", "iluminacao", "outro",
]


# ── Serviços ─────────────────────────────────────────────────────────────
class ServicoCreate(BaseModel):
    nome: str
    categoria: Optional[str] = None
    preco: float = 0
    prazo_dias: int = 3
    descricao: Optional[str] = None


class ServicoUpdate(BaseModel):
    nome: Optional[str] = None
    categoria: Optional[str] = None
    preco: Optional[float] = None
    prazo_dias: Optional[int] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None


class ServicoOut(BaseModel):
    id: str
    org_id: str
    nome: str
    categoria: Optional[str] = None
    preco: float
    prazo_dias: int
    descricao: Optional[str] = None
    ativo: bool
    created_at: datetime
    updated_at: datetime


# ── Equipamentos ─────────────────────────────────────────────────────────
class EquipamentoCreate(BaseModel):
    nome: str
    marca: Optional[str] = None
    modelo: Optional[str] = None
    numero_serie: Optional[str] = None
    categoria: Optional[CategoriaEquipamento] = None
    valor: float = 0
    quantidade: int = 1
    observacoes: Optional[str] = None


class EquipamentoUpdate(BaseModel):
    nome: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    numero_serie: Optional[str] = None
    categoria: Optional[CategoriaEquipamento] = None
    valor: Optional[float] = None
    quantidade: Optional[int] = None
    observacoes: Optional[str] = None
    ativo: Optional[bool] = None


class EquipamentoOut(BaseModel):
    id: str
    org_id: str
    nome: str
    marca: Optional[str] = None
    modelo: Optional[str] = None
    numero_serie: Optional[str] = None
    categoria: Optional[str] = None
    valor: float
    quantidade: int
    observacoes: Optional[str] = None
    ativo: bool
    created_at: datetime
    updated_at: datetime
