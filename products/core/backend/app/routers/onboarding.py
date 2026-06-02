"""
Onboarding Router — Manage organization onboarding wizard state.

GET   /api/onboarding/status   — Returns onboarding completion state for current user's org
PATCH /api/onboarding/complete — Marks a step as completed

-- Supabase SQL to add onboarding columns to organizations:
--
-- ALTER TABLE organizations ADD COLUMN onboarding_completed boolean NOT NULL DEFAULT false;
-- ALTER TABLE organizations ADD COLUMN onboarding_steps jsonb NOT NULL DEFAULT
--   '{"company_details": false, "choose_plan": false, "invite_team": false, "enable_product": false}';
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request

from app.database import get_admin_client
from app.dependencies import get_current_user, get_org_id
from app.rate_limit import limiter
from app.schemas.onboarding import StepComplete, CompanyDetailsUpdate
from noctusai_lib.api.rate_limit_policies import DEFAULT_AUTH_RL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])

VALID_STEPS = {"company_details", "choose_plan", "invite_team", "enable_product"}

DEFAULT_STEPS = {
    "company_details": False,
    "choose_plan": False,
    "invite_team": False,
    "enable_product": False,
}


@router.get("/status")
@limiter.limit(DEFAULT_AUTH_RL)
async def get_onboarding_status(request: Request, authorization: Optional[str] = Header(None)):
    """Returns onboarding completion state for the current user's organization."""
    user, token = await get_current_user(authorization)
    org_id = await get_org_id(user)
    db = get_admin_client()

    # Get organization onboarding state
    org = db.table("organizations").select(
        "id, nome, onboarding_completed, onboarding_steps"
    ).eq("id", org_id).single().execute()

    if not org.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")

    steps = org.data.get("onboarding_steps") or DEFAULT_STEPS.copy()
    completed = org.data.get("onboarding_completed", False)

    # Calculate progress
    total_steps = len(VALID_STEPS)
    completed_count = sum(1 for v in steps.values() if v)

    return {
        "data": {
            "org_id": org_id,
            "org_nome": org.data.get("nome"),
            "onboarding_completed": completed,
            "steps": steps,
            "progress": {
                "completed": completed_count,
                "total": total_steps,
                "percentage": round((completed_count / total_steps) * 100) if total_steps > 0 else 0,
            },
        }
    }


@router.patch("/complete")
@limiter.limit(DEFAULT_AUTH_RL)
async def complete_onboarding_step(
    request: Request,
    body: StepComplete,
    authorization: Optional[str] = Header(None),
):
    """Marks a specific onboarding step as completed."""
    user, token = await get_current_user(authorization)

    if body.step not in VALID_STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Passo inválido. Passos válidos: {', '.join(sorted(VALID_STEPS))}",
        )

    org_id = await get_org_id(user)
    db = get_admin_client()

    # Get current onboarding state
    org = db.table("organizations").select(
        "id, onboarding_completed, onboarding_steps"
    ).eq("id", org_id).single().execute()

    if not org.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")

    steps = org.data.get("onboarding_steps") or DEFAULT_STEPS.copy()
    steps[body.step] = True

    # If company_details step, also update org info (incl. org_type + number_of_users)
    if body.step == "company_details" and body.data:
        update_data = {}
        if body.data.get("nome"):
            update_data["nome"] = body.data["nome"]
        if body.data.get("cnpj"):
            update_data["cnpj"] = body.data["cnpj"]
        if body.data.get("telefone"):
            update_data["telefone"] = body.data["telefone"]
        if body.data.get("endereco"):
            update_data["endereco"] = body.data["endereco"]
        if body.data.get("org_type") in ("individual", "company"):
            update_data["org_type"] = body.data["org_type"]
        if body.data.get("number_of_users") is not None:
            n = int(body.data["number_of_users"])
            if n >= 1:
                update_data["number_of_users"] = n
        if update_data:
            db.table("organizations").update(update_data).eq("id", org_id).execute()

    # Check if all steps are completed
    all_completed = all(steps.get(s, False) for s in VALID_STEPS)

    update_payload = {
        "onboarding_steps": steps,
        "onboarding_completed": all_completed,
    }

    result = db.table("organizations").update(update_payload).eq("id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao atualizar onboarding")

    completed_count = sum(1 for v in steps.values() if v)
    total_steps = len(VALID_STEPS)

    logger.info(f"Onboarding step '{body.step}' completed for org {org_id}")
    return {
        "data": {
            "org_id": org_id,
            "step": body.step,
            "onboarding_completed": all_completed,
            "steps": steps,
            "progress": {
                "completed": completed_count,
                "total": total_steps,
                "percentage": round((completed_count / total_steps) * 100) if total_steps > 0 else 0,
            },
        }
    }
