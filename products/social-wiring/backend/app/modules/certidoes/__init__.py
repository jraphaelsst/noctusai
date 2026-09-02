"""``certidoes`` — Certidões Negativas, ported from the retiring ERP.

Automated issuance of the ten negative certificates a real-estate due diligence
needs (CND Federal, TRF3 ×2, TRT2 ×2, CND Trabalhista TST, TJSP, CENPROT, CND
Fazenda SP, Dívida Ativa SP) through the InfoSimples API, plus AI analysis of
each result, persistence to this product's document bucket, the TJSP
45-minute cooldown queue, reprocess, cancel, manual upload and a ZIP download of
the whole set.

Ported from `products/erp-imobiliario/backend/app/{routers,services}/certidoes*`
as that product is retired. `service.py`'s docstring lists the four things that
changed and why; everything else is the ERP behaviour, because it is the
behaviour a live user depends on.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables, each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Wiring it into the app is a single ``MODULES`` append in ``main.py`` at
integration time (deliberately NOT done by this slice — peer branches are live
in that file concurrently; the tech-lead registers this module when merging).

🔴 THE INTEGRATION STEP HAS A SECOND HALF. ``POST
/api/certidoes/resultados/{resultado_id}/upload`` takes an ``UploadFile``, and
``create_product_app`` REFUSES TO BOOT when a mounted upload route has no
covering ``max_body_path_overrides`` entry — by design, because the 1 MB
webhook-DoS default would 413 an ordinary certidão scan before the route ever
ran, and a fixture-sized test would never notice. The entry is
``"/api/certidoes/resultados/*/upload"`` (the `*` matches exactly the one
dynamic segment). See the return note for the value and its reasoning.

What ``register()`` does
────────────────────────
1. Calls ``scheduler.configure()`` at IMPORT time — the stranded-work sweep has
   to be registered on the seed scheduler before ``start_scheduler()`` fires in
   ``app/lifespan.py``, or the safety net silently does not exist. Same rule
   ``_register_media_wiring`` documents for its five jobs.
2. Returns this module's single router, mounted at ``/api/certidoes``. No extra
   ``standard_routers`` beyond the product's base set.

Routes
──────
    GET    /api/certidoes/tipos
    GET/POST               /api/certidoes/consultas
    GET/DELETE             /api/certidoes/consultas/{id}
    POST                   /api/certidoes/consultas/{id}/reprocessar
    POST                   /api/certidoes/consultas/{id}/cancelar
    GET                    /api/certidoes/consultas/{id}/download-zip
    GET                    /api/certidoes/download
    POST                   /api/certidoes/resultados/{id}/upload
    GET                    /api/certidoes/fila-tjsp
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Imported and invoked by the ``main.py`` assembly loop. ``app.main`` is
    already importing by the time the loop runs, so importing
    ``ModuleRegistration`` here is not circular (same pattern as
    ``app.modules.n8n.register`` / ``app.modules.youtube.register``).
    """
    from app.main import ModuleRegistration
    from app.modules.certidoes import scheduler
    from app.modules.certidoes.routers import certidoes as certidoes_router

    # Import-time registration, BEFORE `start_scheduler()` — see the module
    # docstring and `scheduler.py`'s own for what goes un-recovered otherwise.
    scheduler.configure()

    return ModuleRegistration(
        routers=[certidoes_router.router],
        standard_routers=(),
    )


__all__ = ["register"]
