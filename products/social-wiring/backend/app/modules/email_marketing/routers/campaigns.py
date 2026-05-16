"""Campaigns router — CRUD, schedule, send, pause, cancel, stats."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_org_id, get_admin_client
from app.modules.email_marketing.schemas.campaigns import CampaignCreate, CampaignUpdate, CampaignSchedule
from app.modules.email_marketing.services.campaign_service import CampaignService
from app.modules.email_marketing.services.send_service import SendService
from app.config import settings
from noctusai_lib.primitives.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/email-marketing/campaigns', tags=["Campaigns"])


def _get_service(user) -> CampaignService:
    org_id = get_org_id(user)
    return CampaignService(get_admin_client(), org_id)


@router.get("")
async def list_campaigns(
    auth = Depends(get_current_user_org), status: Optional[str] = Query(None),
):
    user, _, org_id = auth
    svc = _get_service(user)
    return success_response(svc.list_campaigns(status=status))


@router.post("")
async def create_campaign(body: CampaignCreate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.create_campaign(body.model_dump(), str(user.id))
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar campanha")
    return success_response(result)


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.get_campaign(campaign_id)
    if not result:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")
    stats = svc.get_stats(campaign_id)
    result["stats"] = stats
    return success_response(result)


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: str, body: CampaignUpdate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    data = body.model_dump(exclude_unset=True)
    result = svc.update_campaign(campaign_id, data)
    if not result:
        raise HTTPException(status_code=400, detail="Campanha nao pode ser editada neste status")
    return success_response(result)


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    if not svc.delete_campaign(campaign_id):
        raise HTTPException(status_code=400, detail="Apenas rascunhos podem ser excluidos")
    return {"ok": True, "message": "Campanha excluida"}


@router.post("/{campaign_id}/schedule")
async def schedule_campaign(campaign_id: str, body: CampaignSchedule, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.schedule_campaign(campaign_id, body.scheduled_at)
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao agendar campanha")
    return success_response(result)


@router.post("/{campaign_id}/send")
async def send_campaign(campaign_id: str, auth = Depends(get_current_user_org)):
    """Trigger immediate send — queues all recipients and starts sending."""
    user, _, org_id = auth
    org_id = get_org_id(user)
    svc = _get_service(user)

    # Start the campaign
    result = svc.start_send(campaign_id)
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao iniciar envio")

    # Queue all recipients
    send_svc = SendService(get_admin_client(), settings)
    queued = send_svc.queue_campaign_sends(campaign_id, org_id)

    return success_response({"campaign_id": campaign_id, "queued": queued})


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.pause_campaign(campaign_id)
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao pausar campanha")
    return success_response(result)


@router.post("/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.cancel_campaign(campaign_id)
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao cancelar campanha")
    return success_response(result)
