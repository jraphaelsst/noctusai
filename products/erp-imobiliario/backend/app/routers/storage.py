"""
Storage Router — File upload and management endpoints.

Provides upload/delete endpoints for property photos, documents,
inspection images, and other file types.
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, UploadFile
from app.dependencies import get_current_user, get_user_client, get_org_id, log_action
from app.services.storage_service import StorageService
from app.responses import success_response, ok_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    categoria: str = Form(default="geral"),
    auth = Depends(get_current_user)):
    """Upload a single file to Supabase Storage."""
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user)

    storage = StorageService(db, org_id)

    # Validate
    content_type = file.content_type or "application/octet-stream"
    file_bytes = await file.read()
    error = storage.validate_file(file.filename or "file", content_type, len(file_bytes), categoria)
    if error:
        raise HTTPException(status_code=400, detail=error)

    result = await storage.upload(file_bytes, file.filename or "file", content_type, categoria)

    log_action(user.id, "upload", "arquivo", descricao=f"Upload: {file.filename} ({categoria})")

    return success_response(result)


@router.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(...),
    categoria: str = Form(default="geral"),
    auth = Depends(get_current_user)):
    """Upload multiple files at once."""
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user)

    storage = StorageService(db, org_id)

    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Máximo de 20 arquivos por vez")

    results = []
    for f in files:
        content_type = f.content_type or "application/octet-stream"
        file_bytes = await f.read()
        error = storage.validate_file(f.filename or "file", content_type, len(file_bytes), categoria)
        if error:
            raise HTTPException(status_code=400, detail=f"{f.filename}: {error}")
        result = await storage.upload(file_bytes, f.filename or "file", content_type, categoria)
        results.append(result)

    log_action(user.id, "upload_multiplo", "arquivo",
               descricao=f"Upload de {len(results)} arquivos ({categoria})")

    return success_response(results, total=len(results))


@router.delete("/delete")
async def delete_file(
    path: str,
    categoria: str = "geral",
    auth = Depends(get_current_user)):
    """Delete a file from storage."""
    user, token = auth
    db = get_user_client(token)
    org_id = get_org_id(user)

    storage = StorageService(db, org_id)
    success = await storage.delete(path, categoria)

    if not success:
        raise HTTPException(status_code=500, detail="Falha ao excluir arquivo")

    log_action(user.id, "delete", "arquivo", descricao=f"Delete: {path}")

    return ok_response("Arquivo excluído")
