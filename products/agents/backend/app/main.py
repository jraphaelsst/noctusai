"""
NoctusAI Agentes — the Julia control-plane API (G1b: HTTP + SSE).

Contract: ``projects/julia-agents-academia-CONTRACT.md`` §E. Mounts the
unified auth router directly (NOT via ``standard_routers=["auth"]`` — that
registry entry has no seam for this product's real ``SupabaseApiTokenResolver``
/ legacy-JWT bridge; mirrors ``products/social-wiring/backend/app/main.py``'s
documented reason) plus the four G1b routers (agents / persona /
conversations+SSE / approvals).

``app/runtime/`` (G2) is NOT imported here — every route that needs it
resolves the runtime/broker lazily via ``app/dependencies.py``'s
``get_agent_runtime_dep`` / ``get_approval_broker_dep`` /
``get_build_julia_spec_dep``. The one exception is the startup hook below,
which needs the broker to expire orphaned approvals (contract §E.2
"Startup") — wrapped so a missing ``app.runtime`` degrades to a logged
warning, never a boot failure (``KB § PATTERNS/backend/
startup-hook-must-not-be-fatal.md``).
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from noctusai_seed import create_product_app
from noctusai_seed.auth_router import create_auth_router

from app.config import settings
from app.dependencies import (
    _LazyApiTokenResolver,
    _legacy_jwt_resolver,
    auth_router_deps,
)
from app.exceptions import agents_http_exception_handler
from app.rate_limit import limiter
from app.routers.agents_router import router as agents_router
from app.routers.approvals_router import router as approvals_router
from app.routers.conversations_router import router as conversations_router
from app.routers.persona_router import router as persona_router

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
    instances' rows (security finding 5). No-op with a loud warning when
    `app.runtime` (G2) hasn't landed yet."""
    try:
        from app.dependencies import get_approval_broker_dep

        broker = get_approval_broker_dep()
    except ModuleNotFoundError:
        logger.warning(
            "agents.startup.runtime_not_available — app.runtime is not built yet "
            "(G2); skipping the orphaned-approval expiry sweep this boot."
        )
        return
    expired = await broker.expire_orphans_on_startup()
    logger.info("agents.startup.expired_orphan_approvals count=%s", expired)


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
    # Contract §D / §E.5: the approval-assertion signing key + the
    # social-wiring bridge token must both be set in a deploy context —
    # an unset key would silently disable the whole escrita-approval
    # flow's ability to ever call academia (§D), and would let the
    # product boot with no way to reach social-wiring's One Chat bridge.
    required_prod_config=["APPROVAL_ASSERTION_SECRETS", "SOCIAL_WIRING_API_TOKEN"],
)

# Contract §0 error envelope — see app/exceptions.py's module docstring for
# the seed-defect this closes (structured HTTPException.detail dicts, e.g.
# require_scopes's scope_missing/role_missing, were silently flattened by
# the seed's generic handler). Registered AFTER create_product_app so it
# replaces (not stacks on) the seed's default HTTPException handler.
app.add_exception_handler(HTTPException, agents_http_exception_handler)
