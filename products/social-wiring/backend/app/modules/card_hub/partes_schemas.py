"""Schemas for the all-parties surface (atendimento-partes-imoveis §2).

`ParteCreateBody` is the body of `POST .../compradores` (person OR company). The response models mirror CONTRACT §2.1/§2.5
key-for-key — they are what the contract tests pin.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives import identificador as ident_primitives


class ParteCreateBody(StrictHttpModel):
    """Add a party — a person (PF) or a company (PJ).

    EXACTLY ONE of `cliente_id` / `nome` / `empresa_id` / `cnpj`; the rule is
    enforced in `compradores_service.adicionar` (one place, one message).
    `razao_social` only fills a newly created empresa.
    """

    cliente_id: Optional[UUID] = None
    nome: Optional[str] = Field(default=None, max_length=255)
    celular: Optional[str] = Field(default=None, max_length=32)
    papel: Optional[str] = None
    observacao: Optional[str] = Field(default=None, max_length=2000)
    atendimento_id: Optional[UUID] = None
    lado: Optional[str] = None
    empresa_id: Optional[UUID] = None
    cnpj: Optional[str] = Field(default=None, min_length=11, max_length=18)
    razao_social: Optional[str] = Field(default=None, max_length=255)
    #: Only meaningful with `nome` (a NEW pessoa física): persisted on the
    #: created cliente as `cpf_origem='manual'`. Checked, and normalised to the canonical punctuated form.
    cpf: Optional[str] = Field(default=None, max_length=18)

    @field_validator("cpf")
    @classmethod
    def _cpf_valido(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        # Checked against the canonical punctuated shape + check digits, and
        # stored in it (`canonical-identifiers`, owner rule 2026-10-01).
        canonico = ident_primitives.canonico("cpf", v)
        if canonico is None:
            raise ValueError("CPF inválido.")
        return canonico


class EmpresaResumo(BaseModel):
    id: Optional[str] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    cnpj: Optional[str] = None
    situacao_cadastral: Optional[str] = None


class ParteItem(BaseModel):
    parte_id: Optional[str] = None
    titular: bool
    rotulo: str
    lado: Literal["comprador", "vendedor"]
    papel: str
    ordem: int
    tipo_pessoa: Literal["PF", "PJ"]
    cliente_id: Optional[str] = None
    empresa_id: Optional[str] = None
    nome: str
    documento: Optional[str] = None
    observacao: Optional[str] = None
    # Migration 193 contract qualification (party row), readable so the FE
    # form prefills: the represented company of a 'representante', and a PJ
    # party's NIRE + sede ({logradouro, numero, complemento, bairro, cidade, uf, cep}).
    representa_parte_id: Optional[str] = None
    pj_nire: Optional[str] = None
    pj_sede: Optional[dict[str, Optional[str]]] = None
    cliente: Optional[dict[str, Any]] = None
    empresa: Optional[EmpresaResumo] = None


class PartesResponse(BaseModel):
    items: list[ParteItem]
    total: int
    atendimento_id: Optional[str] = None


class ClienteLookup(BaseModel):
    id: str
    nome: Optional[str] = None
    nome_oficial: Optional[str] = None
    cpf: Optional[str] = None
    celular: Optional[str] = None
    email: Optional[str] = None


class EtapaResumo(BaseModel):
    id: str
    nome: Optional[str] = None


class AtendimentoDaPessoa(BaseModel):
    id: str
    titulo: Optional[str] = None
    etapa: Optional[EtapaResumo] = None
    status: Optional[str] = None
    arquivado: bool
    lado: str
    papel: str
    titular: bool
    parte_id: Optional[str] = None


class CertidaoLookupItem(BaseModel):
    tipo: str
    rotulo: str
    resultado_id: str
    emitida_em: str
    validade_ate: Optional[str] = None
    idade_dias: int
    stale_para_contrato: bool
    resultado: Optional[str] = None


class CertidoesLookup(BaseModel):
    max_dias: int
    data_referencia: str
    itens: list[CertidaoLookupItem]
    tipos_vencidos: list[str]
    alerta_vencidas: bool
    mensagem: Optional[str] = None


class LookupResponse(BaseModel):
    documento: str
    tipo_documento: Literal["cpf", "cnpj"]
    encontrado: Optional[Literal["cliente", "empresa"]] = None
    cliente: Optional[ClienteLookup] = None
    empresa: Optional[EmpresaResumo] = None
    ja_no_atendimento: bool
    atendimentos: list[AtendimentoDaPessoa]
    certidoes: CertidoesLookup


__all__ = [
    "AtendimentoDaPessoa",
    "CertidaoLookupItem",
    "CertidoesLookup",
    "ClienteLookup",
    "EmpresaResumo",
    "EtapaResumo",
    "LookupResponse",
    "ParteCreateBody",
    "ParteItem",
    "PartesResponse",
]
