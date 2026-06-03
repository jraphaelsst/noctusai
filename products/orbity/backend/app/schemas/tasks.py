"""
Pydantic schemas for the /api/tasks endpoints.

StrictHttpModel (extra="forbid") on all inbound models.
Outbound models use extra="ignore" (DB may return extra columns).
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

TaskStatus = Literal["todo", "doing", "done", "canceled"]
TaskPriority = Literal["low", "med", "high"]


# ---------------------------------------------------------------------------
# Tasks inbound
# ---------------------------------------------------------------------------

class TaskCreate(StrictHttpModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    assignee_user_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "med"
    due_date: Optional[str] = None   # ISO 8601 date string (YYYY-MM-DD)
    completed_at: Optional[str] = None   # ISO 8601 datetime string


class TaskUpdate(StrictHttpModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    assignee_user_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[str] = None
    completed_at: Optional[str] = None


class TaskStatusUpdate(StrictHttpModel):
    status: TaskStatus


# ---------------------------------------------------------------------------
# Routines inbound
# ---------------------------------------------------------------------------

RoutineCadence = Literal["daily", "weekly", "monthly"]


class RoutineCreate(StrictHttpModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    cadence: RoutineCadence
    next_run: str = Field(..., description="ISO 8601 date (YYYY-MM-DD)")
    active: bool = True


class RoutineUpdate(StrictHttpModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=5000)
    cadence: Optional[RoutineCadence] = None
    next_run: Optional[str] = None
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Outbound (extra="ignore" — DB can return extra columns safely)
# ---------------------------------------------------------------------------

class TaskOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    title: str
    description: Optional[str] = None
    assignee_user_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    status: str
    priority: str
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    # DB always provides timestamps; Optional so mock responses (no timestamps)
    # don't fail serialization in the test environment.
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"extra": "ignore"}


class RoutineOut(StrictHttpModel):
    id: UUID
    org_id: UUID
    title: str
    description: Optional[str] = None
    cadence: str
    next_run: str
    active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"extra": "ignore"}
