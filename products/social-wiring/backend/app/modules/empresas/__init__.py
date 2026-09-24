"""`empresas` — companies a cliente participates in (P0c contract §A/§C6/§D).

`empresas` (the company row, group D1 provenance), `empresa_documentos`
(Cartão CNPJ, `DocumentoStore`-backed) and `empresa_campo_conflitos` (the
shared writer, `app.services.campo_conflitos`) — migration 167.

Seam contract
─────────────
`app/main.py` iterates `MODULES` — zero-arg callables each returning a
`ModuleRegistration`. This module exposes `register()`.

Routes
──────
    GET         /api/empresas/{empresa_id}
    GET/POST    /api/empresas/{empresa_id}/documentos
    POST        /api/empresas/{empresa_id}/documentos/{id}/extrair
    POST        /api/empresas/{empresa_id}/documentos/{id}/extracao/confirmar
    POST        /api/empresas/{empresa_id}/documentos/{id}/extracao/descartar
    GET         /api/empresas/{empresa_id}/documentos/{id}/url
    DELETE      /api/empresas/{empresa_id}/documentos/{id}

`GET/POST /api/clientes/{cliente_id}/empresas` (the card's listing/manual
link) live in `card_hub/router.py` instead — see `card_hub/empresas_
service.py`.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Also configures the Cartão CNPJ extraction recovery sweep as a side
    effect at import time — before `start_scheduler()` fires in
    `app/lifespan.py`, which is the only moment it can be registered.
    Mirrors `imovel_hub.register()`'s identical shape.
    """
    from app.main import ModuleRegistration
    from app.modules.empresas import extracao_scheduler
    from app.modules.empresas.router import router

    extracao_scheduler.configure()

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
