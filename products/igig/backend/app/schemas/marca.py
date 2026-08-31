"""Pydantic contracts for Módulo 2 — Central da Marca and the Cofre de Acessos.

The brand payload is the spine M3/M4/M5 all read from, so its shape is defined
once here and reused by the repertório sidebar rather than re-derived per
screen.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "CorPaleta",
    "LinhaEditorial",
    "Persona",
    "MarcaCreate",
    "MarcaUpdate",
    "MarcaOut",
    "RepertorioOut",
    "AcessoCreate",
    "AcessoUpdate",
    "AcessoOut",
    "AcessosOut",
    "SenhaRevelada",
    "LogoOut",
]

NivelFormalidade = Literal["informal", "neutro", "formal"]


class CorPaleta(BaseModel):
    """One colour in the brand palette.

    `hex` is validated at the edge so an unusable value never reaches the
    designer's sidebar — a malformed swatch there is worse than a missing one,
    because it renders as a silent black.
    """

    nome: str = Field(min_length=1, max_length=60)
    hex: str = Field(pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class LinhaEditorial(BaseModel):
    """A content pillar (Institucional, Educacional, Comercial, …)."""

    nome: str = Field(min_length=1, max_length=80)
    descricao: str | None = Field(default=None, max_length=500)


class Persona(BaseModel):
    """Audience mapping — Módulo 2's Ficha de Persona."""

    nome: str = Field(min_length=1, max_length=80)
    avatar_url: str | None = None
    faixa_etaria: str | None = Field(default=None, max_length=40)
    ocupacao: str | None = Field(default=None, max_length=120)
    dores: list[str] = Field(default_factory=list)
    desejos: list[str] = Field(default_factory=list)


class MarcaCreate(StrictHttpModel):
    cliente_id: str
    nome: str = Field(min_length=1, max_length=200)
    logo_url: str | None = None
    paleta: list[CorPaleta] = Field(default_factory=list)
    tom_de_voz: str | None = None
    termos_proibidos: str | None = None
    nivel_formalidade: NivelFormalidade | None = None
    linhas_editoriais: list[LinhaEditorial] = Field(default_factory=list)
    personas: list[Persona] = Field(default_factory=list)


class MarcaUpdate(StrictHttpModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    logo_url: str | None = None
    paleta: list[CorPaleta] | None = None
    tom_de_voz: str | None = None
    termos_proibidos: str | None = None
    nivel_formalidade: NivelFormalidade | None = None
    linhas_editoriais: list[LinhaEditorial] | None = None
    personas: list[Persona] | None = None


class MarcaOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    cliente_id: str
    nome: str
    logo_url: str | None = None
    paleta: list[CorPaleta] = Field(default_factory=list)
    tom_de_voz: str | None = None
    termos_proibidos: str | None = None
    nivel_formalidade: str | None = None
    linhas_editoriais: list[LinhaEditorial] = Field(default_factory=list)
    personas: list[Persona] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class RepertorioOut(BaseModel):
    """What the persistent sidebar renders while someone works a tarefa.

    Deliberately NOT `MarcaOut`: the sidebar needs the client's name (context)
    and only the creative-direction fields. Sending the whole record would put
    the brand's full history behind every task screen for no benefit.
    """

    cliente_nome: str | None = None
    marca_nome: str | None = None
    logo_url: str | None = None
    paleta: list[CorPaleta] = Field(default_factory=list)
    tom_de_voz: str | None = None
    termos_proibidos: str | None = None
    nivel_formalidade: str | None = None
    linhas_editoriais: list[LinhaEditorial] = Field(default_factory=list)


class LogoOut(BaseModel):
    """Result of a logo upload — a storage key plus a fetchable URL."""

    storage_key: str
    url: str | None = None


# ── Cofre de Acessos ────────────────────────────────────────────────
class AcessoCreate(StrictHttpModel):
    cliente_id: str
    rotulo: str = Field(min_length=1, max_length=120)
    plataforma: str | None = Field(default=None, max_length=60)
    url: str | None = None
    usuario: str | None = Field(default=None, max_length=200)
    #: Encrypted before storage; never echoed back by any response model.
    senha: str | None = Field(default=None, max_length=500)
    observacoes: str | None = None


class AcessoUpdate(StrictHttpModel):
    rotulo: str | None = Field(default=None, min_length=1, max_length=120)
    plataforma: str | None = Field(default=None, max_length=60)
    url: str | None = None
    usuario: str | None = Field(default=None, max_length=200)
    senha: str | None = Field(default=None, max_length=500)
    observacoes: str | None = None


class AcessoOut(BaseModel):
    """A vault entry WITHOUT its password.

    There is no `senha` field and no `senha_cifrada` field, deliberately.
    Listing the vault must never carry credentials — not even ciphertext,
    which would hand an attacker an offline target. `tem_senha` is the only
    signal, and it is a boolean.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    cliente_id: str
    rotulo: str
    plataforma: str | None = None
    url: str | None = None
    usuario: str | None = None
    observacoes: str | None = None
    tem_senha: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class AcessosOut(BaseModel):
    """Vault entries for one client, plus whether the vault can accept a
    new password on THIS deploy.

    `itens` is empty exactly when the client has no entries yet — which is
    also true when `IGIG_COFRE_KEY` is unset, so `cofre_configurado` is not
    inferable from an empty list alone. Wrapping the list (rather than
    stamping the flag on every `AcessoOut`, the shape `IntegracaoStatus`
    uses) is what lets the setup screen know BEFORE a client has any
    entries at all, instead of only learning it from a failed save.
    """

    cofre_configurado: bool
    itens: list[AcessoOut] = Field(default_factory=list)


class SenhaRevelada(BaseModel):
    """The one response that ever carries a plaintext password."""

    senha: str
