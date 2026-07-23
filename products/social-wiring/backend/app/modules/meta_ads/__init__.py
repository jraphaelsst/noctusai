"""``meta_ads`` — social-wiring product module (Meta Ads console, W2-W3).

Read-only console over the operator's own Meta ad account (campaign ->
ad set -> ad hierarchy, daily-snapshot history, an intra-day-accurate
activity change log) built on the seed's Marketing-API read surface
(``noctusai_lib.integrations.meta``, W1). Mirrors
``app/modules/youtube``'s module shape exactly (``register()`` +
``scheduler.configure()`` + a self-contained ``services/``/``routers/``
split) — see
``project-history/roadmaps/meta-ads-console-2026-07.md`` for the full
initiative.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables,
each returning a ``ModuleRegistration``. This module exposes
:func:`register`. Adding it to the app is a single ``MODULES`` append
in ``main.py`` (no assembly-logic edit).

Routes added
────────────
  - ``/api/meta/ads/accounts``
  - ``/api/meta/ads/campaigns``
  - ``/api/meta/ads/campaigns/{object_id}/children``
  - ``/api/meta/ads/insights/series``
  - ``/api/meta/ads/insights/compare``
  - ``/api/meta/ads/activities``
  - ``/api/meta/ads/sync`` (POST) + ``/api/meta/ads/sync/{job_id}`` (GET)
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Also calls ``meta_ads.scheduler.configure()`` to register the daily
    sync job on the seed scheduler (same pattern as ``youtube``/
    ``email_marketing``)."""
    from app.modules.meta_ads.routers import ads_router
    from app.modules.meta_ads.scheduler import configure as _configure_scheduler
    from app.main import ModuleRegistration

    _configure_scheduler()

    return ModuleRegistration(
        routers=[ads_router.router],
        # No extra standard routers needed beyond the base set.
        standard_routers=(),
    )


__all__ = ["register"]
