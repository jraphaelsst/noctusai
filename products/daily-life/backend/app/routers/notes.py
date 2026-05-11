"""
Notes Router — Quick notes and journal entries for Daily Life.

Simple text notes with tags and categories for personal knowledge management.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from noctusai_lib.domain.ai import consent_required
from noctusai_lib.primitives.responses import success_response, paginated_response, ok_response
from noctusai_lib.api.auth import first_or_none

from app.dependencies import get_user_client, get_current_user_org
from noctusai_lib.api.crud_safety import delete_or_404
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notes", tags=["Notes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NoteCreate(StrictHttpModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    conteudo: Optional[str] = None
    categoria: Optional[str] = None
    tags: Optional[list[str]] = None
    fixada: bool = False


class NoteUpdate(StrictHttpModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=300)
    conteudo: Optional[str] = None
    categoria: Optional[str] = None
    tags: Optional[list[str]] = None
    fixada: Optional[bool] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def listar_notas(
    auth: tuple = Depends(get_current_user_org),
    categoria: Optional[str] = Query(None),
    busca: Optional[str] = Query(None, description="Search in title and content"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List user notes with optional filters."""
    user, token, _org_id = auth
    db = get_user_client(token)

    query = db.table("notas").select("*", count="exact").eq("user_id", str(user.id))

    if categoria:
        query = query.eq("categoria", categoria)
    if busca:
        query = query.or_(f"titulo.ilike.%{busca}%,conteudo.ilike.%{busca}%")

    query = query.order("fixada", desc=True).order("updated_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("")
async def criar_nota(body: NoteCreate, auth: tuple = Depends(get_current_user_org)):
    """Create a new note."""
    user, token, org_id = auth
    db = get_user_client(token)

    result = db.table("notas").insert({
        "user_id": str(user.id),
        "org_id": org_id,
        "titulo": body.titulo,
        "conteudo": body.conteudo,
        "categoria": body.categoria,
        "tags": body.tags or [],
        "fixada": body.fixada,
    }).execute()

    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar nota")

    return success_response(row)


@router.get("/{note_id}")
async def obter_nota(note_id: str, auth: tuple = Depends(get_current_user_org)):
    """Get a single note by ID."""
    user, token, _org_id = auth
    db = get_user_client(token)

    result = db.table("notas").select("*").eq("id", note_id).eq("user_id", str(user.id)).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")

    return success_response(row)


@router.patch("/{note_id}")
async def atualizar_nota(note_id: str, body: NoteUpdate, auth: tuple = Depends(get_current_user_org)):
    """Update an existing note."""
    user, token, _org_id = auth
    db = get_user_client(token)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = (
        db.table("notas")
        .update(updates)
        .eq("id", note_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")

    return success_response(row)


@router.delete("/{note_id}")
async def deletar_nota(note_id: str, auth: tuple = Depends(get_current_user_org)):
    """Delete a note."""
    user, token, _org_id = auth
    db = get_user_client(token)

    delete_or_404(db, "notas", ("id", note_id), ("user_id", str(user.id)), message="Nota nao encontrada")

    return ok_response("Nota removida")


@router.post("/{note_id}/extract-tasks")
async def extract_tasks(
    note_id: str,
    auth: tuple = Depends(get_current_user_org),
    _consent: None = Depends(consent_required("daily_life.note_extract")),
):
    """D4 — extract actionable tasks from a note (ai-expansion Phase 16).

    Pulls the note body, asks the LLM for a list of `{title, due_hint}` items,
    returns the list for the user to review. Does NOT create task records —
    the UI confirms each item before it becomes a real task.
    """
    user, token, org_id = auth
    db = get_user_client(token)

    result = (
        db.table("notas")
        .select("conteudo")
        .eq("id", note_id)
        .eq("user_id", str(user.id))
        .execute()
    )
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")

    from app.services.ai_service import extract_tasks_from_note
    tasks = await extract_tasks_from_note(row.get("conteudo") or "", org_id=org_id)
    return success_response({"tasks": tasks})
