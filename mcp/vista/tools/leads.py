"""vista.leads.* — push an inbound lead into the agency's CRM (`POST /lead`).

Supersedes the old "there is no API path to write a lead back into Vista"
conclusion (vista.md § 4.2 retraction): the route is top-level `/lead`, not
`/clientes/lead`, and key `…644c` is PERMITTED on it (empty-POST probe,
2026-09-16). The payload contract was derived on Vista's public sandbox —
never by writing to the live CRM.

🔴 A write to a live system. Refuses unless `VISTA_MCP_ALLOW_WRITES` is set.
LGPD: this sends a third party's personal data to the agency's CRM; the
caller must hold a legal basis for it.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.vista import (
    VistaConfigError,
    VistaTimeout,
    VistaUpstreamError,
)

from ..types import SubmitLeadInput, WriteOutput
from ._common import WritesDisabled, client, require_writes_enabled, typed_error

_HANDLED = (WritesDisabled, ValueError, VistaConfigError, VistaTimeout, VistaUpstreamError)


async def submit_lead(args: dict) -> dict:
    inp = SubmitLeadInput(**args)
    lead = inp.model_dump(exclude_none=True)
    try:
        require_writes_enabled()
        result = await client().enviar_lead(lead)
    except _HANDLED as e:
        return WriteOutput(typed_error=typed_error(e)).model_dump()
    data = result.data if isinstance(result.data, dict) else {"raw": result.data}
    return WriteOutput(result=data, http_status=result.status).model_dump()


HANDLERS = {"vista.leads.submit": submit_lead}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.leads.submit",
            description=(
                "✍️ WRITE — create/attach an inbound lead in the agency's LIVE "
                "Vista CRM (`POST /lead`). Requires nome, mensagem, veiculo "
                "(lead source) and email or fone. Vista de-duplicates: an "
                "existing client answers 'O cadastro foi encontrado.' instead "
                "of 'Ok.'; both return Codigo (client id) and Corretor (the "
                "assigned broker). Disabled unless the server runs with "
                "VISTA_MCP_ALLOW_WRITES=1. Only call this for a real lead the "
                "user asked to register — it is personal data (LGPD)."
            ),
            inputSchema=SubmitLeadInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
