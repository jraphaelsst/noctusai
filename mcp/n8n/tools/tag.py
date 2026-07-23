"""n8n.tag.* tools — workflow tag catalog.

PURE read: list. Tag *assignment* to a workflow is
`n8n.workflow.set_tags` (a workflow-scoped write, lives in
`tools/workflow.py`); this leaf is the read side that surfaces the
tag-id ↔ name mapping `set_tags` needs.

Thin MCP Out shaping over `client.get_client().list_tags()` — the
seed already returns typed `Tag` value objects, so there is no raw
dict to hand-parse here at all (see `mcp/n8n/tools/workflow.py`'s
module docstring for the shared DI-seam shape).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.n8n import N8nError

from .. import api
from ..client import get_client
from ..types import TagListInput, TagListOutput, TagSummary

logger = logging.getLogger(__name__)


async def tag_list(args: dict) -> dict:
    inp = TagListInput(**args)
    try:
        client = get_client()
        tags = await client.list_tags()
    except (api.N8nApiError, N8nError) as e:
        return TagListOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    return TagListOutput(
        tags=[TagSummary(id=t.id, name=t.name) for t in tags][: inp.limit],
        next_cursor=None,
    ).model_dump()


HANDLERS = {"n8n.tag.list": tag_list}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="n8n.tag.list",
            description="List workflow tags (id ↔ name; feed ids to "
            "n8n.workflow.set_tags). READ-ONLY.",
            inputSchema=TagListInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
