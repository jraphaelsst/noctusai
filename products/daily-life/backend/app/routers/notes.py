"""
Notes Router — Quick notes and journal entries for Daily Life.

Simple text notes with tags and categories for personal knowledge management.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from noctusai_lib.domain.ai import consent_required
from noctusai_lib.primitives.responses import success_response, paginated_response, ok_response
from noctusai_lib.api.auth import first_or_none

from app.dependencies import get_current_user, get_org_id, get_user_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notes", tags=["Notes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    conteudo: Optional[str] = None
    categoria: Optional[str] = None
    tags: Optional[list[str]] = None
    fixada: bool = False


class NoteUpdate(BaseModel):
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
    authorization: Optional[str] = Header(None),
    categoria: Optional[str] = Query(None),
    busca: Optional[str] = Query(None, description="Search in title and content"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List user notes with optional filters."""
    user, token = await get_current_user(authorization)
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
async def criar_nota(body: NoteCreate, authorization: Optional[str] = Header(None)):
    """Create a new note."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
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
async def obter_nota(note_id: str, authorization: Optional[str] = Header(None)):
    """Get a single note by ID."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("notas").select("*").eq("id", note_id).eq("user_id", str(user.id)).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")

    return success_response(row)


@router.patch("/{note_id}")
async def atualizar_nota(note_id: str, body: NoteUpdate, authorization: Optional[str] = Header(None)):
    """Update an existing note."""
    user, token = await get_current_user(authorization)
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
async def deletar_nota(note_id: str, authorization: Optional[str] = Header(None)):
    """Delete a note."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("notas").delete().eq("id", note_id).eq("user_id", str(user.id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Nota nao encontrada")

    return ok_response("Nota removida")


@router.post("/{note_id}/extract-tasks")
async def extract_tasks(
    note_id: str,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("daily_life.note_extract")),
):
    """D4 — extract actionable tasks from a note (ai-expansion Phase 16).

    Pulls the note body, asks the LLM for a list of `{title, due_hint}` items,
    returns the list for the user to review. Does NOT create task records —
    the UI confirms each item before it becomes a real task.
    """
    user, token = await get_current_user(authorization)
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
    tasks = await extract_tasks_from_note(row.get("conteudo") or "", org_id=get_org_id(user))
    return success_response({"tasks": tasks})
