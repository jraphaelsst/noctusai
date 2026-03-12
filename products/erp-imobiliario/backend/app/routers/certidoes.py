"""
Certidões Negativas Router — Automated issuance and AI analysis of
negative certificates for real estate due diligence.

-- CREATE TABLE certidao_consultas (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   created_by uuid NOT NULL,
--   tipo_documento text NOT NULL CHECK (tipo_documento IN ('cpf', 'cnpj')),
--   documento text NOT NULL,
--   nome text NOT NULL,
--   data_nascimento text,
--   genero text,
--   rg text,
--   nome_mae text,
--   nome_pai text,
--   status text NOT NULL DEFAULT 'pendente',
--   total_certidoes int NOT NULL DEFAULT 0,
--   concluidas int NOT NULL DEFAULT 0,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
--
-- CREATE TABLE certidao_resultados (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   consulta_id uuid NOT NULL REFERENCES certidao_consultas(id) ON DELETE CASCADE,
--   org_id uuid NOT NULL,
--   tipo text NOT NULL,
--   nome_display text NOT NULL,
--   ordem int NOT NULL DEFAULT 0,
--   status text NOT NULL DEFAULT 'pendente',
--   analise_ia text,
--   arquivo_url text,
--   arquivo_nome text,
--   api_response jsonb,
--   erro_mensagem text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   updated_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import asyncio
import logging
from typing import Optional, Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, get_admin_client, get_org_id, log_action
from app.responses import paginated_response, success_response, ok_response, calculate_pagination
from app.config import settings
from app.services.certidoes_service import (
    CERTIDOES_CONFIG,
    get_certidoes_tipos,
    processar_consulta,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/certidoes", tags=["Certidões"])


# --------------- Schemas ---------------

class ConsultaCreate(BaseModel):
    tipo_documento: Literal["cpf", "cnpj"]
    documento: str = Field(..., min_length=11, max_length=18)
    nome: str = Field(..., min_length=2, max_length=200)
    data_nascimento: Optional[str] = None
    genero: Optional[Literal["M", "F"]] = None
    rg: Optional[str] = None
    nome_mae: Optional[str] = None
    nome_pai: Optional[str] = None


# --------------- Endpoints ---------------

@router.get("/tipos")
async def listar_tipos_certidoes(authorization: Optional[str] = Header(None)):
    """List available certificate types."""
    await get_current_user(authorization)
    return success_response(get_certidoes_tipos())


@router.get("/consultas")
async def listar_consultas(
    busca: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    authorization: Optional[str] = Header(None),
):
    """List certificate consultation requests."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    # Count
    count_query = db.table("certidao_consultas").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if busca:
        count_query = count_query.or_(
            f"nome.ilike.%{busca}%,documento.ilike.%{busca}%"
        )
    count_result = count_query.execute()
    total = count_result.count if count_result.count is not None else 0

    # Data
    query = db.table("certidao_consultas").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if busca:
        query = query.or_(
            f"nome.ilike.%{busca}%,documento.ilike.%{busca}%"
        )
    query = query.range(offset, offset + validated_page_size - 1)

    result = query.execute()
    return paginated_response(result.data or [], total, validated_page, validated_page_size)


@router.post("/consultas")
async def criar_consulta(
    body: ConsultaCreate,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Create a new certificate consultation and start processing in background."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)
    org_id = get_org_id(user)

    # Insert consulta
    consulta_data = {
        **body.model_dump(exclude_none=True),
        "created_by": user.id,
        "status": "pendente",
        "total_certidoes": len(CERTIDOES_CONFIG),
        "concluidas": 0,
    }
    if org_id:
        consulta_data["org_id"] = org_id

    consulta_result = db.table("certidao_consultas").insert(consulta_data).execute()
    if not consulta_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar consulta")
    consulta = consulta_result.data[0]

    # Insert one resultado per certificate type
    resultados_data = [
        {
            "consulta_id": consulta["id"],
            **({"org_id": org_id} if org_id else {}),
            "tipo": config["tipo"],
            "nome_display": config["nome"],
            "ordem": config["ordem"],
            "status": "pendente",
        }
        for config in CERTIDOES_CONFIG
    ]
    db.table("certidao_resultados").insert(resultados_data).execute()

    log_action(
        user.id, "criar", "certidao_consulta", consulta["id"],
        f"Solicitou certidões para {body.nome} ({body.tipo_documento.upper()}: {body.documento})"
    )

    # Start background processing with admin client (service role for updates)
    admin_db = get_admin_client()
    background_tasks.add_task(_run_processing, consulta["id"], admin_db)

    # Return consulta with resultados
    resultados = db.table("certidao_resultados").select("*").eq(
        "consulta_id", consulta["id"]
    ).order("ordem").execute()

    consulta["resultados"] = resultados.data or []
    return success_response(consulta)


@router.get("/consultas/{consulta_id}")
async def obter_consulta(consulta_id: str, authorization: Optional[str] = Header(None)):
    """Get a consultation with all its certificate results."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    consulta = db.table("certidao_consultas").select("*").eq(
        "id", consulta_id
    ).single().execute()
    if not consulta.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    resultados = db.table("certidao_resultados").select("*").eq(
        "consulta_id", consulta_id
    ).order("ordem").execute()

    data = consulta.data
    data["resultados"] = resultados.data or []
    return success_response(data)


@router.post("/consultas/{consulta_id}/reprocessar")
async def reprocessar_consulta(
    consulta_id: str,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Retry failed certificates in a consultation."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    consulta = db.table("certidao_consultas").select("*").eq(
        "id", consulta_id
    ).single().execute()
    if not consulta.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    # Reset failed resultados to pendente
    db.table("certidao_resultados").update({
        "status": "pendente",
        "erro_mensagem": None,
    }).eq("consulta_id", consulta_id).eq("status", "erro").execute()

    # Reset consulta status
    db.table("certidao_consultas").update({
        "status": "processando",
    }).eq("id", consulta_id).execute()

    log_action(
        user.id, "editar", "certidao_consulta", consulta_id,
        "Reprocessou certidões com erro"
    )

    admin_db = get_admin_client()
    background_tasks.add_task(_run_processing, consulta_id, admin_db)

    return ok_response("Reprocessamento iniciado")


@router.delete("/consultas/{consulta_id}")
async def excluir_consulta(consulta_id: str, authorization: Optional[str] = Header(None)):
    """Delete a consultation and all its results."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    check = db.table("certidao_consultas").select("id").eq("id", consulta_id).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    # CASCADE will delete resultados
    db.table("certidao_consultas").delete().eq("id", consulta_id).execute()

    log_action(
        user.id, "excluir", "certidao_consulta", consulta_id,
        f"Excluiu consulta de certidões {consulta_id}"
    )
    return ok_response("Consulta excluída com sucesso")


def _run_processing(consulta_id: str, db) -> None:
    """Wrapper to run async processing from a sync background task."""
    asyncio.run(processar_consulta(consulta_id, db))
