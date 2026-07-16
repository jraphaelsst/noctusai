"""``n8n`` — social-wiring product module (n8n-workflows-page S3).

Consumes the seed n8n adapter (``noctusai_lib.integrations.n8n`` —
Protocol + Fake + Real + factory, shipped by the sibling
``feat/n8n-seed-adapter`` slice this branch is stacked on) to expose
the per-client workflow-management surface: list/assign/rename/toggle/
delete/run workflows, tags, executions, folder tree, and the
Settings-tab credential + client-tag configuration.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables,
each returning a ``ModuleRegistration``. This module exposes
:func:`register`. Wiring it into the app is a single ``MODULES``
append in ``main.py`` at integration time (deliberately NOT done by
this slice — a peer branch is live in ``app/main.py`` concurrently;
the tech-lead registers this module when merging both).

What ``register()`` does
────────────────────────
Returns this module's three routers (workflows+tags, settings,
folders) — all mounted under the ``/api/n8n`` prefix. No extra
``standard_routers`` beyond the product's base set.

Routes
──────
    GET/POST/PATCH/DELETE  /api/n8n/workflows*     (routers/workflows.py)
    GET/POST               /api/n8n/tags           (routers/workflows.py)
    GET/PUT                /api/n8n/settings       (routers/settings.py)
    GET/POST/PATCH/DELETE  /api/n8n/folders*       (routers/folders.py)
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Imported and invoked by the ``main.py`` assembly loop. ``app.main``
    is already imported by the time the loop runs, so importing
    ``ModuleRegistration`` here is not circular (same pattern as
    ``app.modules.youtube.register``).
    """
    from app.main import ModuleRegistration
    from app.modules.n8n.routers import folders, settings, workflows

    return ModuleRegistration(
        routers=[
            workflows.router,
            settings.router,
            folders.router,
        ],
        standard_routers=(),
    )


__all__ = ["register"]
