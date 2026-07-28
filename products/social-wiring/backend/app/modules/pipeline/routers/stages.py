"""Stage-configuration routers — one per pipeline, both from the seed factory.

    /api/funil/etapas             — Funil de Vendas stage editor
    /api/processos-venda/etapas   — Processos de Venda stage editor

No handler code here on purpose: it is
`noctusai_lib.domain.pipeline.pipeline_stages_router` mounted twice with two
`PipelineConfig`s, exactly as erp-imobiliario does it. A third board is another
three lines.
"""
from __future__ import annotations

from noctusai_lib.domain.pipeline import pipeline_stages_router
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_current_user_org_unified
from app.modules.pipeline.configs import PIPELINE_FUNIL, PIPELINE_PROCESSOS
from app.modules.pipeline.deps import pipeline_context

funil_stages_router = pipeline_stages_router(
    PIPELINE_FUNIL,
    auth_dependency=get_current_user_org_unified,
    resolve_context=pipeline_context,
    success_response=success_response,
    prefix="/api/funil/etapas",
    tags=["funil-etapas"],
)

processos_stages_router = pipeline_stages_router(
    PIPELINE_PROCESSOS,
    auth_dependency=get_current_user_org_unified,
    resolve_context=pipeline_context,
    success_response=success_response,
    prefix="/api/processos-venda/etapas",
    tags=["processos-etapas"],
)
