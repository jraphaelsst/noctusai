"""
Journal Service — Patient journaling CRUD.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.responses import calculate_pagination

logger = logging.getLogger(__name__)


async def create_entry(
    patient_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Create a journal entry for a patient."""
    record = {
        "patient_id": patient_id,
        "titulo": data.get("titulo"),
        "conteudo": data["conteudo"],
        "is_shared_with_therapist": False,
    }
    result = db.table("journal_entries").insert(record).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar entrada de diário")
    logger.info("Journal entry created for patient %s", patient_id)
    return row


async def update_entry(
    entry_id: str,
    data: Dict,
    db: Any,
) -> Dict:
    """Update a journal entry."""
    check = db.table("journal_entries").select("id").eq("id", entry_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Entrada de diário não encontrada")

    update_fields = {k: v for k, v in data.items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("journal_entries").update(update_fields).eq("id", entry_id).execute()
    return first_or_none(result) or {}


async def delete_entry(
    entry_id: str,
    db: Any,
) -> None:
    """Delete a journal entry."""
    check = db.table("journal_entries").select("id").eq("id", entry_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Entrada de diário não encontrada")

    db.table("journal_entries").delete().eq("id", entry_id).execute()
    logger.info("Journal entry %s deleted", entry_id)


async def list_entries(
    patient_id: str,
    db: Any,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[Dict], int]:
    """List journal entries for a patient, paginated."""
    page, page_size, offset = calculate_pagination(page, page_size)

    result = (
        db.table("journal_entries")
        .select("*", count="exact")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    return result.data or [], result.count or 0
