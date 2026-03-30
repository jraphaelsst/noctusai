"""
Matrículas Router — Upload property registration PDFs and extract text via AI OCR.

-- CREATE TABLE erp.matricula_extracoes (
--   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id UUID NOT NULL,
--   user_id UUID NOT NULL,
--   nome_arquivo TEXT NOT NULL,
--   tamanho_bytes INTEGER,
--   num_paginas INTEGER,
--   texto_extraido TEXT,
--   status TEXT NOT NULL DEFAULT 'pendente',
--   erro_mensagem TEXT,
--   created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
--   updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, UploadFile, File

from app.dependencies import get_current_user, get_user_client, get_admin_client, get_org_id, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.matricula_service import (
    processar_extracao,
    check_required_credentials,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matriculas", tags=["Matrículas"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


# --------------- Endpoints ---------------

@router.post("/extrair")
async def extrair_matricula(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    authorization: Optional[str] = Header(None),
):
    """Upload a matrícula PDF and start text extraction in background."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = get_org_id(user)

    # Validate credentials upfront
    missing = check_required_credentials(org_id)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=" ".join(missing)
            + " Acesse Configurações > Chaves de API para configurar.",
        )

    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    # Read and validate size
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo muito grande ({len(pdf_bytes) // (1024*1024)}MB). Máximo: {MAX_FILE_SIZE // (1024*1024)}MB.",
        )

    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    # Create DB record
    extracao_data = {
        "user_id": user.id,
        "nome_arquivo": file.filename or "matricula.pdf",
        "tamanho_bytes": len(pdf_bytes),
        "status": "pendente",
    }
    if org_id:
        extracao_data["org_id"] = org_id

    result = db.table("matricula_extracoes").insert(extracao_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar extração")
    extracao = result.data[0]

    log_action(
        user.id, "criar", "matricula_extracao", extracao["id"],
        f"Upload de matrícula: {file.filename} ({len(pdf_bytes) // 1024}KB)"
    )

    # Start background processing with admin client
    admin_db = get_admin_client()
    background_tasks.add_task(_run_extraction, extracao["id"], pdf_bytes, org_id, admin_db)

    return success_response(extracao)


@router.get("/extracoes")
async def listar_extracoes(
    busca: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """List extraction history."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count
    count_query = db.table("matricula_extracoes").select("id", count="exact")
    if busca:
        count_query = count_query.ilike("nome_arquivo", f"%{busca}%")
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data — exclude texto_extraido from list for performance
    query = db.table("matricula_extracoes").select(
        "id,nome_arquivo,tamanho_bytes,num_paginas,status,erro_mensagem,created_at"
    ).order("created_at", desc=True)
    if busca:
        query = query.ilike("nome_arquivo", f"%{busca}%")
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.get("/extracoes/{extracao_id}")
async def obter_extracao(extracao_id: str, authorization: Optional[str] = Header(None)):
    """Get a single extraction with full text."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("matricula_extracoes").select("*").eq(
        "id", extracao_id
    ).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Extração não encontrada")

    return success_response(result.data)


@router.delete("/extracoes/{extracao_id}")
async def excluir_extracao(extracao_id: str, authorization: Optional[str] = Header(None)):
    """Delete an extraction."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("matricula_extracoes").select("id").eq("id", extracao_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Extração não encontrada")

    db.table("matricula_extracoes").delete().eq("id", extracao_id).execute()

    log_action(
        user.id, "excluir", "matricula_extracao", extracao_id,
        f"Excluiu extração de matrícula {extracao_id}"
    )
    return ok_response("Extração excluída com sucesso")


def _run_extraction(extracao_id: str, pdf_bytes: bytes, org_id: Optional[str], db) -> None:
    """Wrapper to run async extraction from a sync background task."""
    asyncio.run(processar_extracao(extracao_id, pdf_bytes, org_id, db))
