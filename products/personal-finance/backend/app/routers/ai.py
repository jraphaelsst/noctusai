"""AI Features Router for Personal Finance — P1 indicators (Phase 7)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from noctusai_lib.ai import AIOutput, consent_required, persist_output

from app.dependencies import get_current_user_org, get_user_client
from app.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI"])


def _require_openai(org_id: Optional[str]):
    from app.services.ai_service import check_openai_configured
    if not check_openai_configured(org_id):
        raise HTTPException(
            status_code=422,
            detail=(
                "OpenAI API Key não configurada. "
                "Acesse Configurações > Chaves de API para configurar."
            ),
        )


def _persist_indicator(db, ref_type: str, ref_id: str, out: dict) -> dict:
    output = AIOutput(
        ref_type=ref_type,
        ref_id=ref_id,
        kind=out["kind"],
        label=out["label"],
        score=out.get("score"),
        chip=out.get("chip"),
        explanation=out.get("explanation"),
        confidence=out.get("confidence"),
        model_version=out.get("model_version"),
        prompt_version=out.get("prompt_version"),
    )
    try:
        return persist_output(db, schema="personal-finance", output=output)
    except Exception as e:
        logger.warning(
            "pf.ai.persist_indicator failed for %s/%s: %s", ref_type, ref_id, e
        )
        return {**output.to_insert_payload(), "id": None, "persist_error": str(e)}


class CategorizeTransactionRequest(BaseModel):
    transacao_id: str


class FlagRecurringRequest(BaseModel):
    transacao_id: str


@router.post("/transacoes/{transacao_id}/categorize")
async def categorize_transaction_endpoint(
    transacao_id: str,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("pf.transaction_categorize")),
):
    """P1-opp — suggest a category for a transaction and persist the indicator."""
    user, token, org_id = await get_current_user_org(authorization)
    _require_openai(org_id)
    db = get_user_client(token)

    tx_res = (
        db.table("transacoes")
        .select("id, descricao, valor, tipo, comerciante, categoria_id")
        .eq("id", transacao_id)
        .single()
        .execute()
    )
    if not tx_res.data:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    tx = tx_res.data

    cat_res = (
        db.table("categorias").select("id, nome, tipo").limit(50).execute()
    )
    categories = cat_res.data or []

    from app.services.ai_service import categorize_transaction
    out = await categorize_transaction(
        descricao=tx.get("descricao") or "",
        valor=float(tx.get("valor") or 0),
        tipo=tx.get("tipo") or "despesa",
        comerciante=tx.get("comerciante"),
        available_categories=categories,
        org_id=org_id,
    )
    persisted = _persist_indicator(db, "transacao", transacao_id, out)
    persisted["matched_categoria_id"] = out.get("matched_categoria_id")
    return success_response(persisted)


class MonthlyNarrativeSendRequest(BaseModel):
    recipient: str
    period_days: int = 30


@router.get("/monthly-narrative")
async def monthly_narrative_endpoint(
    period_days: int = 30,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("pf.monthly_narrative")),
):
    """P2-opp — build the past-month financial narrative for the caller's org
    and return the rendered digest payload + structured summary. No email send.

    Used by the dashboard card. Cron callers use the `/send` variant below.
    """
    user, token, org_id = await get_current_user_org(authorization)
    _require_openai(org_id)
    db = get_user_client(token)

    from app.services.monthly_narrative_service import build_narrative
    digest, summary = await build_narrative(db, org_id=org_id, period_days=period_days)
    return success_response({
        "subject": digest.subject,
        "html": digest.html,
        "text": digest.text,
        "summary": summary,
    })


@router.post("/monthly-narrative/send")
async def monthly_narrative_send_endpoint(
    body: MonthlyNarrativeSendRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("pf.monthly_narrative")),
):
    """P2-opp — build + email the past-month financial narrative to a recipient.
    Designed for cron / n8n triggers (typically end-of-month)."""
    user, token, org_id = await get_current_user_org(authorization)
    _require_openai(org_id)
    db = get_user_client(token)

    from app.services.monthly_narrative_service import send_monthly_narrative
    result = await send_monthly_narrative(
        db, org_id=org_id, recipient=body.recipient, period_days=body.period_days
    )
    return success_response(result)


@router.post("/transacoes/{transacao_id}/recurring-flag")
async def recurring_flag_endpoint(
    transacao_id: str,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("pf.recurring_flag")),
):
    """P3-opp — flag whether a transaction looks recurring and persist the indicator."""
    user, token, org_id = await get_current_user_org(authorization)
    _require_openai(org_id)
    db = get_user_client(token)

    tx_res = (
        db.table("transacoes")
        .select("id, descricao, valor, tipo, comerciante, data")
        .eq("id", transacao_id)
        .single()
        .execute()
    )
    if not tx_res.data:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    tx = tx_res.data

    history: list[dict] = []
    if tx.get("comerciante"):
        hist_res = (
            db.table("transacoes")
            .select("id, data, valor, descricao")
            .eq("comerciante", tx["comerciante"])
            .neq("id", transacao_id)
            .order("data", desc=True)
            .limit(12)
            .execute()
        )
        history = hist_res.data or []

    from app.services.ai_service import flag_recurring_expense
    out = await flag_recurring_expense(
        descricao=tx.get("descricao") or "",
        valor=float(tx.get("valor") or 0),
        tipo=tx.get("tipo") or "despesa",
        similar_history=history,
        org_id=org_id,
    )
    persisted = _persist_indicator(db, "transacao", transacao_id, out)
    return success_response(persisted)
