"""DI seams for the contract generator — production values here, tests override
through `app.dependency_overrides` (never a patch).

🔴 `get_complementos_contrato` is GONE, and its absence is the point. It
existed to hand the generator an EMPTY `Complementos()` — spec §6.1's fields
had no storage, so every switch needing one reported `faltando` and no contract
could ever be generated. Migrations 114-118 gave all of them real storage, so
`carregador` now READS them off the entities that own them (see `dados`'s
module docstring). A seam whose only job was to supply nothing is not a seam.
"""
from __future__ import annotations

from noctusai_lib.integrations.docx_render import DocxRenderAdapter, get_docx_render_adapter

from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO, Politica


def get_politica_contrato() -> Politica:
    return POLITICA_PADRAO


def get_contrato_docx_adapter() -> DocxRenderAdapter:
    return get_docx_render_adapter(real=True)


__all__ = [
    "get_contrato_docx_adapter",
    "get_politica_contrato",
]
