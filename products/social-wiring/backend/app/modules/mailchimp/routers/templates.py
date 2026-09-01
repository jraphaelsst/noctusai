"""Templates router — /api/mailchimp/templates.

Manages user-owned Mailchimp templates (type=user). The ``edit_url`` is
computed server-side as ``https://{dc}.admin.mailchimp.com/templates/edit?id={id}``
using the seed mapper once slice A ships; until then we compute it inline.

  GET    /templates                  → {items, total}
  POST   /templates                  → TemplateOut (201)
  GET    /templates/{template_id}    → TemplateOut
  PATCH  /templates/{template_id}    → TemplateOut
  DELETE /templates/{template_id}    → 204
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.mailchimp.deps import make_require_mailchimp_client
from app.modules.mailchimp.errors import translate_mailchimp_errors
from app.modules.mailchimp.schemas import (
    TemplateCreateBody,
    TemplateListOut,
    TemplatePatchBody,
    TemplateOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mailchimp/templates", tags=["Mailchimp"])

_require_client = make_require_mailchimp_client(require_audience=False)


def _template_edit_url(server_prefix: str, template_id: int) -> str:
    """Compute the Mailchimp template editor deep-link.

    ``https://{dc}.admin.mailchimp.com/templates/edit?id={id}``

    This is best-effort for drag-and-drop templates too (real API only
    exposes user-created templates with this URL shape). Once slice A
    ships, this can delegate to ``noctusai_lib.integrations.mailchimp.mappers.template_edit_url``.
    """
    return f"https://{server_prefix}.admin.mailchimp.com/templates/edit?id={template_id}"


def _template_out(t, server_prefix: str) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        name=t.name,
        category=t.category,
        type=t.type,
        drag_and_drop=t.drag_and_drop or False,
        preview_image=t.preview_image,
        date_created=t.date_created,
        date_edited=t.date_edited,
        edit_url=_template_edit_url(server_prefix, t.id),
    )


@router.get("", response_model=TemplateListOut)
async def list_templates(
    count: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    client_record=Depends(_require_client),
) -> TemplateListOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        page = await client.list_templates(count=count, offset=offset)
    return TemplateListOut(
        items=[_template_out(t, record.server_prefix) for t in page.items],
        total=page.total,
    )


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreateBody,
    client_record=Depends(_require_client),
) -> TemplateOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        tmpl = await client.create_template(name=body.name, html=body.html)
    return _template_out(tmpl, record.server_prefix)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: int,
    client_record=Depends(_require_client),
) -> TemplateOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        tmpl = await client.get_template(template_id)
    return _template_out(tmpl, record.server_prefix)


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    body: TemplatePatchBody,
    client_record=Depends(_require_client),
) -> TemplateOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        tmpl = await client.update_template(template_id, name=body.name, html=body.html)
    return _template_out(tmpl, record.server_prefix)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    client_record=Depends(_require_client),
) -> Response:
    client, record = client_record
    async with translate_mailchimp_errors():
        await client.delete_template(template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
