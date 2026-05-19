"""n8n.tag.* tools — workflow tag catalog.

PURE read: list. Tag *assignment* to a workflow is
`n8n.workflow.set_tags` (a workflow-scoped write, lives in
`tools/workflow.py`); this leaf is the read side that surfaces the
tag-id ↔ name mapping `set_tags` needs.

Routes through the single `api.request_json` HTTP seam (tests patch
`n8n.api.request_json`). API failure ⇒ a typed-error envelope, never a
fabricated success.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import TagListInput, TagListOutput, TagSummary

logger = logging.getLogger(__name__)


def _ctx() -> dict:
    s = get_settings()
    return {
        "base_url": s.base_url or "",
        "api_key": s.api_key or "",
        "timeout": s.timeout_seconds,
    }


async def tag_list(args: dict) -> dict:
    inp = TagListInput(**args)
    try:
        data = api.request_json(
            "GET", "/tags", params={"limit": inp.limit}, **_ctx()
        )
    except api.N8nApiError as e:
        return TagListOutput(error=typed_error(e)).model_dump()
    items = (data or {}).get("data", []) if isinstance(data, dict) else []
    return TagListOutput(
        tags=[
            TagSummary(id=str(d.get("id", "")), name=d.get("name", ""))
            for d in items
            if d.get("id")
        ],
        next_cursor=(data or {}).get("nextCursor")
        if isinstance(data, dict) else None,
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
