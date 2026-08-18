"""`olx.leads.*` — the OUTBOUND Gestor de Leads surface.

One tool. It is small but load-bearing: `POST /v1/addLeads` is the only
authenticated endpoint OLX exposes to us, so it is the only way to prove
a key actually works before homologation traffic starts. Gate 1 leans on
it for exactly that.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.olx import OlxError

from .. import api
from ..client import get_client
from ..types import LeadsPushInput, LeadsPushOutput

logger = logging.getLogger(__name__)


async def push(args: dict) -> dict:
    parsed_args = LeadsPushInput(**args)
    try:
        if not parsed_args.confirm:
            raise api.ConfirmationRequiredError(
                "olx.leads.push",
                "sends a REAL lead into the client's OLX Gestor de Leads inbox",
            )
        client = get_client()
        response = await client.push_lead(
            lead_name=parsed_args.lead_name,
            lead_email=parsed_args.lead_email,
            lead_telephone=parsed_args.lead_telephone,
            message=parsed_args.message,
            external_id=parsed_args.external_id,
            business_type=parsed_args.business_type,
            broker_email=parsed_args.broker_email,
            lead_origin=parsed_args.lead_origin,
        )
        return LeadsPushOutput(pushed=True, response=response).model_dump()
    except (api.OlxApiError, OlxError, ValueError) as exc:
        # ValueError is the SALE/RENTAL-vs-SELL/RENT guard — a real
        # mistake to make, given the inbound webhook uses the other pair.
        return LeadsPushOutput(
            pushed=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


HANDLERS = {"olx.leads.push": push}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="olx.leads.push",
            description=(
                "Send a lead INTO the client's OLX Gestor de Leads inbox "
                "(POST /v1/addLeads). WRITE — requires confirm=true. Note "
                "business_type is SALE/RENTAL here, NOT the SELL/RENT the "
                "inbound webhook uses; the vendor is inconsistent across its "
                "own surfaces and the wrong value is rejected loudly. This is "
                "the only authenticated endpoint OLX exposes, so it is also "
                "the only live proof that a key works."
            ),
            inputSchema=LeadsPushInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
