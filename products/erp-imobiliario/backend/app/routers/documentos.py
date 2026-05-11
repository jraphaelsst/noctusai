"""
Documentos CRUD Router — Document management and template-based generation.

Manages document uploads, metadata, templates with variable substitution,
and document generation from templates.

-- CREATE TABLE documentos (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   nome text NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('contrato', 'procuracao', 'laudo', 'certidao', 'outro')),
--   arquivo_url text,
--   arquivo_path text,
--   tamanho_bytes bigint,
--   mime_type text,
--   imovel_id uuid,
--   cliente_id uuid,
--   proposta_id uuid,
--   template_id uuid,
--   metadata jsonb NOT NULL DEFAULT '{}',
--   created_by uuid NOT NULL,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE TABLE document_templates (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   nome text NOT NULL,
--   tipo text NOT NULL,
--   conteudo text NOT NULL,
--   variaveis text[] NOT NULL DEFAULT '{}',
--   is_active boolean NOT NULL DEFAULT true,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
from typing import Optional, Literal, Dict
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field
from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.services.document_service import DocumentService
from app.config import settings
from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documentos", tags=["Documentos"])


# --- Pydantic models ---

class DocumentoCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    tipo: Literal["contrato", "procuracao", "laudo", "certidao", "outro"]
    arquivo_url: Optional[str] = None
    arquivo_path: Optional[str] = None
    tamanho_bytes: Optional[int] = Field(default=None, ge=0)
    mime_type: Optional[str] = Field(default=None, max_length=100)
    imovel_id: Optional[str] = None
    cliente_id: Optional[str] = None
    proposta_id: Optional[str] = None
    template_id: Optional[str] = None
    metadata: Optional[dict] = None


class TemplateCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    tipo: Literal["contrato", "procuracao", "laudo", "certidao", "outro"]
    conteudo: str = Field(..., min_length=1, description="Conteúdo do template com variáveis {{nome}}")
    variaveis: list[str] = Field(default_factory=list, description="Lista de variáveis do template")
    is_active: bool = True


class GenerateDocumentRequest(BaseModel):
    template_id: str
    variables: Dict[str, str] = Field(..., description="Valores das variáveis do template")
    imovel_id: Optional[str] = None
    cliente_id: Optional[str] = None
    proposta_id: Optional[str] = None


# --- Document Endpoints ---

@router.get("")
async def listar_documentos(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    imovel_id: Optional[str] = Query(None, description="Filtrar por imóvel"),
    cliente_id: Optional[str] = Query(None, description="Filtrar por cliente"),
    proposta_id: Optional[str] = Query(None, description="Filtrar por proposta"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    """List documents with filters and pagination."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Build count query
    count_query = db.table("documentos").select("id", count="exact")
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if imovel_id:
        count_query = count_query.eq("imovel_id", imovel_id)
    if cliente_id:
        count_query = count_query.eq("cliente_id", cliente_id)
    if proposta_id:
        count_query = count_query.eq("proposta_id", proposta_id)

    # Build data query
    query = db.table("documentos").select("*").order("created_at", desc=True)
    if tipo:
        query = query.eq("tipo", tipo)
    if imovel_id:
        query = query.eq("imovel_id", imovel_id)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)
    if proposta_id:
        query = query.eq("proposta_id", proposta_id)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/templates")
async def listar_templates(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    ativo: bool = Query(True, description="Filtrar apenas ativos"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    auth = Depends(get_current_user)):
    """List document templates."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    count_query = db.table("document_templates").select("id", count="exact")
    if tipo:
        count_query = count_query.eq("tipo", tipo)
    if ativo:
        count_query = count_query.eq("is_active", True)

    query = db.table("document_templates").select("*").order("created_at", desc=True)
    if tipo:
        query = query.eq("tipo", tipo)
    if ativo:
        query = query.eq("is_active", True)

    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    data = result.data or []

    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else len(data)

    return paginated_response(data, total, validated_page, validated_page_size)


@router.get("/{documento_id}")
async def obter_documento(documento_id: str, auth = Depends(get_current_user)):
    """Get a single document by ID."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("documentos").select("*").eq("id", documento_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return success_response(result.data)


@router.post("")
async def criar_documento(body: DocumentoCreate, auth = Depends(get_current_user)):
    """Create/upload a new document."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    data["created_by"] = user.id
    if "metadata" not in data:
        data["metadata"] = {}

    result = db.table("documentos").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar documento")

    log_action(user.id, "criar", "documento", row["id"],
               f"Criou documento: {body.nome} ({body.tipo})")

    return success_response(row)


@router.post("/templates")
async def criar_template(body: TemplateCreate, auth = Depends(get_current_user)):
    """Create a new document template."""
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)

    # Auto-detect variables from content if not provided
    if not data.get("variaveis"):
        service = DocumentService(db, user.id)
        data["variaveis"] = service.extract_variables(body.conteudo)

    result = db.table("document_templates").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar template")

    log_action(user.id, "criar", "template", row["id"],
               f"Criou template: {body.nome}")

    return success_response(row)


@router.post("/generate")
async def gerar_documento(body: GenerateDocumentRequest, auth = Depends(get_current_user)):
    """Generate a document from a template by substituting variables."""
    user, token = auth
    db = get_user_client(token)

    service = DocumentService(db, user.id)

    # Build metadata from optional references
    metadata = {}
    if body.imovel_id:
        metadata["imovel_id"] = body.imovel_id
    if body.cliente_id:
        metadata["cliente_id"] = body.cliente_id
    if body.proposta_id:
        metadata["proposta_id"] = body.proposta_id

    result = await service.generate_from_template(
        template_id=body.template_id,
        variables=body.variables,
        metadata=metadata,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Template não encontrado ou inativo")

    log_action(user.id, "gerar", "documento", result["id"],
               f"Gerou documento a partir do template {body.template_id}")

    return success_response(result)


@router.delete("/{documento_id}")
async def excluir_documento(documento_id: str, auth = Depends(get_current_user)):
    """Delete a document."""
    user, token = auth
    db = get_user_client(token)

    delete_or_404(db, "documentos", ("id", documento_id), message = "Documento não encontrado")

    log_action(user.id, "excluir", "documento", documento_id,
               f"Excluiu documento {documento_id}")

    return ok_response("Documento excluído com sucesso")
