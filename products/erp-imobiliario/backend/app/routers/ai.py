"""
AI Features Router — property description generation, lead scoring, and price suggestions.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from noctusai_lib.domain.ai import consent_required, safe_persist_indicator

from app.dependencies import get_current_user, get_user_client, get_org_id
from app.responses import success_response
from app.rate_limit import limiter
from app.services.ai_service import check_openai_configured
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI"])


def _require_openai(org_id):
    """Raise 422 if OpenAI key is not configured."""
    if not check_openai_configured(org_id):
        raise HTTPException(
            status_code=422,
            detail="OpenAI API Key não configurada. "
            "Acesse Configurações > Chaves de API para configurar.",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateDescriptionRequest(StrictHttpModel):
    imovel_id: Optional[str] = None
    imovel_data: Optional[dict] = None


class LeadScoreRequest(StrictHttpModel):
    cliente_id: Optional[str] = None
    cliente_data: Optional[dict] = None


class SuggestPriceRequest(StrictHttpModel):
    imovel_id: Optional[str] = None
    imovel_data: Optional[dict] = None


class FollowUpDraftRequest(StrictHttpModel):
    cliente_id: str
    imovel_interesse: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate-description")
@limiter.limit(DEFAULT_AI_RL)
async def generate_description(
    request: Request,
    body: GenerateDescriptionRequest,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.imovel_description")),
):
    """Generate an AI-powered property description."""
    user, token = auth
    _require_openai(get_org_id(user))
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
@limiter.limit(DEFAULT_AI_RL)
async def lead_score(
    request: Request,
    body: LeadScoreRequest,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.lead_score")),
):
    """Score a lead using AI analysis."""
    user, token = auth
    _require_openai(get_org_id(user))
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
@limiter.limit(DEFAULT_AI_RL)
async def suggest_price(
    request: Request,
    body: SuggestPriceRequest,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.suggest_price")),
):
    """Suggest a price for a property based on comparables."""
    user, token = auth
    _require_openai(get_org_id(user))
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


@router.post("/leads/{lead_id}/follow-up-draft")
@limiter.limit(DEFAULT_AI_RL)
async def follow_up_draft(
    request: Request,
    lead_id: str,
    body: FollowUpDraftRequest,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.lead_follow_up_draft")),
):
    """E4 — draft a personalized follow-up message for a stalled lead.

    Pulls lead info from `clientes` (nome, etapa_atual, lead_score_justificativa,
    observacoes, last_activity delta) and asks the LLM for a short WhatsApp-ready
    message. Returns `{channel, subject, body}`. Never modifies the lead record —
    UI sends the message after user review.
    """
    user, token = auth
    _require_openai(get_org_id(user))
    db = get_user_client(token)

    # Fetch the lead. Body's cliente_id is authoritative but path lead_id is the URL key.
    cliente_id = body.cliente_id or lead_id
    result = (
        db.table("clientes")
        .select("id, nome, etapa_atual, lead_score_justificativa, observacoes, created_at, updated_at")
        .eq("id", cliente_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    lead = result.data

    # Compute days since last activity — use updated_at as proxy.
    from datetime import datetime, timezone
    days = 0
    last_str = lead.get("updated_at") or lead.get("created_at")
    if last_str:
        try:
            last_dt = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
            days = max(0, (datetime.now(timezone.utc) - last_dt).days)
        except (ValueError, TypeError) as exc:
            logger.warning("ai: lead has unparseable timestamp %r (%s); using days=0 for follow-up draft", last_str, exc)
            days = 0

    try:
        from app.services.ai_service import draft_follow_up
        draft = await draft_follow_up(
            cliente_nome=lead.get("nome") or "cliente",
            last_interaction_days=days,
            etapa_atual=lead.get("etapa_atual"),
            imovel_interesse=body.imovel_interesse,
            observacoes=lead.get("observacoes") or lead.get("lead_score_justificativa"),
            org_id=get_org_id(user),
        )
        return success_response({**draft, "days_since_activity": days})
    except Exception as e:
        logger.error(f"AI follow-up draft failed for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar rascunho de follow-up")


# ---------------------------------------------------------------------------
# Phase 6 P1 indicators (E2/E6/E7/E8/E10) — persist to erp.ai_outputs.
# ---------------------------------------------------------------------------


class WhatsAppIntentRequest(StrictHttpModel):
    cliente_id: str
    message_text: str
    cliente_nome: Optional[str] = None


class CertidoesScoreRequest(StrictHttpModel):
    cliente_id: str


class MetasCoachTipRequest(StrictHttpModel):
    user_id: str
    user_nome: str
    progresso_percent: float
    dias_restantes: int
    eventos_recentes: Optional[list[str]] = None


class PhotoComplianceRequest(StrictHttpModel):
    imovel_id: str


class SearchRelevanceRequest(StrictHttpModel):
    imovel_id: str
    query: str


@router.post("/whatsapp-intent")
@limiter.limit("60/minute")
async def whatsapp_intent(
    request: Request,
    body: WhatsAppIntentRequest,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.whatsapp_intent")),
):
    """E2 — classify a WhatsApp message into a sales intent and persist."""
    user, token = auth
    _require_openai(get_org_id(user))
    db = get_user_client(token)

    from app.services.ai_service import classify_whatsapp_intent
    out = await classify_whatsapp_intent(
        message_text=body.message_text,
        cliente_nome=body.cliente_nome,
        org_id=get_org_id(user),
    )
    persisted = safe_persist_indicator(db, schema="erp", ref_type="cliente", ref_id=body.cliente_id, out=out, logger=logger)
    return success_response(persisted)


@router.post("/clientes/{cliente_id}/certidoes-score")
@limiter.limit(DEFAULT_AI_RL)
async def certidoes_score(
    request: Request,
    cliente_id: str,
    body: Optional[CertidoesScoreRequest] = None,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.certidoes_score")),
):
    """E6 — score a client's certidões health and persist."""
    user, token = auth
    _require_openai(get_org_id(user))
    db = get_user_client(token)

    cliente_res = (
        db.table("clientes").select("id, nome").eq("id", cliente_id).single().execute()
    )
    if not cliente_res.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    cliente_nome = cliente_res.data.get("nome") or "cliente"

    # The canonical certidões schema (migrations/001 §12B) splits the data
    # across erp.certidao_consultas (one row per cliente-document lookup) and
    # erp.certidao_resultados (one row per certidão tipo within a consulta).
    # erp.clientes has no `cpf` / `cnpj` / `documento` column, and consultas
    # carry no `cliente_id` FK — the available linkage is by `nome`. We do a
    # best-effort name match (case-insensitive equality) on the 5 most recent
    # consultas for this cliente, then aggregate their resultados.
    consultas_res = (
        db.table("certidao_consultas")
        .select("id, nome, tipo_documento, documento, created_at")
        .ilike("nome", cliente_nome)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    consultas = consultas_res.data or []

    certidoes: list[dict] = []
    if consultas:
        consulta_ids = [c["id"] for c in consultas]
        resultados_res = (
            db.table("certidao_resultados")
            .select("tipo, nome_display, status, analise_ia, api_requested_at")
            .in_("consulta_id", consulta_ids)
            .order("api_requested_at", desc=True)
            .limit(20)
            .execute()
        )
        certidoes = resultados_res.data or []

    from app.services.ai_service import score_certidoes
    out = await score_certidoes(
        cliente_nome=cliente_nome,
        certidoes=certidoes,
        org_id=get_org_id(user),
    )
    persisted = safe_persist_indicator(db, schema="erp", ref_type="cliente", ref_id=cliente_id, out=out, logger=logger)
    return success_response(persisted)


@router.post("/metas/coach-tip")
@limiter.limit(DEFAULT_AI_RL)
async def metas_coach_tip(
    request: Request,
    body: MetasCoachTipRequest,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.metas_coach_tip")),
):
    """E7 — generate a coaching tip for the user's current metas progress."""
    user, token = auth
    _require_openai(get_org_id(user))
    db = get_user_client(token)

    from app.services.ai_service import generate_metas_coach_tip
    out = await generate_metas_coach_tip(
        user_nome=body.user_nome,
        progresso_percent=body.progresso_percent,
        dias_restantes=body.dias_restantes,
        eventos_recentes=body.eventos_recentes,
        org_id=get_org_id(user),
    )
    persisted = safe_persist_indicator(db, schema="erp", ref_type="user_metas", ref_id=body.user_id, out=out, logger=logger)
    return success_response(persisted)


@router.post("/imoveis/{imovel_id}/photo-compliance")
@limiter.limit(DEFAULT_AI_RL)
async def photo_compliance(
    request: Request,
    imovel_id: str,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.photo_compliance")),
):
    """E8 — assess listing-photo compliance from photo metadata."""
    user, token = auth
    _require_openai(get_org_id(user))
    db = get_user_client(token)

    imovel_res = (
        db.table("ativos")
        .select("id, descricao, fotos")
        .eq("id", imovel_id)
        .single()
        .execute()
    )
    if not imovel_res.data:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")

    fotos = imovel_res.data.get("fotos") or []
    # Coerce to list of dicts in case the column stores plain URL strings.
    fotos = [
        f if isinstance(f, dict) else {"url": str(f), "filename": str(f).rsplit("/", 1)[-1]}
        for f in fotos
    ]

    from app.services.ai_service import assess_photo_compliance
    out = await assess_photo_compliance(
        imovel_descricao=imovel_res.data.get("descricao"),
        fotos=fotos,
        org_id=get_org_id(user),
    )
    persisted = safe_persist_indicator(db, schema="erp", ref_type="ativo", ref_id=imovel_id, out=out, logger=logger)
    return success_response(persisted)


@router.post("/search-relevance")
@limiter.limit("60/minute")
async def search_relevance(
    request: Request,
    body: SearchRelevanceRequest,
    auth = Depends(get_current_user), _consent: None = Depends(consent_required("erp.search_relevance")),
):
    """E10 — score the relevance of a property to a search query and persist."""
    user, token = auth
    _require_openai(get_org_id(user))
    db = get_user_client(token)

    imovel_res = (
        db.table("ativos")
        .select(
            "id, tipo_imovel, bairro, cidade, area_privativa, area_total, "
            "quartos, valor, descricao"
        )
        .eq("id", body.imovel_id)
        .single()
        .execute()
    )
    if not imovel_res.data:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")

    from app.services.ai_service import score_search_relevance
    out = await score_search_relevance(
        query=body.query,
        imovel_data=imovel_res.data,
        org_id=get_org_id(user),
    )
    persisted = safe_persist_indicator(db, schema="erp", ref_type="ativo", ref_id=body.imovel_id, out=out, logger=logger)
    return success_response(persisted)
