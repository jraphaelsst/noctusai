"""``condominios`` -- the condomínio master list (migration 265).

Built FROM data (Vista `empreendimento` spellings), refined and VALIDATED by
the owner on the "Condominios" page, which then is the permanent source of
truth for the price evaluator's location driver.

Routes (all org-scoped, `Depends(get_current_user_org)`):

    GET    /api/condominios                        list + stats (imoveis, preço/m²)
    POST   /api/condominios/sugerir                admin: build suggestions
    GET    /api/condominios/{id}                   one + aliases + events
    PATCH  /api/condominios/{id}                   edit attributes (member)
    POST   /api/condominios/{id}/validar           admin
    POST   /api/condominios/{id}/descartar         admin
    POST   /api/condominios/{id}/reabrir           admin
    POST   /api/condominios/{id}/renomear          admin
    POST   /api/condominios/{id}/fundir            admin: merge into body.destino_id
    POST   /api/condominios/{id}/desfazer-fusao    admin: reverse the merge
    POST   /api/condominios/{id}/aliases           admin
    DELETE /api/condominios/{id}/aliases/{alias_id}  admin

Unique 2-segment literal prefix with no 1-segment dynamic path at its root;
`/sugerir` is declared before `/{condominio_id}` all the same.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.main import ModuleRegistration
    from app.modules.condominios.router import router

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
