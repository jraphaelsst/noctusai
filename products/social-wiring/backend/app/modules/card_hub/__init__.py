"""`card_hub` — the card's data surface (lead-card-hub Phase 2).

Contract: `products/social-wiring/projects/lead-card-hub-p2-PROJECT.md`.
Consumes the seed's blob storage seam (`noctusai_lib.integrations.storage`
— Protocol + Fake + Real + factory) for LGPD-complete document handling
and the seed's shared PostgREST pager
(`noctusai_lib.integrations.persistence.iter_paged_rows`) for every
unbounded read.

Seam contract
─────────────
`app/main.py` iterates `MODULES` — a list of zero-arg callables, each
returning a `ModuleRegistration`. This module exposes `register()`.

🔴 `register()` is placed BEFORE `_register_media_wiring` in
`app/main.py`'s `MODULES` list — see that file's comment for the
route-ordering hazard this resolves (`GET/POST /api/clientes/tags`
structurally collides with `clientes_router.py`'s bare `/{cliente_id}`;
whichever router mounts first in the app's route table wins the match).

What `register()` does
───────────────────────
Registers this module's one router (all endpoints share the
`/api/clientes` prefix) and, as a side effect at import time, the
document-retention sweep on the seed scheduler (`documentos_service.
configure()`) — mirrors `app.services.clientes_backfill_job.configure()`'s
identical "configure before `start_scheduler()` fires" shape.

Routes
──────
    GET                     /api/clientes/tags
    POST                    /api/clientes/tags
    PATCH/DELETE            /api/clientes/tags/{tag_id}
    GET                     /api/clientes/documentos/tipos
    GET                     /api/clientes/{id}/timeline
    POST/PATCH/DELETE       /api/clientes/{id}/notas[/{nota_id}]
    PUT                     /api/clientes/{id}/tags
    GET/PUT                 /api/clientes/{id}/membros
    PATCH                   /api/clientes/{id}/datas
    GET/POST                /api/clientes/{id}/checklists
    PATCH/DELETE            /api/clientes/{id}/checklists/{cid}
    POST/PATCH/DELETE       /api/clientes/{id}/checklists/{cid}/itens[/{iid}]
    GET/POST                /api/clientes/{id}/documentos
    GET                     /api/clientes/{id}/documentos/{did}/url
    DELETE                  /api/clientes/{id}/documentos/{did}
    GET                     /api/clientes/{id}/documentos/{did}/acessos
    GET                     /api/clientes/{id}/card
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Imported and invoked by the `main.py` assembly loop — `app.main` is
    already imported by the time the loop runs, so importing
    `ModuleRegistration` here is not circular (same pattern as
    `app.modules.n8n.register`)."""
    from app.main import ModuleRegistration
    from app.modules.card_hub import documentos_service, financiamento_service
    from app.modules.card_hub.router import defaults_router, router

    # Configured at import time — before `start_scheduler()` fires in
    # `app/lifespan.py` (see `clientes_backfill_job.configure()`'s
    # identical rationale).
    documentos_service.configure()
    # Two sweeps, not one: the cliente clock is stamped at upload and only
    # needs collecting, while the atendimento clock is DERIVED from the deal's
    # `closed_at` and has to be re-derived each run (migration 079).
    financiamento_service.configure()

    return ModuleRegistration(
        routers=[router, defaults_router], standard_routers=()
    )


__all__ = ["register"]
