"""Inbound bodies for the per-party Certidões tab
(`certidoes_partes_router`). Contract: `projects/atendimento-partes-imoveis-
CONTRACT.md` §1.2-§1.4.

`StrictHttpModel` (`extra="forbid"`): an unknown field is a 422, never a
silent drop — a misspelled `tipos` would otherwise request EVERY certidão
(a billed call each) instead of the selected ones.
Response shapes are plain dicts (the card_hub house convention).
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from noctusai_lib.api import StrictHttpModel


class EmissaoBody(StrictHttpModel):
    """`POST …/certidoes/partes/{kind}/{alvo_id}/emissao`. `tipos=None` ⇒
    every AUTOMATED tipo applicable to the party (TJSP excluded)."""

    tipos: Optional[list[str]] = None
    atendimento_id: Optional[UUID] = None


class ReemitirBody(StrictHttpModel):
    """`POST …/certidoes/resultados/{resultado_id}/reemitir` — empty body."""


class CelulaBody(StrictHttpModel):
    """`POST …/certidoes/celulas` — ensure an uploadable cell."""

    kind: Literal["pessoa", "empresa"]
    alvo_id: UUID
    linha_chave: str
    atendimento_id: Optional[UUID] = None


__all__ = ["CelulaBody", "EmissaoBody", "ReemitirBody"]
