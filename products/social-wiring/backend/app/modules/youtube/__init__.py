"""``youtube`` — social-wiring product module (Phase 8).

Folds the W2.1-era app-level YouTube footprint (uploads, videos cache,
dashboard, YouTube OAuth tab, the DownloadCache for Drive-staged uploads)
into a self-contained module mirroring ``modules/email_marketing`` and
``modules/scheduling``. Resolves the Phase 0 app-level-vs-``modules/``
asymmetry: after Phase 8 every product-domain surface lives under
``app/modules/<domain>/`` and ``app/routers/`` only holds cross-domain
routers (settings non-youtube tabs, whatsapp inbound, chat, calendar,
google, meta, intake-monitor).

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables, each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Adding it to the app is a single ``MODULES`` append in ``main.py`` (no
assembly-logic edit) — same shape as W2.2/W2.3.

What ``register()`` does
────────────────────────
Returns the module's routers — videos, upload, dashboard, plus the
YouTube tab + OAuth callback routers from the split ``routers/settings``.
Standard-router fan-in is empty (this module needs no extra seed
``standard_routers`` beyond the W2.1 base set).

Routes preserved
────────────────
The external URL surface is unchanged pre/post-modularization:
  - ``/api/videos/*``                   (videos.router)
  - ``/api/videos/upload/*``            (upload.router)
  - ``/api/dashboard/*``                (dashboard.router)
  - ``/api/settings/youtube/*``         (settings.router — same /api/settings prefix)
  - ``/api/youtube/oauth/callback``     (settings.oauth_router — same /api/youtube/oauth prefix)
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Imported and invoked by the ``main.py`` assembly loop. ``app.main``
    is already imported by the time the loop runs, so importing
    ``ModuleRegistration`` here is not circular.

    Also calls ``youtube.scheduler.configure()`` to register the daily
    snapshot job on the seed scheduler (same pattern as email_marketing).
    """
    from app.modules.youtube.routers import (
        dashboard,
        settings as yt_settings,
        upload,
        videos,
        snapshot as yt_snapshot,
    )
    from app.modules.youtube.scheduler import configure as _configure_scheduler
    from app.main import ModuleRegistration

    # Register scheduler jobs before the lifespan starts the scheduler.
    _configure_scheduler()

    return ModuleRegistration(
        routers=[
            videos.router,
            upload.router,
            dashboard.router,
            yt_settings.router,
            yt_settings.oauth_router,
            yt_snapshot.router,
        ],
        # No extra standard routers — the W2.1 base set (health /
        # notificacoes / team) covers everything the YouTube surface
        # needs at the seed-router level.
        standard_routers=(),
    )


__all__ = ["register"]
