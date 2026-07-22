"""``leads`` — social-wiring product module for the Leads surface.

Slice A of the Leads module (``leads-module-PROJECT.md``). Turns the
29-sheet "CONTROLE LEADS" spreadsheet import into a managed CRUD +
analytics + import surface at ``/api/leads/*``.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Adding it to the app:

    from app.modules.leads import register as _leads
    MODULES = [..., _leads]

What ``register()`` does
─────────────────────────
Returns the five Leads routers (leads CRUD+facets, analytics, sources,
corretores, import) under ``/api/leads/...``. No ``standard_routers``
needed beyond what the existing MODULES already request.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.modules.leads.routers import (
        analytics,
        corretores,
        imports,
        leads,
        sources,
    )
    from app.main import ModuleRegistration

    return ModuleRegistration(
        # `leads.router` owns a catch-all `GET/PATCH/DELETE /{lead_id}`
        # under the SAME `/api/leads` prefix every other sub-router here
        # mounts under (`/api/leads/sources`, `/api/leads/analytics`,
        # `/api/leads/import`) — FastAPI/Starlette tries routers in
        # registration order, so `leads.router` MUST be listed LAST or
        # e.g. `GET /api/leads/sources` gets caught by `/{lead_id}` and
        # 422s trying to parse "sources" as a UUID (found exactly this
        # way while building this module's test suite).
        routers=[
            analytics.router,
            sources.router,
            corretores.router,
            imports.router,
            leads.router,
        ],
        standard_routers=(),
    )


__all__ = ["register"]
