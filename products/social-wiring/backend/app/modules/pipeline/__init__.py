"""``pipeline`` — Funil de Vendas + Processos de Venda for social-wiring.

The second consumer of the pipeline primitive extracted from erp-imobiliario:
DB-driven user-editable stages, one shared card-move mechanic that always
writes a stage-transition history row, and the accept-proposal seam between
the two boards.

Cards come from LEADS. Migration 034 installs an AFTER INSERT trigger on both
`social_wiring.leads` and `social_wiring.meta_ads_leads`, so a lead arriving —
by the API, the workbook importer, or the Meta Lead-Ads sync — lands a card on
the first configured stage. That is why this module exposes no create endpoint.

Seam contract: `app/main.py` iterates `MODULES`; this module exposes
:func:`register`.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.main import ModuleRegistration
    from app.modules.pipeline.routers.boards import (
        funil_router,
        atendimentos_router,
        processos_router,
    )
    from app.modules.pipeline.routers.stages import (
        funil_stages_router,
        processos_stages_router,
    )

    return ModuleRegistration(
        # ORDER MATTERS. The stage routers must precede the card routers:
        # `/api/processos-venda/{processo_id}` would otherwise match the
        # literal path `/api/processos-venda/etapas` and try to load a processo
        # whose id is "etapas". FastAPI resolves in registration order, so the
        # literal has to be registered first.
        routers=[
            funil_stages_router,
            processos_stages_router,
            funil_router,
            atendimentos_router,
            processos_router,
        ],
    )
