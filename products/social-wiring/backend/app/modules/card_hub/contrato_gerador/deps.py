"""DI seams for the contract generator — production values here, tests override
through `app.dependency_overrides` (never a patch)."""
from __future__ import annotations

from noctusai_lib.integrations.docx_render import DocxRenderAdapter, get_docx_render_adapter

from app.modules.card_hub.contrato_gerador.dados import Complementos
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO, Politica


def get_complementos_contrato() -> Complementos:
    """Spec §6.1 fields the system does not hold yet: empty, so every switch
    that needs one reports it as `faltando`.
    NOC-REMEDIATE[contrato-f6-campos-missing]: read these from real storage
    once the F6 data-model slice lands — 2026-09-14"""
    return Complementos()


def get_politica_contrato() -> Politica:
    return POLITICA_PADRAO


def get_contrato_docx_adapter() -> DocxRenderAdapter:
    return get_docx_render_adapter(real=True)


__all__ = [
    "get_complementos_contrato",
    "get_contrato_docx_adapter",
    "get_politica_contrato",
]
