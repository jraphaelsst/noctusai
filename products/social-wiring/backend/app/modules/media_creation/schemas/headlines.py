"""Headlines (Geração, BE-4) -- request schemas, strict at the HTTP boundary.

Contract ``specs/geracao-contract.md`` section 4.4. ``LoteCreate`` is discriminated on ``origem``;
the response shapes mirror section 4.8 and are plain dicts built by ``headline_service``.

No ``from __future__ import annotations`` on purpose: these models are FastAPI body types, and a
stringified annotation under a slowapi-wrapped route turns a body into a query param (422
"body: Field required").
"""
import uuid
from typing import Annotated, Literal, Optional, Union

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

from app.modules.media_creation.geracao_taxonomias import TONS

Criatividade = Literal["essencial", "equilibrado", "explorador"]
Gatilho = Literal["recompensa", "misterio", "reconhecimento", "popularidade", "crenca", "autoridade", "disrupcao"]

#: A form's ``variaveis`` list is bounded by the variable taxonomy (40 slugs + the ``*`` wildcard).
MAX_VARIAVEIS = 45
MAX_ASSUNTO_CHARS = 300
MAX_TEXTO_CHARS = 1000


class RefPerfil(StrictHttpModel):
    tipo: Literal["perfil"]
    perfil_ids: list[uuid.UUID] = Field(min_length=1, max_length=2)


class RefFormato(StrictHttpModel):
    tipo: Literal["formato"]
    formato_ids: list[int] = Field(min_length=1, max_length=3)


class RefGatilho(StrictHttpModel):
    tipo: Literal["gatilho"]
    gatilhos: list[Gatilho] = Field(min_length=1, max_length=3)


Referencia = Annotated[Union[RefPerfil, RefFormato, RefGatilho], Field(discriminator="tipo")]
ReferenciaViral = Annotated[Union[RefPerfil, RefFormato], Field(discriminator="tipo")]


class LoteForm(StrictHttpModel):
    """``form_me`` / ``form_public``: headlines from the marca's research (Minha Pesquisa)."""

    marca_id: uuid.UUID
    post_id: Optional[uuid.UUID] = None
    origem: Literal["form_me", "form_public"]
    variaveis: list[str] = Field(min_length=1, max_length=MAX_VARIAVEIS)
    valores: Optional[dict[str, list[uuid.UUID]]] = None
    assunto: Optional[str] = Field(default=None, max_length=MAX_ASSUNTO_CHARS)
    referencia: Optional[Referencia] = None
    somente_pesquisa: bool = False
    criatividade: Criatividade = "equilibrado"


class LoteViral(StrictHttpModel):
    """``form_viral``: headlines from approved viral topics (Assuntos Virais)."""

    marca_id: uuid.UUID
    post_id: Optional[uuid.UUID] = None
    origem: Literal["form_viral"]
    assunto_ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=5)
    assunto_livre: Optional[str] = Field(default=None, max_length=MAX_ASSUNTO_CHARS)
    tom: Optional[Union[int, str]] = None
    referencia: Optional[ReferenciaViral] = None
    criatividade: Criatividade = "equilibrado"

    @field_validator("tom", mode="before")
    @classmethod
    def _tom_id_ou_slug(cls, v):
        """Accept the CoreStudio id (10..15) or the slug; stored as the id."""
        if v is None:
            return None
        ids = {10 + i: slug for i, (slug, _) in enumerate(TONS)}
        if isinstance(v, bool):
            raise ValueError("tom inválido")
        if isinstance(v, str) and v.strip().isdigit():
            v = int(v)
        if isinstance(v, int) and v in ids:
            return v
        if isinstance(v, str):
            for i, slug in ids.items():
                if slug == v.strip():
                    return i
        raise ValueError("tom inválido")

    @model_validator(mode="after")
    def _um_assunto(self) -> "LoteViral":
        if not self.assunto_ids and not (self.assunto_livre or "").strip():
            raise ValueError("Informe ao menos um assunto viral ou um assunto livre")
        return self


class LoteBiblioteca(StrictHttpModel):
    """``biblioteca``: one chosen viral from the Biblioteca wizard."""

    marca_id: uuid.UUID
    post_id: Optional[uuid.UUID] = None
    origem: Literal["biblioteca"]
    viral_id: uuid.UUID
    assunto_ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=5)
    assunto_livre: Optional[str] = Field(default=None, max_length=MAX_ASSUNTO_CHARS)


LoteCreate = Annotated[Union[LoteForm, LoteViral, LoteBiblioteca], Field(discriminator="origem")]


class HeadlineEdit(StrictHttpModel):
    texto: str = Field(min_length=1, max_length=MAX_TEXTO_CHARS)


class HeadlineCreate(StrictHttpModel):
    """Save a headline from the chat (or an own one): ``lote_id`` stays NULL."""

    marca_id: uuid.UUID
    texto: str = Field(min_length=1, max_length=MAX_TEXTO_CHARS)
    favoritar: Literal[True] = True


class IdsBody(StrictHttpModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SugestaoAgora(StrictHttpModel):
    marca_id: uuid.UUID


__all__ = [
    "Criatividade",
    "HeadlineCreate",
    "HeadlineEdit",
    "IdsBody",
    "LoteBiblioteca",
    "LoteCreate",
    "LoteForm",
    "LoteViral",
    "SugestaoAgora",
]
