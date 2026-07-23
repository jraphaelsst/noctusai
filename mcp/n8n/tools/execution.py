"""n8n.execution.* tools — execution history + failure diagnosis.

PURE reads (no confirm gate): list / get. This is the debugging core —
`list` (filter workflow_id + status="error") finds recent failures,
`get` pulls the full run payload of one so the actual error is visible.

Thin MCP In/Out shaping over `client.get_client()` — see
`mcp/n8n/tools/workflow.py`'s module docstring for the shared DI-seam
shape. `_extract_error` stays connector-side: it's presentation logic
specific to this tool's `error_summary` Output field, not a
generalizable seed concern.
"""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.n8n import Execution, N8nError

from .. import api
from ..client import get_client
from ..types import (
    ExecutionDeleteInput,
    ExecutionDeleteOutput,
    ExecutionGetInput,
    ExecutionGetOutput,
    ExecutionListInput,
    ExecutionListOutput,
    ExecutionSummary,
)

logger = logging.getLogger(__name__)


def _summary(e: Execution) -> ExecutionSummary:
    return ExecutionSummary(
        id=e.id,
        finished=e.finished,
        mode=e.mode,
        status=e.status,
        retryOf=e.retry_of,
        startedAt=e.started_at.isoformat() if e.started_at else None,
        stoppedAt=e.stopped_at.isoformat() if e.stopped_at else None,
        workflowId=e.workflow_id,
    )


def _extract_error(execution: dict) -> Optional[dict]:
    """Best-effort pull of the failing node + error from n8n run-data.

    n8n nests the error at `data.resultData.error` and/or per-node at
    `data.resultData.runData[<node>][0].error`. Shape is
    version-dependent, so this is *best-effort* — returns None (never a
    fabricated value) when nothing recognizable is found; the caller
    keeps the raw `execution` as the source of truth.
    """
    if not isinstance(execution, dict):
        return None
    result = (
        execution.get("data", {}).get("resultData", {})
        if isinstance(execution.get("data"), dict) else {}
    )
    if not isinstance(result, dict):
        return None

    def _shape(err: dict, node: Optional[str]) -> dict:
        return {
            "node": node or err.get("node", {}).get("name")
            if isinstance(err.get("node"), dict) else node,
            "name": err.get("name"),
            "message": err.get("message"),
            "description": err.get("description"),
            "stack": (err.get("stack") or "")[:2000] or None,
        }

    top = result.get("error")
    if isinstance(top, dict):
        return _shape(top, result.get("lastNodeExecuted"))

    run_data = result.get("runData")
    if isinstance(run_data, dict):
        for node, runs in run_data.items():
            if not isinstance(runs, list):
                continue
            for run in runs:
                if isinstance(run, dict) and isinstance(run.get("error"), dict):
                    return _shape(run["error"], node)
    return None


async def execution_list(args: dict) -> dict:
    inp = ExecutionListInput(**args)
    try:
        client = get_client()
        executions = await client.list_executions(
            workflow_id=inp.workflow_id, status=inp.status, limit=inp.limit
        )
    except (api.N8nApiError, N8nError) as e:
        return ExecutionListOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    return ExecutionListOutput(
        executions=[_summary(e) for e in executions],
        next_cursor=None,
    ).model_dump()


async def execution_get(args: dict) -> dict:
    inp = ExecutionGetInput(**args)
    try:
        client = get_client()
        execution = await client.get_execution(inp.id, include_data=inp.include_data)
    except (api.N8nApiError, N8nError) as e:
        return ExecutionGetOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    execution = execution if isinstance(execution, dict) else None
    return ExecutionGetOutput(
        execution=execution,
        error_summary=_extract_error(execution) if execution else None,
    ).model_dump()


async def execution_delete(args: dict) -> dict:
    inp = ExecutionDeleteInput(**args)
    if not inp.confirm:
        return ExecutionDeleteOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.execution.delete")
            )
        ).model_dump()
    try:
        client = get_client()
        await client.delete_execution(inp.id)
    except (api.N8nApiError, N8nError) as e:
        return ExecutionDeleteOutput(
            id=inp.id, error=typed_error(api.map_seed_error(e))
        ).model_dump()
    return ExecutionDeleteOutput(id=inp.id, deleted=True).model_dump()


HANDLERS = {
    "n8n.execution.list": execution_list,
    "n8n.execution.get": execution_get,
    "n8n.execution.delete": execution_delete,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="n8n.execution.list",
            description="List executions newest-first (filter workflow_id "
            "+ status='error' to find recent failures). READ-ONLY.",
            inputSchema=ExecutionListInput.model_json_schema(),
        ),
        Tool(
            name="n8n.execution.get",
            description="Fetch one execution with full run-data — the "
            "failure-diagnosis core. Returns the raw execution plus a "
            "best-effort `error_summary` (node/name/message/stack). "
            "READ-ONLY.",
            inputSchema=ExecutionGetInput.model_json_schema(),
        ),
        Tool(
            name="n8n.execution.delete",
            description="Delete one execution record (history cleanup). "
            "WRITE — confirm-gated (status 412 without confirm=true).",
            inputSchema=ExecutionDeleteInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
