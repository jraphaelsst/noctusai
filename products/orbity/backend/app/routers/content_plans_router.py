"""
Content plans router — monthly plans, ordered items, tasks from items,
promote-to-post and AI item generation (preview).

Auth boundary: every endpoint is Depends(get_current_user_org) -> strict 401.

  GET    /api/content/plans                                  list plans (+items)
  POST   /api/content/plans                                  create plan (+optional items) -> 201
  GET    /api/content/plans/{id}                             plan detail (+items)
  PATCH  /api/content/plans/{id}                             update plan
  DELETE /api/content/plans/{id}                             delete plan (cascades items)

  POST   /api/content/plans/{id}/items                       append items -> 201
  PUT    /api/content/plans/{id}/items/order                 reorder items
  PATCH  /api/content/plans/{id}/items/{item_id}             update item
  DELETE /api/content/plans/{id}/items/{item_id}             delete (task? discard : hard delete)
  POST   /api/content/plans/{id}/items/{item_id}/post        promote item -> draft content_post

  POST   /api/content/plans/{id}/tasks                       create tasks from items
  POST   /api/content/plans/{id}/ai-items                    AI preview (nothing persisted)

AI errors are honest: not configured -> 503, provider failure -> 502,
invalid model output after one retry -> 502. Never fake output.
"""
import logging
from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.dependencies import coerce_org_uuid, get_current_user_org, get_user_client
from app.schemas.content_plans import (
    AIGenerateOut,
    AIGenerateParams,
    PlanCreate,
    PlanItemDeleteOut,
    PlanItemOut,
    PlanItemsAppend,
    PlanItemsReorder,
    PlanItemUpdate,
    PlanOut,
    PlanTasksCreate,
    PlanTasksOut,
    PlanUpdate,
)
from app.schemas.social_content import PostOut
from app.services.content_plan_ai_service import (
    ContentPlanAIInvalidOutput,
    ContentPlanAINotConfigured,
    generate_plan_items,
)
from app.rate_limit import limiter
from app.services.content_plans_service import ContentPlansService, PlanReferenceError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Content Plans"])


def _svc(token: str, org_id: UUID) -> ContentPlansService:
    return ContentPlansService(get_user_client(token), org_id=org_id)


@contextmanager
def _guard(op: str, org_id: UUID, failure: str) -> Iterator[None]:
    """Map service errors: bad reference -> 422, anything else logged -> 502."""
    try:
        yield
    except HTTPException:
        raise
    except PlanReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("content_plans.%s failed org=%s", op, org_id)
        raise HTTPException(status_code=502, detail=failure)


def _plan_or_404(svc: ContentPlansService, plan_id: str) -> dict:
    plan = svc.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Planejamento não encontrado")
    return plan


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@router.get("/api/content/plans", status_code=status.HTTP_200_OK)
def list_plans(
    client_id: str | None = Query(default=None),
    month: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("list_plans", org_id, "Falha ao listar planejamentos"):
        return _svc(token, org_id).list_plans(
            client_id=client_id, month=month, status=status_filter,
            page=page, page_size=page_size,
        )


@router.post("/api/content/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, auth: tuple = Depends(get_current_user_org)) -> PlanOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("create_plan", org_id, "Falha ao criar planejamento"):
        row = _svc(token, org_id).create_plan(payload.model_dump(mode="json", exclude_none=True))
    return PlanOut(**row)


@router.get("/api/content/plans/{plan_id}", response_model=PlanOut, status_code=status.HTTP_200_OK)
def get_plan(plan_id: str, auth: tuple = Depends(get_current_user_org)) -> PlanOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("get_plan", org_id, "Falha ao buscar planejamento"):
        plan = _plan_or_404(_svc(token, org_id), plan_id)
    return PlanOut(**plan)


@router.patch("/api/content/plans/{plan_id}", response_model=PlanOut, status_code=status.HTTP_200_OK)
def update_plan(
    plan_id: str, payload: PlanUpdate, auth: tuple = Depends(get_current_user_org)
) -> PlanOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    with _guard("update_plan", org_id, "Falha ao atualizar planejamento"):
        row = _svc(token, org_id).update_plan(plan_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Planejamento não encontrado")
    return PlanOut(**row)


@router.delete("/api/content/plans/{plan_id}", status_code=status.HTTP_200_OK)
def delete_plan(plan_id: str, auth: tuple = Depends(get_current_user_org)) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("delete_plan", org_id, "Falha ao remover planejamento"):
        deleted = _svc(token, org_id).delete_plan(plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Planejamento não encontrado")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@router.post(
    "/api/content/plans/{plan_id}/items",
    response_model=list[PlanItemOut],
    status_code=status.HTTP_201_CREATED,
)
def append_items(
    plan_id: str, payload: PlanItemsAppend, auth: tuple = Depends(get_current_user_org)
) -> list[PlanItemOut]:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("append_items", org_id, "Falha ao adicionar conteúdos"):
        svc = _svc(token, org_id)
        _plan_or_404(svc, plan_id)
        rows = svc.append_items(
            plan_id, [i.model_dump(mode="json", exclude_none=True) for i in payload.items]
        )
    return [PlanItemOut(**r) for r in rows]


@router.put(
    "/api/content/plans/{plan_id}/items/order",
    response_model=list[PlanItemOut],
    status_code=status.HTTP_200_OK,
)
def reorder_items(
    plan_id: str, payload: PlanItemsReorder, auth: tuple = Depends(get_current_user_org)
) -> list[PlanItemOut]:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("reorder_items", org_id, "Falha ao reordenar conteúdos"):
        svc = _svc(token, org_id)
        _plan_or_404(svc, plan_id)
        rows = svc.reorder_items(plan_id, [str(i) for i in payload.ids])
    return [PlanItemOut(**r) for r in rows]


@router.patch(
    "/api/content/plans/{plan_id}/items/{item_id}",
    response_model=PlanItemOut,
    status_code=status.HTTP_200_OK,
)
def update_item(
    plan_id: str, item_id: str, payload: PlanItemUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> PlanItemOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    with _guard("update_item", org_id, "Falha ao atualizar conteúdo"):
        row = _svc(token, org_id).update_item(plan_id, item_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    return PlanItemOut(**row)


@router.delete(
    "/api/content/plans/{plan_id}/items/{item_id}",
    response_model=PlanItemDeleteOut,
    status_code=status.HTTP_200_OK,
)
def delete_item(
    plan_id: str, item_id: str, auth: tuple = Depends(get_current_user_org)
) -> PlanItemDeleteOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("delete_item", org_id, "Falha ao remover conteúdo"):
        result = _svc(token, org_id).delete_item(plan_id, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    return PlanItemDeleteOut(**result)


@router.post(
    "/api/content/plans/{plan_id}/items/{item_id}/post",
    response_model=PostOut,
    status_code=status.HTTP_201_CREATED,
)
def promote_item_to_post(
    plan_id: str, item_id: str, auth: tuple = Depends(get_current_user_org)
) -> PostOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("promote_item", org_id, "Falha ao criar post"):
        svc = _svc(token, org_id)
        plan = _plan_or_404(svc, plan_id)
        try:
            result = svc.promote_to_post(plan, item_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    return PostOut(**result["post"])


# ---------------------------------------------------------------------------
# Tasks from items
# ---------------------------------------------------------------------------

@router.post(
    "/api/content/plans/{plan_id}/tasks",
    response_model=PlanTasksOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tasks_from_items(
    plan_id: str, payload: PlanTasksCreate, auth: tuple = Depends(get_current_user_org)
) -> PlanTasksOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("create_tasks", org_id, "Falha ao criar tarefas"):
        svc = _svc(token, org_id)
        plan = _plan_or_404(svc, plan_id)
        result = svc.create_tasks(
            plan,
            [str(i) for i in payload.item_ids],
            str(payload.assignee_user_id) if payload.assignee_user_id else None,
        )
    return PlanTasksOut(**result)


# ---------------------------------------------------------------------------
# AI generation (preview only)
# ---------------------------------------------------------------------------

@router.post(
    "/api/content/plans/{plan_id}/ai-items",
    response_model=AIGenerateOut,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute;60/hour")
async def generate_items_with_ai(
    request: Request,  # required positionally by @limiter.limit (slowapi)
    plan_id: str,
    payload: AIGenerateParams,
    auth: tuple = Depends(get_current_user_org),
) -> AIGenerateOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    with _guard("ai_items_load", org_id, "Falha ao carregar o planejamento"):
        svc = _svc(token, org_id)
        plan = _plan_or_404(svc, plan_id)
        client_name = None
        if plan.get("client_id"):
            rows = (
                get_user_client(token).table("clients").select("name")
                .eq("org_id", str(org_id)).eq("id", str(plan["client_id"])).execute().data
            ) or []
            client_name = rows[0].get("name") if rows else None
    try:
        items = await generate_plan_items(
            payload, plan=plan, client_name=client_name,
            existing_items=[i for i in plan["items"] if i.get("status") != "discarded"],
            org_id=str(org_id),
        )
    except ContentPlanAINotConfigured:
        raise HTTPException(
            status_code=503,
            detail="IA não configurada. Cadastre a chave do provedor de IA em Configurações > Chaves de API.",
        )
    except ContentPlanAIInvalidOutput:
        raise HTTPException(
            status_code=502,
            detail="A IA retornou um resultado fora do combinado. Tente novamente.",
        )
    return AIGenerateOut(items=items)
