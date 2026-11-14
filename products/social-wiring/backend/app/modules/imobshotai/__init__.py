"""`imobshotai` — the ImobShotAI photo funnel on top of Edição de Fotos (IMOBSHOTAI-CONTRACT.md v1).

    etapa.py        the card-stage projection (pure)
    repository.py   `imobshot_cards` / `imobshot_eventos` port: Supabase (atomic RPCs) + in-memory
    service.py      `sincronizar_etapa` + the card read models (batched reads)
    router.py       POST /lotes · GET /cards · GET /cards/{id}
    worker_hook.py  `fotos.lote_pronto` -> sync the card

Prefix `/api/imobshotai` is a unique literal with only literal first segments (`/lotes`, `/cards`): no shadowing
hazard, no upload route, no scheduler job."""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.main import ModuleRegistration
    from app.modules.imobshotai.router import router

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
