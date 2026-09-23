"""HTTP contracts for the e-mail slice (wave-2 contract, slice B)."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = ["SmtpIn", "SmtpTesteIn", "EnviarOrcamentoIn"]

_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def _email(valor: str) -> str:
    valor = valor.strip()
    if not _EMAIL.match(valor):
        raise ValueError(f"e-mail inválido: {valor!r}")
    return valor


def _lista(valor: object) -> list[str]:
    """Accept a single address, a comma/semicolon-separated string or a list."""
    if valor is None:
        return []
    itens = re.split(r"[;,]", valor) if isinstance(valor, str) else list(valor)  # type: ignore[arg-type]
    return [_email(str(i)) for i in itens if str(i).strip()]


class SmtpIn(StrictHttpModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1, max_length=320)
    #: Omitted ⇒ keep the stored password.
    password: str | None = Field(default=None, min_length=1, max_length=1000)
    security: Literal["ssl", "starttls"]
    from_email: str = Field(max_length=320)
    from_name: str | None = Field(default=None, max_length=200)

    @field_validator("from_email")
    @classmethod
    def _v_from(cls, valor: str) -> str:
        return _email(valor)


class SmtpTesteIn(StrictHttpModel):
    para: str = Field(max_length=320)

    @field_validator("para")
    @classmethod
    def _v_para(cls, valor: str) -> str:
        return _email(valor)


class EnviarOrcamentoIn(StrictHttpModel):
    #: Default: the lead's e-mail. A string ("a@x.com, b@y.com") or a list.
    para: list[str] | str | None = None
    cc: list[str] | str | None = None
    assunto: str | None = Field(default=None, max_length=300)
    mensagem: str | None = Field(default=None, max_length=10000)

    @field_validator("para", "cc", mode="after")
    @classmethod
    def _normalizar(cls, valor: object) -> list[str]:
        return _lista(valor)
