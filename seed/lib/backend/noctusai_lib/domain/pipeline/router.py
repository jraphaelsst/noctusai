"""`pipeline_stages_router(...)` — mountable CRUD for user-editable stages.

A factory (mirroring `noctusai_lib.security.oauth.oauth_router` and
`google_scopes_router`) because the seed cannot know the product's auth
dependency, its supabase-client accessor, or its audit-log sink. Everything
product-specific is injected; everything pipeline-specific arrives in the
`PipelineConfig`. Mounting it twice with two configs is what gives the ERP a
Funil stage editor and a Processos stage editor with no second implementation.

Routes (under the caller's chosen prefix):
    GET    /                    list stages, ordered
    POST   /                    create
    PATCH  /{stage_id}          edit (this is what "rename" is)
    DELETE /{stage_id}          delete, optionally reassigning cards
    POST   /reordenar           rewrite the full order
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.exceptions import ValidationError_

from .config import PipelineConfig
from .stages import (
    STAGE_COLORS,
    STAGE_ROLES,
    create_stage,
    delete_stage,
    list_stages,
    reorder_stages,
    update_stage,
)


class StageCreate(StrictHttpModel):
    label: str = Field(..., min_length=1, max_length=60)
    cor: str | None = None
    posicao: int | None = None
    papel: str | None = None
    slug: str | None = None


class StageUpdate(StrictHttpModel):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    cor: str | None = None
    posicao: int | None = None
    # `papel` is explicitly nullable: clearing a role is how you hand it to a
    # different stage, so "not sent" and "sent as null" must differ. Callers
    # send `papel: null` to clear.
    papel: str | None = None
    ativo: bool | None = None


class StageReorder(StrictHttpModel):
    ordem: list[str] = Field(..., min_length=1)


def pipeline_stages_router(
    cfg: PipelineConfig,
    *,
    get_current_user: Callable[..., Any],
    get_user_client: Callable[[str], Any],
    resolve_org_id: Callable[[Any, Any], str | None],
    success_response: Callable[[Any], Any],
    log_action: Callable[..., Any] | None = None,
    prefix: str = "",
    tags: list[str] | None = None,
) -> APIRouter:
    """Build a stage-CRUD router for one pipeline.

    Args:
        cfg: The pipeline these stages belong to.
        get_current_user: Product auth dependency returning `(user, token)`.
        get_user_client: Product factory turning a token into a scoped client.
        resolve_org_id: `(db, user) -> org_id`. Creating a stage needs the
            caller's org, which RLS enforces but does not supply.
        success_response: Product envelope wrapper.
        log_action: Optional audit-log sink.
        prefix: Router prefix.
        tags: OpenAPI tags.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["pipeline-stages"])

    @router.get("")
    async def listar_etapas(auth=Depends(get_current_user)):
        """Stage definitions for this pipeline, in display order."""
        _user, token = auth
        db = get_user_client(token)
        stages = list_stages(db, cfg, incluir_inativas=True)
        return success_response(stages)

    @router.get("/opcoes")
    async def opcoes(auth=Depends(get_current_user)):
        """The valid colour tokens + roles, so the UI never guesses them.

        Serving these keeps the editor's dropdowns in step with the CHECK
        constraints; a hardcoded frontend list is how you get a 400 the user
        cannot act on.
        """
        return success_response({"cores": list(STAGE_COLORS), "papeis": list(STAGE_ROLES)})

    @router.post("")
    async def criar_etapa(body: StageCreate, auth=Depends(get_current_user)):
        user, token = auth
        db = get_user_client(token)
        org_id = resolve_org_id(db, user)
        if not org_id:
            raise ValidationError_(
                "Não foi possível identificar a organização do usuário. "
                "Etapas são configuradas por organização."
            )
        stage = create_stage(
            db, cfg, body.model_dump(exclude_unset=True), org_id=str(org_id)
        )
        if log_action:
            log_action(
                user.id, "criar", "pipeline_stage", stage["id"],
                f"Criou a etapa '{stage['label']}' no funil {cfg.pipeline}",
                {"pipeline": cfg.pipeline, "slug": stage.get("slug")},
            )
        return success_response(stage)

    @router.patch("/{stage_id}")
    async def editar_etapa(stage_id: str, body: StageUpdate, auth=Depends(get_current_user)):
        """Edit a stage. Renaming here re-labels every card that references it."""
        user, token = auth
        db = get_user_client(token)
        stage = update_stage(db, cfg, stage_id, body.model_dump(exclude_unset=True))
        if log_action:
            log_action(
                user.id, "editar", "pipeline_stage", stage_id,
                f"Editou a etapa '{stage['label']}' no funil {cfg.pipeline}",
                {"pipeline": cfg.pipeline, "campos": list(body.model_dump(exclude_unset=True))},
            )
        return success_response(stage)

    @router.delete("/{stage_id}")
    async def excluir_etapa(
        stage_id: str,
        reassign_to: str | None = None,
        auth=Depends(get_current_user),
    ):
        user, token = auth
        db = get_user_client(token)
        result = delete_stage(db, cfg, stage_id, reassign_to=reassign_to)
        if log_action:
            log_action(
                user.id, "excluir", "pipeline_stage", stage_id,
                f"Excluiu uma etapa do funil {cfg.pipeline}",
                {"pipeline": cfg.pipeline, **result},
            )
        return success_response(result)

    @router.post("/reordenar")
    async def reordenar_etapas(body: StageReorder, auth=Depends(get_current_user)):
        user, token = auth
        db = get_user_client(token)
        stages = reorder_stages(db, cfg, body.ordem)
        if log_action:
            log_action(
                user.id, "editar", "pipeline_stage", None,
                f"Reordenou as etapas do funil {cfg.pipeline}",
                {"pipeline": cfg.pipeline, "ordem": body.ordem},
            )
        return success_response(stages)

    return router
