"""
Tasks router — tasks CRUD, status patch, and routines CRUD + on-demand spawn.

Auth boundary:
  All /api/tasks/* and /api/routines/* → Depends(get_current_user_org) → strict 401.

Endpoints:
  GET    /api/tasks                      paginated task list (filter: status, priority, assignee, client)
  POST   /api/tasks                      create task → 201
  GET    /api/tasks/{id}                 task detail
  PATCH  /api/tasks/{id}                 update task
  DELETE /api/tasks/{id}                 delete task
  PATCH  /api/tasks/{id}/status          quick status update

  GET    /api/routines                   list routines (filter: active_only)
  POST   /api/routines                   create routine → 201
  GET    /api/routines/{id}              routine detail
  PATCH  /api/routines/{id}              update routine
  DELETE /api/routines/{id}              delete routine
  POST   /api/routines/run-due           spawn tasks for all due routines → 200
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_client,
)
from app.schemas.tasks import (
    RoutineCreate,
    RoutineOut,
    RoutineUpdate,
    TaskCreate,
    TaskOut,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.tasks_service import TasksService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tasks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(token: str, org_id: UUID) -> TasksService:
    return TasksService(get_user_client(token), org_id=org_id)


# ---------------------------------------------------------------------------
# Tasks CRUD
# ---------------------------------------------------------------------------

@router.get("/api/tasks", status_code=status.HTTP_200_OK)
async def list_tasks(
    task_status: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    assignee_user_id: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_tasks(
            status=task_status,
            priority=priority,
            assignee_user_id=assignee_user_id,
            client_id=client_id,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("tasks.list_tasks failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar tarefas")


@router.post(
    "/api/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    payload: TaskCreate,
    auth: tuple = Depends(get_current_user_org),
) -> TaskOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_task(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("tasks.create_task failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar tarefa")
    return TaskOut(**row)


@router.get(
    "/api/tasks/{task_id}",
    response_model=TaskOut,
    status_code=status.HTTP_200_OK,
)
async def get_task(
    task_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> TaskOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_task(task_id)
    except Exception:
        logger.exception("tasks.get_task failed org=%s id=%s", org_id, task_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar tarefa")
    if not row:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return TaskOut(**row)


@router.patch(
    "/api/tasks/{task_id}",
    response_model=TaskOut,
    status_code=status.HTTP_200_OK,
)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> TaskOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_task(task_id, data)
    except Exception:
        logger.exception("tasks.update_task failed org=%s id=%s", org_id, task_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar tarefa")
    if not row:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return TaskOut(**row)


@router.delete("/api/tasks/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
    task_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_task(task_id)
    except Exception:
        logger.exception("tasks.delete_task failed org=%s id=%s", org_id, task_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar tarefa")
    if not ok:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return {"ok": True, "id": task_id}


@router.patch(
    "/api/tasks/{task_id}/status",
    response_model=TaskOut,
    status_code=status.HTTP_200_OK,
)
async def update_task_status(
    task_id: str,
    payload: TaskStatusUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> TaskOut:
    """Quick status transition — sets completed_at when status becomes 'done'."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    update_data: dict = {"status": payload.status}
    if payload.status == "done":
        from datetime import datetime, timezone
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        row = _svc(token, org_id).update_task(task_id, update_data)
    except Exception:
        logger.exception("tasks.update_task_status failed org=%s id=%s", org_id, task_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar status")
    if not row:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return TaskOut(**row)


# ---------------------------------------------------------------------------
# Routines CRUD + spawn
# ---------------------------------------------------------------------------

@router.get("/api/routines", status_code=status.HTTP_200_OK)
async def list_routines(
    active_only: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_routines(active_only=active_only)
    except Exception:
        logger.exception("tasks.list_routines failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar rotinas")


@router.post(
    "/api/routines",
    response_model=RoutineOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_routine(
    payload: RoutineCreate,
    auth: tuple = Depends(get_current_user_org),
) -> RoutineOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_routine(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("tasks.create_routine failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar rotina")
    return RoutineOut(**row)


@router.get(
    "/api/routines/{routine_id}",
    response_model=RoutineOut,
    status_code=status.HTTP_200_OK,
)
async def get_routine(
    routine_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> RoutineOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_routine(routine_id)
    except Exception:
        logger.exception("tasks.get_routine failed org=%s id=%s", org_id, routine_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar rotina")
    if not row:
        raise HTTPException(status_code=404, detail="Rotina não encontrada")
    return RoutineOut(**row)


@router.patch(
    "/api/routines/{routine_id}",
    response_model=RoutineOut,
    status_code=status.HTTP_200_OK,
)
async def update_routine(
    routine_id: str,
    payload: RoutineUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> RoutineOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_routine(routine_id, data)
    except Exception:
        logger.exception("tasks.update_routine failed org=%s id=%s", org_id, routine_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar rotina")
    if not row:
        raise HTTPException(status_code=404, detail="Rotina não encontrada")
    return RoutineOut(**row)


@router.delete("/api/routines/{routine_id}", status_code=status.HTTP_200_OK)
async def delete_routine(
    routine_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_routine(routine_id)
    except Exception:
        logger.exception("tasks.delete_routine failed org=%s id=%s", org_id, routine_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar rotina")
    if not ok:
        raise HTTPException(status_code=404, detail="Rotina não encontrada")
    return {"ok": True, "id": routine_id}


@router.post("/api/routines/run-due", status_code=status.HTTP_200_OK)
async def run_due_routines(
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    """On-demand: spawn tasks for all active routines due today or earlier.

    Returns the list of spawned task rows. Intended for scheduled triggers
    or admin-initiated runs. Advances each routine's next_run after spawning.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        spawned = _svc(token, org_id).run_due_routines()
    except Exception:
        logger.exception("tasks.run_due_routines failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao executar rotinas")
    return {"spawned": len(spawned), "tasks": spawned}
