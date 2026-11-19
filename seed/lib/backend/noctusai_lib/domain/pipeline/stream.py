"""Live pipeline stream — the publish half (`pipeline.card_moved` / `pipeline.card_state`).

Every kanban built on `move_card` gets a live board for free: pass `publish=` and, AFTER the move
commits, one `pipeline.card_moved` frame goes out on scope `pipeline:{org}:{pipeline}` of the existing
`noctusai_lib.realtime` bus. Browser half: `usePipelineStream` (`@noctusai/lib`).

Best-effort by contract: the move is already durable, so a bus failure is logged with context and never
raises into it (clients fall back to polling). It is never silent.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from noctusai_lib.realtime.bus import RealtimeBus

if TYPE_CHECKING:
    from .config import PipelineConfig

logger = logging.getLogger(__name__)

CARD_MOVED_EVENT = "pipeline.card_moved"
CARD_STATE_EVENT = "pipeline.card_state"

#: `publish(event, payload)` — what `move_card(publish=...)` calls after the commit.
PipelinePublisher = Callable[[str, dict[str, Any]], Any]


def pipeline_scope(org_id: str, pipeline: str) -> str:
    """Bus scope of one org's pipeline. Org first: two orgs can never share a scope."""
    return f"pipeline:{org_id}:{pipeline}"


async def _publish(bus: RealtimeBus, org_id: str, pipeline: str, event: str, payload: dict[str, Any]) -> str | None:
    try:
        return await bus.publish(pipeline_scope(org_id, pipeline), event, payload)
    except Exception:
        logger.warning(
            "pipeline publish failed event=%s org=%s pipeline=%s card=%s (clients fall back to polling)",
            event, org_id, pipeline, payload.get("card_id"), exc_info=True,
        )
        return None


async def publish_card_moved(
    bus: RealtimeBus,
    org_id: str,
    pipeline: str,
    *,
    card_id: str,
    from_stage_id: str | None,
    to_stage_id: str,
    motivo: str | None = None,
    actor: str | None = None,
    at: str | None = None,
) -> str | None:
    return await _publish(bus, org_id, pipeline, CARD_MOVED_EVENT, {
        "card_id": card_id,
        "from_stage_id": from_stage_id,
        "to_stage_id": to_stage_id,
        "motivo": motivo,
        "actor": actor,
        "at": at or datetime.now(timezone.utc).isoformat(),
    })


async def publish_card_state(
    bus: RealtimeBus, org_id: str, pipeline: str, card_id: str, state: dict[str, Any]
) -> str | None:
    """Push a card's live sub-state (status line, progress, ...) — merged into the card by the browser."""
    return await _publish(bus, org_id, pipeline, CARD_STATE_EVENT, {"card_id": card_id, "state": dict(state)})


def make_pipeline_publisher(bus: RealtimeBus, org_id: str, pipeline: str) -> PipelinePublisher:
    """A sync `publish` hook for `move_card`, bound to one org + pipeline.

    From a running loop (async route) the publish is scheduled; from a plain thread (sync route in the
    threadpool) it runs to completion on its own loop."""

    def publish(event: str, payload: dict[str, Any]) -> Any:
        coro = _publish(bus, org_id, pipeline, event, payload)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        return loop.create_task(coro)

    return publish


def create_pipeline_stream_router(
    cfg: "PipelineConfig",
    bus: RealtimeBus,
    *,
    auth_dependency: Callable[..., Any],
    org_resolver: Callable[[Any, Any], "str | Awaitable[str]"],
    heartbeat_seconds: float = 15.0,
    path: str = "/",
):
    """`GET <path>` -> `text/event-stream` of ONE org's `cfg.pipeline` board, over `create_sse_router`.

    The org comes ONLY from the authenticated context (`org_resolver(request, auth_ctx)`), never from
    the URL or query, so a caller cannot name another org's scope. `auth_dependency` is REQUIRED:
    unauthenticated -> the dependency's 401."""
    from noctusai_lib.api.access_tiers import make_router
    from noctusai_lib.realtime.sse import create_sse_router

    async def scope_resolver(request: Any, auth_ctx: Any) -> str:
        org_id = org_resolver(request, auth_ctx)
        if inspect.isawaitable(org_id):
            org_id = await org_id
        return pipeline_scope(str(org_id), cfg.pipeline)

    router = make_router(tier="org", guard=auth_dependency)
    router.include_router(
        create_sse_router(
            bus,
            scope_resolver=scope_resolver,
            auth_dependency=auth_dependency,
            heartbeat_seconds=heartbeat_seconds,
            path=path,
        )
    )
    return router
