"""
AI Features Router — property description generation, lead scoring, and price suggestions.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from app.dependencies import get_current_user, get_user_client
from app.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateDescriptionRequest(BaseModel):
    imovel_id: Optional[str] = None
    imovel_data: Optional[dict] = None


class LeadScoreRequest(BaseModel):
    cliente_id: Optional[str] = None
    cliente_data: Optional[dict] = None


class SuggestPriceRequest(BaseModel):
    imovel_id: Optional[str] = None
    imovel_data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate-description")
async def generate_description(body: GenerateDescriptionRequest, authorization: Optional[str] = Header(None)):
    """Generate an AI-powered property description."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Get property data — either from ID or from request body
    imovel_data = body.imovel_data or {}
    if body.imovel_id and not imovel_data:
        result = db.table("ativos").select("*").eq("id", body.imovel_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        imovel_data = result.data

    if not imovel_data:
        raise HTTPException(status_code=400, detail="Dados do imóvel são obrigatórios")

    try:
        from app.services.ai_service import generate_description as gen_desc
        result = await gen_desc(imovel_data)
        return success_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"AI description generation failed: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar descrição com IA")


@router.post("/lead-score")
async def lead_score(body: LeadScoreRequest, authorization: Optional[str] = Header(None)):
    """Score a lead using AI analysis."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Get client data — either from ID or from request body
    cliente_data = body.cliente_data or {}
    if body.cliente_id and not cliente_data:
        result = db.table("clientes").select("*").eq("id", body.cliente_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        cliente_data = result.data

    if not cliente_data:
        raise HTTPException(status_code=400, detail="Dados do cliente são obrigatórios")

    try:
        from app.services.ai_service import score_lead
        result = await score_lead(cliente_data)

        # Persist score to the clientes table
        if body.cliente_id:
            from datetime import datetime, timezone
            db.table("clientes").update({
                "lead_score": result["score"],
                "lead_score_justificativa": result["justificativa"],
                "lead_score_updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", body.cliente_id).execute()

        return success_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"AI lead scoring failed: {e}")
        raise HTTPException(status_code=500, detail="Erro ao pontuar lead com IA")


@router.post("/suggest-price")
async def suggest_price(body: SuggestPriceRequest, authorization: Optional[str] = Header(None)):
    """Suggest a price for a property based on comparables."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Get property data
    imovel_data = body.imovel_data or {}
    if body.imovel_id and not imovel_data:
        result = db.table("ativos").select("*").eq("id", body.imovel_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Imóvel não encontrado")
        imovel_data = result.data

    if not imovel_data:
        raise HTTPException(status_code=400, detail="Dados do imóvel são obrigatórios")

    # Fetch comparables — same tipo_imovel in the same cidade
    comparables = []
    if imovel_data.get("cidade") and imovel_data.get("tipo_imovel"):
        comp_query = db.table("ativos").select(
            "id, tipo_imovel, cidade, bairro, area_privativa, quartos, vagas, valor"
        ).eq("natureza", "imovel").eq("status", "ativo").eq(
            "tipo_imovel", imovel_data["tipo_imovel"]
        ).eq("cidade", imovel_data["cidade"]).limit(10)

        # Exclude the property itself if it has an id
        if imovel_data.get("id"):
            comp_query = comp_query.neq("id", imovel_data["id"])

        comp_result = comp_query.execute()
        comparables = comp_result.data or []

    try:
        from app.services.ai_service import suggest_price as sug_price
        result = await sug_price(imovel_data, comparables)
        result["total_comparaveis"] = len(comparables)
        return success_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"AI price suggestion failed: {e}")
        raise HTTPException(status_code=500, detail="Erro ao sugerir preço com IA")
