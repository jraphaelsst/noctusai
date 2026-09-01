"""Campaigns router — /api/mailchimp/campaigns.

  GET    /campaigns                           → {items, total}
  POST   /campaigns                           → CampaignOut (201)
  GET    /campaigns/{campaign_id}             → CampaignOut
  PATCH  /campaigns/{campaign_id}             → CampaignOut
  DELETE /campaigns/{campaign_id}             → 204
  POST   /campaigns/{campaign_id}/actions/send        → CampaignOut
  POST   /campaigns/{campaign_id}/actions/schedule    → CampaignOut
  POST   /campaigns/{campaign_id}/actions/unschedule  → CampaignOut
  POST   /campaigns/{campaign_id}/actions/test        → {ok: true}
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.mailchimp.deps import make_require_mailchimp_client
from app.modules.mailchimp.errors import translate_mailchimp_errors
from app.modules.mailchimp.schemas import (
    CampaignCreateBody,
    CampaignListOut,
    CampaignOut,
    CampaignPatchBody,
    CampaignScheduleBody,
    CampaignTestBody,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mailchimp/campaigns", tags=["Mailchimp"])

_require_client = make_require_mailchimp_client(require_audience=True)


def _campaign_out(c) -> CampaignOut:
    report = getattr(c, "report_summary", None) or {}
    return CampaignOut(
        id=c.id,
        web_id=getattr(c, "web_id", None),
        title=getattr(c, "title", None),
        status=getattr(c, "status", None),
        subject_line=getattr(c, "subject_line", None),
        preview_text=getattr(c, "preview_text", None),
        from_name=getattr(c, "from_name", None),
        reply_to=getattr(c, "reply_to", None),
        segment_id=getattr(c, "segment_id", None),
        template_id=getattr(c, "template_id", None),
        send_time=getattr(c, "send_time", None),
        create_time=getattr(c, "create_time", None),
        emails_sent=getattr(c, "emails_sent", None),
        opens=report.get("opens_total") if isinstance(report, dict) else getattr(report, "opens_total", None),
        clicks=report.get("clicks_total") if isinstance(report, dict) else getattr(report, "clicks_total", None),
        archive_url=getattr(c, "archive_url", None),
    )


@router.get("", response_model=CampaignListOut)
async def list_campaigns(
    count: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    client_record=Depends(_require_client),
) -> CampaignListOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        page = await client.list_campaigns(count=count, offset=offset)
    return CampaignListOut(
        items=[_campaign_out(c) for c in page.items],
        total=page.total,
    )


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreateBody,
    client_record=Depends(_require_client),
) -> CampaignOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        campaign = await client.create_campaign(
            audience_id=record.audience_id,
            title=body.title,
            subject_line=body.subject_line,
            preview_text=body.preview_text,
            from_name=body.from_name,
            reply_to=body.reply_to,
            segment_id=body.segment_id,
        )
        if body.template_id is not None:
            await client.set_campaign_content(campaign.id, template_id=body.template_id)
    return _campaign_out(campaign)


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: str,
    client_record=Depends(_require_client),
) -> CampaignOut:
    client, _record = client_record
    async with translate_mailchimp_errors():
        campaign = await client.get_campaign(campaign_id)
    return _campaign_out(campaign)


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: str,
    body: CampaignPatchBody,
    client_record=Depends(_require_client),
) -> CampaignOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        campaign = await client.update_campaign(
            campaign_id,
            title=body.title,
            subject_line=body.subject_line,
            preview_text=body.preview_text,
            from_name=body.from_name,
            reply_to=body.reply_to,
            segment_id=body.segment_id,
        )
    return _campaign_out(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    client_record=Depends(_require_client),
) -> Response:
    client, _record = client_record
    async with translate_mailchimp_errors():
        await client.delete_campaign(campaign_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{campaign_id}/actions/send", response_model=CampaignOut)
async def send_campaign(
    campaign_id: str,
    client_record=Depends(_require_client),
) -> CampaignOut:
    client, _record = client_record
    async with translate_mailchimp_errors():
        await client.send_campaign(campaign_id)
        campaign = await client.get_campaign(campaign_id)
    return _campaign_out(campaign)


@router.post("/{campaign_id}/actions/schedule", response_model=CampaignOut)
async def schedule_campaign(
    campaign_id: str,
    body: CampaignScheduleBody,
    client_record=Depends(_require_client),
) -> CampaignOut:
    client, _record = client_record
    async with translate_mailchimp_errors():
        await client.schedule_campaign(campaign_id, schedule_time=body.schedule_time)
        campaign = await client.get_campaign(campaign_id)
    return _campaign_out(campaign)


@router.post("/{campaign_id}/actions/unschedule", response_model=CampaignOut)
async def unschedule_campaign(
    campaign_id: str,
    client_record=Depends(_require_client),
) -> CampaignOut:
    client, _record = client_record
    async with translate_mailchimp_errors():
        await client.unschedule_campaign(campaign_id)
        campaign = await client.get_campaign(campaign_id)
    return _campaign_out(campaign)


@router.post("/{campaign_id}/actions/test")
async def test_campaign(
    campaign_id: str,
    body: CampaignTestBody,
    client_record=Depends(_require_client),
) -> dict:
    client, _record = client_record
    async with translate_mailchimp_errors():
        await client.send_test(campaign_id, test_emails=body.emails)
    return {"ok": True}
