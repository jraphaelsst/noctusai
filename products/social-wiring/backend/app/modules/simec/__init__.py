"""``simec`` — Sistema de Inteligência de Marketing e Estratégia de Conteúdo
(marketing-intelligence P1, slice S2).

Per-org + per-profile SIMEC config (partial overrides on the seed defaults),
readouts computed by the seed's pure ``noctusai_lib.domain.content_performance``
calculator over readings from a ``SimecMetricsSource`` (Real: our Instagram
daily snapshots; Fake: an in-memory demo catalog), and the ``/api/simec/...``
surface. Migration ``284_simec.sql``. Contract:
``projects/marketing-intelligence/specs/simec-api-contract.md``.

    sources.py     SimecMetricsSource seam + Instagram Real/Fake + factory
    repository.py  simec_configs / simec_config_historico / simec_readouts / simec_leituras IO
    service.py     config layering + readout computation (delegates math to the seed)
    router.py      HTTP surface
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    from app.main import ModuleRegistration
    from app.modules.simec.router import router

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
