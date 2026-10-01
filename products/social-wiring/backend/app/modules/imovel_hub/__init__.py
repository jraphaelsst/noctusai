"""`imovel_hub` — the cartório data and documents WE author for an imóvel.

Companion to `app/routers/imoveis_router.py`, which reads the Vista sync
mirror. Migration 075 explains why the two are separate in the schema; this
module is the same separation in the code.

Seam contract
─────────────
`app/main.py` iterates `MODULES` — a list of zero-arg callables, each
returning a `ModuleRegistration`. This module exposes `register()`.

Routes
──────
    GET/PATCH   /api/imoveis/{codigo}/dados
    GET/POST    /api/imoveis/{codigo}/documentos
    GET         /api/imoveis/{codigo}/documentos/{documento_id}/url
    DELETE      /api/imoveis/{codigo}/documentos/{documento_id}

Atendimento↔imóvel↔pessoa relationships (project `atendimento-partes-imoveis`,
contract §3-§4):
    GET/POST/DELETE  /api/clientes/{id}/atendimento-imoveis[/{item}[/principal]]
    GET/POST/DELETE  /api/clientes/{id}/interesses[/{interesse}]
    GET/POST/DELETE  /api/clientes/{id}/propriedades[/{id}]  (+ /api/empresas/…)
    GET              /api/clientes/{id}/resumo
    GET              /api/imoveis/{codigo}/proprietarios|interessados|similares

Consumes the seed's blob storage seam
(`noctusai_lib.integrations.storage`) and the matrícula extractor
(`noctusai_lib.integrations.documents.make_matricula_extractor`) — both
Protocol + Fake + Real + factory.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Also configures the matrícula-extraction recovery sweep as a side effect
    at import time — before `start_scheduler()` fires in `app/lifespan.py`,
    which is the only moment it can be registered. Mirrors
    `card_hub.register()`'s identical shape.
    """
    from app.main import ModuleRegistration
    from app.modules.imovel_hub import extracao_scheduler
    from app.modules.imovel_hub.atendimento_imoveis_router import (
        router as atendimento_imoveis_router,
    )
    from app.modules.imovel_hub.imovel_relacionamentos_router import (
        router as imovel_relacionamentos_router,
    )
    from app.modules.imovel_hub.interesses_router import router as interesses_router
    from app.modules.imovel_hub.pessoa_router import router as pessoa_router
    from app.modules.imovel_hub.router import router

    extracao_scheduler.configure()

    return ModuleRegistration(
        routers=[
            router,
            atendimento_imoveis_router,
            interesses_router,
            imovel_relacionamentos_router,
            pessoa_router,
        ],
        standard_routers=(),
    )


__all__ = ["register"]
