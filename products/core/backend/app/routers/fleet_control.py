"""Fleet Control — platform-admin panel to switch product containers ON/OFF
and read live status.

Control-plane surface: the Core container shares its host's docker socket
(compose bind-mount; see products/core/docker-compose.yml) so the SAME code
operates the dev laptop and the production VPS. ALL container-control logic is
in the seed primitive ``noctusai_lib.domain.fleet_control`` — this router is a
thin admin-gated HTTP shell over ``get_fleet_controller()``; zero per-product
code.

Security: every endpoint is gated by core's platform-admin dependency
(``get_current_admin``). The state-changing endpoint additionally inherits the
seed's HARD ALLOWLIST — verb ∈ {start, stop, restart} AND slug ∈ registered
products — which raises ``FleetControlError`` (→ 400) before any docker is
shelled. The verb path-param is a ``Literal`` enum so an unknown verb is a 422
at the framework boundary (never reaches the controller).

Read (status) is free for admins; start/stop/restart are mutations.
"""
from __future__ import annotations

import logging
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_admin
from noctusai_lib.config.cors_registry import parse_products_registry
from noctusai_lib.domain.fleet_control import (
    ContainerController,
    FleetControlError,
    get_fleet_controller,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fleet", tags=["Admin · Fleet Control"])


class FleetVerb(str, Enum):
    """The ONLY actions exposed — anything else is a 422 at the boundary."""

    start = "start"
    stop = "stop"
    restart = "restart"


def get_controller() -> ContainerController:
    """FastAPI dependency that resolves the active fleet controller.

    A real DI seam: tests override THIS via ``app.dependency_overrides`` to
    inject the seed Fake (never monkeypatching our own symbols). Production
    resolves Real-vs-Fake by the docker-socket auto-detect in the seed factory.
    """
    return get_fleet_controller()


def _display_names() -> dict[str, str]:
    """slug → display name, from the start.sh registry (single source of truth)."""
    return {e["slug"]: e["display"] for e in parse_products_registry()}


@router.get("")
async def list_fleet(
    admin=Depends(get_current_admin),
    controller: ContainerController = Depends(get_controller),
) -> dict:
    """Live status of every registered product container, joined with display
    names from the product registry. Admin-only, read-only.
    """
    names = _display_names()
    products = []
    for st in controller.status():
        d = st.as_dict()
        d["display"] = names.get(st.slug, st.slug)
        products.append(d)
    return {"products": products, "count": len(products)}


@router.post("/{slug}/{verb}")
async def act_on_product(
    slug: str,
    verb: FleetVerb,
    admin=Depends(get_current_admin),
    controller: ContainerController = Depends(get_controller),
) -> dict:
    """start / stop / restart the ``noctus-<slug>`` container. Admin-only.

    ``verb`` is constrained to the :class:`FleetVerb` enum (bad verb → 422).
    ``slug`` is validated against the registered-product set inside the seed
    controller — an unregistered/malformed slug raises ``FleetControlError``,
    mapped here to 400, before any docker command is built.
    """
    try:
        result = controller.act(slug, verb.value)
    except FleetControlError as exc:
        logger.warning("fleet_control: rejected act slug=%s verb=%s: %s", slug, verb.value, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    if not result.ok:
        # The container exists/is-known but docker reported a failure (e.g.
        # already-stopped, missing image). Surface it, don't swallow.
        raise HTTPException(status_code=502, detail=result.message)
    return result.as_dict()
