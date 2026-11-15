"""Estruturas library -- load (importação) request schema (estruturas-contract.md section 6.3).

Strict at the HTTP boundary (``extra="forbid"``). ``conteudo`` is the PARSED JSON document of one of the two
vendor-shaped files (its shape is validated by the loader, row by row, never by pydantic: a bad row is a coded ignore,
not a 422 for the whole file). Responses are the plain ``ImportacaoRelatorio`` dict built by the service.

NOTE: no ``from __future__ import annotations`` (slowapi-safe body params, same as the sibling schemas).
"""
from typing import Any, Optional, Union

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class ImportacaoCreate(StrictHttpModel):
    # a str, not a Literal: a file of another source is a CODED 422 `arquivo_invalido` / `fonte_nao_suportada` from the loader
    fonte: str = Field(min_length=1, max_length=40)
    conteudo: Union[list[Any], dict[str, Any]]
    arquivo_nome: Optional[str] = Field(default=None, max_length=300)
    dry_run: bool = True


__all__ = ["ImportacaoCreate"]
