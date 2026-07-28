"""
Stage-configuration routers — one per pipeline, both from the seed factory.

    /api/funil/etapas             — the Funil de Vendas stage editor
    /api/processos-venda/etapas   — the Processos de Venda stage editor

There is no handler code here on purpose. Everything is
`noctusai_lib.domain.pipeline.pipeline_stages_router`, mounted twice with two
`PipelineConfig`s. Adding a third board is another three lines in this file.

Both live UNDER their board's prefix rather than at a shared `/api/pipelines/…`
so a client that knows how to read a board also knows where to configure it,
with no separate registry to look up.
"""
from __future__ import annotations

from app.dependencies import get_current_user, get_org_id, get_user_client, log_action
from app.responses import success_response
from app.services.pipelines import PIPELINE_FUNIL, PIPELINE_PROCESSOS
from noctusai_lib.domain.pipeline import pipeline_stages_router


def _resolve_org_id(_db, user):
    """Seed signature is `(db, user)`; the ERP resolves org from the user alone.

    `get_org_id` reads `public.noctus_users` — the SAME row RLS's
    `current_org_id()` reads — so the app's notion of org cannot drift from the
    policy that will accept or reject the insert.
    """
    return get_org_id(user)


funil_stages_router = pipeline_stages_router(
    PIPELINE_FUNIL,
    get_current_user=get_current_user,
    get_user_client=get_user_client,
    resolve_org_id=_resolve_org_id,
    success_response=success_response,
    log_action=log_action,
    prefix="/api/funil/etapas",
    tags=["Funil — Etapas"],
)

processos_stages_router = pipeline_stages_router(
    PIPELINE_PROCESSOS,
    get_current_user=get_current_user,
    get_user_client=get_user_client,
    resolve_org_id=_resolve_org_id,
    success_response=success_response,
    log_action=log_action,
    prefix="/api/processos-venda/etapas",
    tags=["Processos de Venda — Etapas"],
)
