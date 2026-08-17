from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class ClienteCreate(BaseModel):
    nome: str
    empresa: Optional[str] = None
    corretor: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    observacoes: Optional[str] = None
    # Dados do pagador (migração 003). Opcionais no cadastro, obrigatórios na
    # emissão de cobrança — a validação fica lá, com mensagem dizendo o campo.
    cpf_cnpj: Optional[str] = None
    cep: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    empresa: Optional[str] = None
    corretor: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: Optional[bool] = None
    cpf_cnpj: Optional[str] = None
    cep: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None


class ClienteOut(BaseModel):
    id: str
    org_id: str
    nome: str
    empresa: Optional[str] = None
    corretor: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool
    cpf_cnpj: Optional[str] = None
    cep: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    provedor: Optional[str] = None
    provedor_cliente_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ClienteMetricas(BaseModel):
    """Histórico consolidado do cliente (spec § 8).

    Calculado sob demanda a partir de negócios, imóveis e lançamentos —
    nunca armazenado, para não haver número desatualizado na tela.
    """

    cliente_id: str
    nome: str
    empresa: Optional[str] = None
    faturamento_total: float = 0
    total_servicos: int = 0
    total_imoveis: int = 0
    ticket_medio: float = 0
    ultimo_servico: Optional[str] = None
    frequencia_mensal: float = 0
