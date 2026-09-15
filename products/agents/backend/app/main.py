"""
NoctusAI Agentes — the Julia control-plane API (G1b: HTTP + SSE).

Contract: ``projects/julia-agents-academia-CONTRACT.md`` §E. Mounts the
unified auth router directly (NOT via ``standard_routers=["auth"]`` — that
registry entry has no seam for this product's real ``SupabaseApiTokenResolver``
/ legacy-JWT bridge; mirrors ``products/social-wiring/backend/app/main.py``'s
documented reason) plus the four G1b routers (agents / persona /
conversations+SSE / approvals).

``app/runtime/`` (G2) is a hard dependency of the routers (``TurnContext``
/ ``Orphaned`` are imported at module level — both are lightweight,
``claude_agent_sdk``-free). The runtime/broker/spec-builder INSTANCES are
still resolved lazily via ``app/dependencies.py``'s ``get_agent_runtime_dep``
/ ``get_approval_broker_dep`` / ``get_build_julia_spec_dep`` — deferring
the real runtime's conditional SDK import to first use, not because the
package might be absent. The startup hook below (contract §E.2 "Startup",
extended by §E.11 "Every slot is swept once at startup") is wrapped by
the seed's own ``lifespan_startup`` contract so a hook failure degrades to
a logged warning, never a boot failure
(``KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md``).

**Health seam (contract §E.11 "Any failure quarantines K ... /api/health
reports degraded"):** the seed's bundled ``standard_routers=["health"]``
``/api/health`` route has no hook seam — it surfaces exactly one signal
(``startup_hook_error``) and never forks. The seed's SUPPORTED extension
point for additional signals is ``health_config=HealthEndpointConfig(...)``
(``noctusai_seed.health``), which mounts ``/_health`` (liveness) +
``/_ready`` (readiness). The slot pool's ``health()`` is a fast,
network-free, in-memory check — liveness, not readiness — so it is wired
below as a ``liveness_hooks`` entry on ``/_health``, never a fork of
``/api/health``.
"""
from __future__ import annotations

import logging

from noctusai_seed import HealthEndpointConfig, create_product_app
from noctusai_seed.auth_router import create_auth_router

from app.config import settings
from app.dependencies import (
    _LazyApiTokenResolver,
    _legacy_jwt_resolver,
    auth_router_deps,
)
from app.rate_limit import limiter
from app.routers.agents_router import router as agents_router
from app.routers.approvals_router import router as approvals_router
from app.routers.conversations_router import router as conversations_router
from app.routers.persona_router import router as persona_router
from app.runtime.slots import get_slot_pool

logger = logging.getLogger(__name__)

# ONE combined router (`/api/auth` + `/api/settings/api-tokens`) — built
# directly via the factory (not `standard_routers=["auth"]`) so `pk_*` /
# legacy-JWT callers resolve through THIS product's real composition
# instead of the registry's bare `FakeApiTokenResolver()` default. See
# module docstring + `products/social-wiring/backend/app/main.py` for the
# pattern this mirrors.
_auth_router = create_auth_router(
    auth_router_deps,
    settings,
    api_token_resolver=_LazyApiTokenResolver(),
    legacy_jwt_resolver=_legacy_jwt_resolver,
)


async def on_startup() -> None:
    """Contract §E.2 "Startup": every `pendente` approval row whose
    `instance_id` equals THIS instance becomes `expirada` — never other
    instances' rows (security finding 5). Then contract §E.11 "Every slot
    is swept once at startup": kill+sweep+unlink every non-quarantined
    slot before serving a single turn."""
    from app.dependencies import get_approval_broker_dep

    broker = get_approval_broker_dep()
    expired = await broker.expire_orphans_on_startup()
    logger.info("agents.startup.expired_orphan_approvals count=%s", expired)

    slot_pool = get_slot_pool(settings)
    await slot_pool.sweep_all_on_startup()
    logger.info("agents.startup.slot_pool_swept health=%s", slot_pool.health())


async def _slot_pool_health() -> tuple[bool, str | None]:
    """Liveness hook (contract §E.11): degrades `/_health` — never
    `/api/health`, which has no hook seam (see module docstring) — when
    any slot is quarantined. Fast + network-free: reads the in-process
    `SlotPool.health()` dict only."""
    health = get_slot_pool(settings).health()
    quarantined = health.get("quarantined") or []
    if quarantined:
        return False, f"slots quarantined: {quarantined}"
    return True, None


app = create_product_app(
    name="Agentes",
    schema="agents",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[
        _auth_router,
        agents_router,
        persona_router,
        conversations_router,
        approvals_router,
    ],
    lifespan_startup=on_startup,
    health_config=HealthEndpointConfig(liveness_hooks=[_slot_pool_health]),
    # Contract §D / §E.5: the approval-assertion signing key + the
    # social-wiring bridge token must both be set in a deploy context —
    # an unset key would silently disable the whole escrita-approval
    # flow's ability to ever call academia (§D), and would let the
    # product boot with no way to reach social-wiring's One Chat bridge.
    required_prod_config=["APPROVAL_ASSERTION_SECRETS", "SOCIAL_WIRING_API_TOKEN"],
)
