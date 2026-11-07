"""`mount_funnel(app, cfg, ...)` — one call mounts the whole funnel organ.

    {prefix}/etapa*      seed `pipeline_stages_router` (stage CRUD)
    {prefix}/cards/...   seed `card_hub_routers` (notes, tags, members, checklists,
                         documents, reminders, timeline, card) — only when `cfg.card_hub`
    {prefix}             `pipeline_board_router` (board, cards, moves, loss, actions)

ORDER MATTERS and is why this is one function: the card hub's collection router
owns the literal `GET {prefix}/cards/tags`, which `GET {prefix}/cards/{card_id}`
would swallow if the board router were included first.

Both inner routers receive the SAME tenancy-scoped context, so the stage editor
cannot read a wider tenant than the board does (`stages.list_stages(org_id=None)`
reads every tenant; `scope()` never lets a None org through).
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI

from noctusai_lib.domain.card_hub import CardHubContext, card_hub_routers
from noctusai_lib.domain.pipeline.router import PipelineContext, pipeline_stages_router

from . import service as svc
from .config import FunnelConfig
from .router import pipeline_board_router


def mount_funnel(
    app: FastAPI,
    cfg: FunnelConfig,
    *,
    prefix: str,
    auth_dependency: Callable[..., Any],
    resolve_context: Callable[[Any], PipelineContext],
    success_response: Callable[[Any], Any],
    log_action: Callable[..., Any] | None = None,
    require_stage_admin: Callable[..., Any] | None = None,
    require_card_write: Callable[..., Any] | None = None,
    get_db: Callable[..., Any] | None = None,
    get_storage: Callable[..., Any] | None = None,
    documento_upload_hook: Callable[..., Any] | None = None,
    documento_delete_hook: Callable[..., Any] | None = None,
) -> None:
    """Mount stages + (optional) card hub + board on `app` under `prefix`.

    `get_db` / `get_storage` are required exactly when `cfg.card_hub` is set
    (they are the card hub's own DI seams).
    """
    if not prefix.startswith("/") or prefix.endswith("/"):
        raise ValueError(f"mount_funnel prefix must look like '/api/x', got {prefix!r}")

    def scoped(auth: Any) -> PipelineContext:
        return svc.scope(cfg, resolve_context(auth))

    app.include_router(
        pipeline_stages_router(
            cfg.pipeline,
            auth_dependency=auth_dependency,
            resolve_context=scoped,
            success_response=success_response,
            log_action=log_action,
            prefix=f"{prefix}/etapas",
            require_stage_admin=require_stage_admin,
        )
    )

    if cfg.card_hub is not None:
        if get_db is None or get_storage is None:
            raise ValueError("mount_funnel: get_db and get_storage are required when cfg.card_hub is set")

        def hub_context(auth: Any, db: Any) -> CardHubContext:
            ctx = scoped(auth)
            return CardHubContext(db=db, org_id=ctx.org_id, user_id=ctx.user_id)

        collection, entity = card_hub_routers(
            cfg.card_hub,
            auth_dependency=auth_dependency,
            resolve_context=hub_context,
            get_db=get_db,
            get_storage=get_storage,
            prefix=f"{prefix}/cards",
            documento_upload_hook=documento_upload_hook,
            documento_delete_hook=documento_delete_hook,
        )
        app.include_router(collection)
        app.include_router(entity)

    app.include_router(
        pipeline_board_router(
            cfg,
            auth_dependency=auth_dependency,
            resolve_context=resolve_context,
            success_response=success_response,
            log_action=log_action,
            require_card_write=require_card_write,
            prefix=prefix,
        )
    )


__all__ = ["mount_funnel"]
