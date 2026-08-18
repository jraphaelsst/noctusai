"""`imovelweb.agencies.*` — who is authorized to our integration.

One tool, and it is the tenant-resolution key rather than a listing.

An imobiliária authorizes us through the vendor's login button, which we
embed as
`https://loginbr-open.navent.com/[INTEGRADOR]/[CODIGOIMOBILIARIA].js` —
and **we choose `CODIGOIMOBILIARIA`**. Deriving it from the org at
onboarding is what turns tenant resolution into a pure lookup instead of a
guess, and it is the one place this integration is structurally better than
the Grupo OLX pipe, where nothing in the payload names the advertiser.

So this list is the map from vendor code to our org. If a lead arrives
carrying a code that is not here, it parks as `unresolved` rather than
being attributed to somebody — the tenant-leak guard.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.imovelweb import ImovelWebError

from .. import api
from ..client import get_client
from ..settings import get_settings
from ..types import AgenciesListInput, AgenciesListOutput

logger = logging.getLogger(__name__)

_NOTE = (
    "These agency codes are the tenant-resolution key: WE choose them at "
    "onboarding, which is what makes org resolution a pure lookup. A lead "
    "carrying a code that is not in this list must park as `unresolved` — "
    "never be attributed to a best guess."
)


async def list_agencies(args: dict) -> dict:
    parsed_args = AgenciesListInput(**args)
    settings = get_settings()
    try:
        client = get_client()
        page = await client.list_agencies(page=parsed_args.page, size=parsed_args.size)
        page = api.redact(page, settings, client)
        content = page.get("content") or page.get("inmobiliarias") or []
        return AgenciesListOutput(
            listed=True,
            agencies=content,
            page=page.get("number", parsed_args.page),
            size=page.get("size", parsed_args.size),
            total=page.get("total"),
            note=_NOTE,
        ).model_dump()
    except (api.ImovelWebApiError, ImovelWebError) as exc:
        return AgenciesListOutput(
            listed=False, error=typed_error(api.map_seed_error(exc))
        ).model_dump()


HANDLERS = {"imovelweb.agencies.list": list_agencies}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="imovelweb.agencies.list",
            description=(
                "List the imobiliárias authorized to our integration. These "
                "agency codes are chosen by US at onboarding and are the "
                "tenant-resolution key — a lead carrying a code absent from "
                "this list parks as `unresolved` rather than being attributed "
                "to a guess. READ-ONLY."
            ),
            inputSchema=AgenciesListInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
