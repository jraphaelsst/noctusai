"""Estruturas library -- request schemas (estruturas-contract.md sections 6.1 / 6.2).

Strict at the HTTP boundary (``extra="forbid"``): a misspelt field is a 422, never silently dropped. Responses are
plain dicts built by the service (the shapes of contract section 6.0 / FE ``src/types/estruturas.ts``), so the
admin-only keys can be stripped for a non-admin in ONE place.

NOTE: no ``from __future__ import annotations`` -- the routers wrap some handlers with slowapi's limiter, which makes
FastAPI resolve string annotations in slowapi's globals and turns body params into query params.
"""
import re
import uuid
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from noctusai_lib.api import StrictHttpModel

from app.modules.media_creation import estruturas_formatos as fmt

Formato = Literal["reels", "carrossel", "stories", "post"]
Objetivo = Literal["alcance", "autoridade", "conexao", "venda"]

#: The ``campo`` grammar of contract section 3.1 that an admin can CONFIRM (a field that carries provenance).
_CAMPO_RE = re.compile(
    r"^(formula_headline|formato|objetivos|bloco\.[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"\.(nome|tipo|tempo|instrucao))$"
)


def _objetivos_unicos(value: list[str]) -> list[str]:
    if len(set(value)) != len(value):
        raise ValueError("Objetivos repetidos.")
    return value


class BlocoIn(StrictHttpModel):
    """One block of a NEW Estrutura (``POST /estruturas``): position in the list = ``ordem``."""

    nome: str = Field(min_length=1, max_length=fmt.BLOCO_NOME_MAX)
    tipo_id: uuid.UUID
    tempo: Optional[str] = Field(default=None, max_length=fmt.BLOCO_TEMPO_MAX)
    instrucao: Optional[str] = Field(default=None, max_length=fmt.BLOCO_INSTRUCAO_MAX)
    nota: Optional[str] = Field(default=None, max_length=fmt.BLOCO_NOTA_MAX)
    repeticoes: int = Field(default=1, ge=1, le=fmt.BLOCO_REPETICOES_MAX)

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Informe o nome do bloco.")
        return v


class BlocoPut(BlocoIn):
    """One block of the full ordered replace (``PUT /estruturas/{id}/blocos``): ``id`` keeps identity + provenance."""

    id: Optional[uuid.UUID] = None


class EstruturaCreate(StrictHttpModel):
    perfil_id: uuid.UUID
    viral_id: Optional[uuid.UUID] = None
    formula_headline: str = Field(min_length=1, max_length=fmt.FORMULA_MAX)
    formato: Formato
    objetivos: list[Objetivo] = Field(min_length=1, max_length=fmt.MAX_OBJETIVOS)
    blocos: list[BlocoIn] = Field(min_length=fmt.BLOCOS_MIN, max_length=fmt.BLOCOS_MAX)
    status: Literal["rascunho", "ativa"] = "ativa"

    @field_validator("formula_headline")
    @classmethod
    def _formula(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Informe a fórmula da headline.")
        return v

    @field_validator("objetivos")
    @classmethod
    def _objetivos(cls, v: list[str]) -> list[str]:
        return _objetivos_unicos(v)


class EstruturaPatch(StrictHttpModel):
    """``PATCH /estruturas/{id}``: at least one field; status NEVER changes here (publicar / arquivar / restaurar)."""

    expected_versao: int = Field(ge=1)
    formula_headline: Optional[str] = Field(default=None, min_length=1, max_length=fmt.FORMULA_MAX)
    formato: Optional[Formato] = None
    objetivos: Optional[list[Objetivo]] = Field(default=None, min_length=1, max_length=fmt.MAX_OBJETIVOS)
    #: null clears the source video (the only nullable field of the patch).
    viral_id: Optional[uuid.UUID] = None

    @field_validator("formula_headline")
    @classmethod
    def _formula(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Informe a fórmula da headline.")
        return v

    @field_validator("objetivos")
    @classmethod
    def _objetivos(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        return v if v is None else _objetivos_unicos(v)

    @model_validator(mode="after")
    def _ao_menos_um_campo(self):
        sent = self.model_fields_set - {"expected_versao"}
        if not sent:
            raise ValueError("Informe ao menos um campo para alterar.")
        # null is meaningful only for viral_id (clears it); null on a NOT NULL column is a client error.
        nulos = sorted(k for k in sent if getattr(self, k) is None and k != "viral_id")
        if nulos:
            raise ValueError(f"Valor nulo não permitido: {', '.join(nulos)}")
        return self


class BlocosReplace(StrictHttpModel):
    expected_versao: int = Field(ge=1)
    blocos: list[BlocoPut] = Field(min_length=fmt.BLOCOS_MIN, max_length=fmt.BLOCOS_MAX)


class ConfirmarBody(StrictHttpModel):
    """``POST /estruturas/{id}/confirmar``: exactly one of ``campos`` / ``todos``."""

    expected_versao: int = Field(ge=1)
    campos: Optional[list[str]] = Field(default=None, min_length=1, max_length=500)
    todos: Optional[bool] = None

    @model_validator(mode="after")
    def _um_dos_dois(self):
        tem_campos = self.campos is not None
        tem_todos = self.todos is not None
        if tem_campos == tem_todos or (tem_todos and not self.todos):
            raise ValueError("Informe exatamente um: `campos` ou `todos: true`.")
        for campo in self.campos or []:
            if not _CAMPO_RE.match(campo):
                raise ValueError(f"Campo desconhecido: {campo[:80]!r}.")
        return self


class PublicarBody(StrictHttpModel):
    expected_versao: int = Field(ge=1)


class TipoBlocoCreate(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=fmt.TIPO_NOME_MAX)
    tempo_tipico: Optional[str] = Field(default=None, max_length=fmt.BLOCO_TEMPO_MAX)
    instrucao_referencia: str = Field(min_length=1, max_length=fmt.TIPO_INSTRUCAO_MAX)
    ativo: bool = True
    ordem: Optional[int] = Field(default=None, ge=1)

    @field_validator("nome", "instrucao_referencia")
    @classmethod
    def _nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Valor obrigatório.")
        return v


class TipoBlocoUpdate(StrictHttpModel):
    """``PUT /estruturas/tipos-bloco/{id}``: partial by ``fields_set`` (omitted = unchanged); ``nome`` and
    ``instrucao_referencia`` may be omitted but never blank; ``tempo_tipico: null`` clears the hint."""

    expected_versao: int = Field(ge=1)
    nome: Optional[str] = Field(default=None, min_length=1, max_length=fmt.TIPO_NOME_MAX)
    tempo_tipico: Optional[str] = Field(default=None, max_length=fmt.BLOCO_TEMPO_MAX)
    instrucao_referencia: Optional[str] = Field(default=None, min_length=1, max_length=fmt.TIPO_INSTRUCAO_MAX)
    ativo: Optional[bool] = None
    ordem: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _sem_nulos_indevidos(self):
        sent = self.model_fields_set - {"expected_versao"}
        if not sent:
            raise ValueError("Informe ao menos um campo para alterar.")
        nulos = sorted(k for k in sent if getattr(self, k) is None and k != "tempo_tipico")
        if nulos:
            raise ValueError(f"Valor nulo não permitido: {', '.join(nulos)}")
        for k in ("nome", "instrucao_referencia"):
            v = getattr(self, k)
            if k in sent and v is not None and not v.strip():
                raise ValueError(f"Valor obrigatório: {k}")
        return self


__all__ = [
    "BlocoIn",
    "BlocoPut",
    "BlocosReplace",
    "ConfirmarBody",
    "EstruturaCreate",
    "EstruturaPatch",
    "Formato",
    "Objetivo",
    "PublicarBody",
    "TipoBlocoCreate",
    "TipoBlocoUpdate",
]
