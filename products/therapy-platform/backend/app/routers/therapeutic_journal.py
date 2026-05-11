"""
Therapeutic Journal Router — Patient private journal entries.

Patients maintain a personal therapeutic journal. Entries are
private by default and only visible to the patient.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import (
    first_or_none,
    get_current_user,
    get_user_client,
    get_user_role,
)
from app.responses import ok_response, paginated_response, success_response
from app.services import journal_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/diary", tags=["Therapeutic Journal"])


@router.post("")
async def create_journal_entry(
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Create a journal entry (patient only)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem criar entradas no diário")

    db = get_user_client(token)
    data = await journal_service.create_entry(
        patient_id=user.id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.get("")
async def list_journal_entries(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List journal entries for the current patient (paginated)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem visualizar o diário")

    db = get_user_client(token)
    data, total = await journal_service.list_entries(
        patient_id=user.id,
        page=page,
        page_size=page_size,
        db=db,
    )
    return paginated_response(data, total, page, page_size)


@router.patch("/{entry_id}")
async def update_journal_entry(
    entry_id: str,
    body: dict,
    authorization: Optional[str] = Header(None),
):
    """Update a journal entry (patient only, must be owner)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem editar entradas no diário")

    db = get_user_client(token)

    # Verify existence and ownership
    existing = first_or_none(
        db.table("journal_entries")
        .select("id, patient_id")
        .eq("id", entry_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Entrada de diário não encontrada")
    if existing["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta entrada")

    data = await journal_service.update_entry(
        entry_id=entry_id,
        data=body,
        db=db,
    )
    return success_response(data)


@router.delete("/{entry_id}")
async def delete_journal_entry(
    entry_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a journal entry (patient only, must be owner)."""
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    if role != "patient":
        raise HTTPException(status_code=403, detail="Apenas pacientes podem excluir entradas do diário")

    db = get_user_client(token)

    # Verify existence and ownership
    existing = first_or_none(
        db.table("journal_entries")
        .select("id, patient_id")
        .eq("id", entry_id)
        .execute()
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Entrada de diário não encontrada")
    if existing["patient_id"] != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para excluir esta entrada")

    await journal_service.delete_entry(entry_id=entry_id, db=db)
    return ok_response("Entrada de diário excluída com sucesso")
