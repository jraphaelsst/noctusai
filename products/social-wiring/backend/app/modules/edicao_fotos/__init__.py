"""``edicao_fotos`` — AI photo editing for real estate (Edição de Fotos, R1).

WHAT THIS IS
────────────
The social-wiring consumer of the seed engine
``noctusai_lib.domain.photo_editing`` (`KB § PATTERNS/backend/photo-editing-seed.md`).
The engine owns the pipeline; this module owns routes, authorization, the
storage bucket, notification fan-out and the worker lifecycle. Contract:
``projects/edicao-fotos/EDICAO-FOTOS-CONTRACT.md``.

    deps.py                 actor + role guards + DI seams (ports, grants, Vista)
    services/ports.py       engine ports → real adapters
    services/worker.py      seed Worker, behind EDICAO_FOTOS_WORKER_ENABLED (default OFF)
    services/notifier.py    batch-ready in-app notification
    services/vista_fotos.py Vista gallery → batch
    services/review.py      FotoRevisao rows (verdict read only for admins)
    routers/                capacidades · configuracoes · curadores · modelos · lotes · revisao

Response shapes are the seed FE hook types
(`seed/lib/frontend/src/photo-editing/hooks.ts`), pinned by
`seed/lib/frontend/src/photo-editing/contract.fixture.json`.

Routes (all under ``/api/edicao-fotos``; every one requires auth → 401):
    GET    /capacidades                              member ∨ platform admin ∨ curator
    GET    /configuracoes                            member (read-only summary)
    PUT    /configuracoes                            agency admin ∨ platform admin
    GET    /configuracoes/plataforma                 platform admin
    PUT    /configuracoes/plataforma                 platform admin
    GET    /curadores                                platform admin
    POST   /curadores                                platform admin
    DELETE /curadores/{user_id}                      platform admin
    GET    /modelos                                  member (catalog; metrics/notes null until W8)
    GET    /lotes                                    member (corretor: own)
    POST   /lotes                                    member
    GET    /lotes/{id}                               member, batch visible
    POST   /lotes/{id}/fotos                         member, batch visible (UploadFile)
    POST   /lotes/{id}/vista                         member, batch visible
    POST   /lotes/{id}/submeter                      member, batch visible
    POST   /lotes/{id}/fotos/{foto_id}/retentar      member, batch visible
    GET    /lotes/{id}/zip                           member, batch visible
    GET    /revisao/{lote_id}                        member, batch visible (verdict: admins only)
    POST   /revisao/{lote_id}/fotos/{foto_id}/decisao member, batch visible

Not in R1 here (later slices): reference pool, style guides, learning rules,
model metrics/notes, dashboard, email/WhatsApp notifications, Econômico (C8).

Seam contract
─────────────
``app/main.py`` iterates ``MODULES``; this module exposes :func:`register`.
Its prefix ``/api/edicao-fotos`` is a unique literal with no 1-segment
dynamic path at its root, so it cannot shadow or be shadowed by the
``clientes_router`` hazard documented there. One upload route →
one ``_MAX_BODY_PATH_OVERRIDES`` entry. The worker is started from
``app/lifespan.py``.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.main import ModuleRegistration
    from app.modules.edicao_fotos.routers import (
        capacidades,
        configuracoes,
        curadores,
        lotes,
        modelos,
        revisao,
    )

    return ModuleRegistration(
        routers=[
            capacidades.router,
            configuracoes.router,
            curadores.router,
            modelos.router,
            lotes.router,
            revisao.router,
        ],
        standard_routers=(),
    )


__all__ = ["register"]
