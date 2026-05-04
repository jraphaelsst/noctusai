"""Admin CRUD on `media_scheduling.authorized_users`.

Frontend contract (Phase 5 hooks `useAuthorizedUsers.ts`):
  - GET    /api/authorized-users           → `{data: AuthorizedUser[]}`
  - POST   /api/authorized-users           → created row
  - GET    /api/authorized-users/{id}      → AuthorizedUser
  - PATCH  /api/authorized-users/{id}      → updated row
  - DELETE /api/authorized-users/{id}      → `{ok: true}`

Wire-shape note: the frontend hook surfaces `is_active` (camelCase-ish
boolean alias of the DB column `active`) and an optional `notes` field
that does NOT exist in the schema (`002_initial_schema.sql`). We honor
the active alias both directions; `notes` is silently dropped (forwarded
as a no-op attribute the DB ignores). Surface in Phase 3 improvements
so the schema/hook drift gets resolved at Phase 6 verification.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.database import get_supabase_client
from app.dependencies import get_current_user
from app.services.lid_auth import normalize_phone_number

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/authorized-users", tags=["AuthorizedUsers"])


class AuthorizedUserCreate(BaseModel):
    """POST shape — frontend may send is_active, name, phone_number, role,
    email, optional notes. `notes` not in schema → dropped (see module
    docstring)."""

    name: str = Field(..., min_length=1, max_length=120)
    phone_number: str = Field(..., min_length=1, max_length=32)
    role: str = Field(default="real_estate_agent", max_length=40)
    email: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)


class AuthorizedUserUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


def _wire(row: dict[str, Any]) -> dict[str, Any]:
    """Translate DB row → wire-shape (active → is_active for frontend)."""
    out = dict(row)
    if "active" in out:
        out["is_active"] = out.pop("active")
    return out


def _persistable(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate wire-shape → DB shape (is_active → active; normalize phone)."""
    out: dict[str, Any] = {}
    if "name" in payload and payload["name"] is not None:
        out["name"] = payload["name"]
    if "role" in payload and payload["role"] is not None:
        out["role"] = payload["role"]
    if "email" in payload:
        out["email"] = payload["email"]
    if "phone_number" in payload and payload["phone_number"] is not None:
        out["phone_number"] = normalize_phone_number(payload["phone_number"])
    if "is_active" in payload and payload["is_active"] is not None:
        out["active"] = bool(payload["is_active"])
    return out


@router.get("")
async def list_authorized_users(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    await get_current_user(authorization)
    db = get_supabase_client()
    result = (
        db.table("authorized_users")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    rows = [_wire(r) for r in (result.data or [])]
    return {"data": rows}


@router.post("")
async def create_authorized_user(
    body: AuthorizedUserCreate,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    await get_current_user(authorization)
    db = get_supabase_client()
    payload = _persistable(body.model_dump(exclude_unset=True))
    if not payload.get("phone_number"):
        raise HTTPException(status_code=400, detail="phone_number is required")
    try:
        result = db.table("authorized_users").insert(payload).execute()
    except Exception as exc:
        logger.warning("authorized_users insert failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=400, detail="Insert returned no row")
    return _wire(rows[0])


@router.get("/{user_id}")
async def get_authorized_user(
    user_id: str,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    await get_current_user(authorization)
    db = get_supabase_client()
    result = (
        db.table("authorized_users")
        .select("*")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Authorized user not found")
    return _wire(rows[0])


@router.patch("/{user_id}")
async def update_authorized_user(
    user_id: str,
    body: AuthorizedUserUpdate,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    await get_current_user(authorization)
    db = get_supabase_client()
    payload = _persistable(body.model_dump(exclude_unset=True))
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        result = (
            db.table("authorized_users")
            .update(payload)
            .eq("id", user_id)
            .execute()
        )
    except Exception as exc:
        logger.warning("authorized_users update failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Authorized user not found")
    return _wire(rows[0])


@router.delete("/{user_id}")
async def delete_authorized_user(
    user_id: str,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    await get_current_user(authorization)
    db = get_supabase_client()
    db.table("authorized_users").delete().eq("id", user_id).execute()
    return {"ok": True}
