"""Mailing AI wrappers router — M1/M2/M5/M6/M7 from ai-expansion Phase 14
and M3 contact segmentation from Phase 8."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from noctusai_lib.ai import AIOutput, consent_required, persist_output
from noctusai_lib.responses import success_response

from app.dependencies import get_current_user, get_org_id, get_user_client
from app.services import ai_service
from app.services import segmentation_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI"])


class SubjectsRequest(BaseModel):
    campaign_summary: str


class TemplateDraftRequest(BaseModel):
    prompt: str


class ReengagementRequest(BaseModel):
    context: str


class DeliverabilityRequest(BaseModel):
    html: str
    subject: Optional[str] = None


class TranslationRequest(BaseModel):
    html: str
    target_lang: str  # "en" | "es" | "fr"


@router.post("/subjects")
async def generate_subjects_endpoint(
    body: SubjectsRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.subject_gen")),
):
    """M1 — generate 3–5 subject-line variants with tone labels."""
    user, _ = await get_current_user(authorization)
    variants = await ai_service.generate_subjects(
        body.campaign_summary, org_id=get_org_id(user)
    )
    return success_response({"variants": variants})


@router.post("/template-draft")
async def template_draft_endpoint(
    body: TemplateDraftRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.template_draft")),
):
    """M2 — draft an HTML email body from a prompt."""
    user, _ = await get_current_user(authorization)
    html = await ai_service.draft_template(body.prompt, org_id=get_org_id(user))
    return success_response({"html": html})


@router.post("/reengagement")
async def reengagement_endpoint(
    body: ReengagementRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.reengagement_variants")),
):
    """M5 — 3 re-engagement email variants (leve/direto/valor)."""
    user, _ = await get_current_user(authorization)
    variants = await ai_service.reengagement_variants(body.context, org_id=get_org_id(user))
    return success_response({"variants": variants})


@router.post("/deliverability")
async def deliverability_endpoint(
    body: DeliverabilityRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.deliverability_review")),
):
    """M6 — review HTML for spam/deliverability issues. Returns `{findings: [...]}`."""
    user, _ = await get_current_user(authorization)
    result = await ai_service.review_deliverability(
        body.html, subject=body.subject, org_id=get_org_id(user)
    )
    return success_response(result)


@router.post("/translate")
async def translate_endpoint(
    body: TranslationRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.translate")),
):
    """M7 — translate PT HTML email to EN/ES/FR preserving template structure."""
    user, _ = await get_current_user(authorization)
    translated = await ai_service.translate_template(
        body.html, body.target_lang, org_id=get_org_id(user)
    )
    return success_response({"html": translated})


# ---------------------------------------------------------------------------
# M3 — Contact segmentation (ai-expansion Phase 8)
# ---------------------------------------------------------------------------


class SegmentRequest(BaseModel):
    list_id: Optional[str] = None  # if absent: segment ALL active contacts of the org
    threshold: Optional[float] = None
    max_segments: Optional[int] = None


@router.post("/segment-contacts")
async def segment_contacts_endpoint(
    body: SegmentRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.segment_contacts")),
):
    """M3 — embed + cluster contacts, name segments via LLM, persist one
    `<AIIndicator/>` row per contact to `mailing.ai_outputs`. Returns the
    persisted rows so the caller can update the UI immediately.
    """
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_user_client(token)

    # 1. Fetch contacts (RLS-scoped via the user-token-bound client).
    if body.list_id:
        member_res = (
            db.table("contact_list_members")
            .select("contact_id")
            .eq("list_id", body.list_id)
            .limit(500)
            .execute()
        )
        if not member_res.data:
            raise HTTPException(
                status_code=404,
                detail="Lista vazia ou inexistente — não há contatos para segmentar.",
            )
        contact_ids = [m["contact_id"] for m in member_res.data]
        contact_res = (
            db.table("contacts")
            .select("id, email, nome, empresa, tags, custom_fields")
            .in_("id", contact_ids)
            .eq("status", "active")
            .execute()
        )
    else:
        contact_res = (
            db.table("contacts")
            .select("id, email, nome, empresa, tags, custom_fields")
            .eq("status", "active")
            .limit(500)
            .execute()
        )
    contacts = contact_res.data or []

    if not contacts:
        return success_response({"persisted": [], "segmented": 0})

    # 2. Run the segmentation pipeline.
    threshold = body.threshold if body.threshold is not None else segmentation_service.DEFAULT_THRESHOLD
    max_segments = (
        body.max_segments if body.max_segments is not None else segmentation_service.DEFAULT_MAX_SEGMENTS
    )
    outputs = await segmentation_service.segment_contacts(
        contacts=contacts,
        threshold=threshold,
        max_segments=max_segments,
        org_id=org_id,
    )

    # 3. Persist N rows — one per contact.
    persisted: list[dict] = []
    for o in outputs:
        contact_id = o.pop("_contact_id")
        try:
            output = AIOutput(
                ref_type="contact",
                ref_id=contact_id,
                kind=o["kind"],
                label=o["label"],
                score=o.get("score"),
                chip=o.get("chip"),
                explanation=o.get("explanation"),
                confidence=o.get("confidence"),
                model_version=o.get("model_version"),
                prompt_version=o.get("prompt_version"),
                metadata=o.get("metadata") or {},
            )
            persisted.append(persist_output(db, schema="mailing", output=output))
        except Exception as e:
            logger.warning(
                "mailing.segment_contacts persist failed for contact %s: %s",
                contact_id,
                e,
            )

    return success_response({"persisted": persisted, "segmented": len(persisted)})


# ---------------------------------------------------------------------------
# M4 — Campaign debrief (ai-expansion Phase 12)
# ---------------------------------------------------------------------------


class CampaignDebriefRequest(BaseModel):
    recipient: str


@router.get("/campaigns/{campaign_id}/debrief")
async def campaign_debrief_preview_endpoint(
    campaign_id: str,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.campaign_debrief")),
):
    """M4 — build the post-send debrief for a campaign. Returns body +
    structured summary (no email send). Used by the campaign detail page."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_user_client(token)

    from app.services import campaign_debrief_service
    built = await campaign_debrief_service.build_debrief(
        db, campaign_id=campaign_id, org_id=org_id
    )
    if built is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    digest, summary = built
    return success_response({
        "subject": digest.subject,
        "html": digest.html,
        "text": digest.text,
        "summary": summary,
    })


@router.post("/campaigns/{campaign_id}/debrief/send")
async def campaign_debrief_send_endpoint(
    campaign_id: str,
    body: CampaignDebriefRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("mailing.campaign_debrief")),
):
    """M4 — build + email the post-send debrief. Cron / send-completion
    hook calls this with the campaign creator as recipient."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_user_client(token)

    from app.services import campaign_debrief_service
    result = await campaign_debrief_service.send_campaign_debrief(
        db, campaign_id=campaign_id, recipient=body.recipient, org_id=org_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return success_response(result)
