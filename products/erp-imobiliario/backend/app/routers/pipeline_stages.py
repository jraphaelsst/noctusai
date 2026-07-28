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
from noctusai_lib.domain.pipeline import PipelineContext, pipeline_stages_router


def _context(auth) -> PipelineContext:
    """Map this product's `(user, token)` auth to the seed's context triple.

    The client is RLS-scoped (`get_user_client(token)`), so `org_id` is passed
    only for the INSERT path, which needs a value RLS can check but cannot
    supply. `get_org_id` reads `public.noctus_users` — the SAME row
    `current_org_id()` reads — so the app's notion of org cannot drift from the
    policy that will accept or reject the write.
    """
    user, token = auth
    return PipelineContext(
        db=get_user_client(token), org_id=get_org_id(user), user_id=user.id
    )


funil_stages_router = pipeline_stages_router(
    PIPELINE_FUNIL,
    auth_dependency=get_current_user,
    resolve_context=_context,
    success_response=success_response,
    log_action=log_action,
    prefix="/api/funil/etapas",
    tags=["Funil — Etapas"],
)

processos_stages_router = pipeline_stages_router(
    PIPELINE_PROCESSOS,
    auth_dependency=get_current_user,
    resolve_context=_context,
    success_response=success_response,
    log_action=log_action,
    prefix="/api/processos-venda/etapas",
    tags=["Processos de Venda — Etapas"],
)
