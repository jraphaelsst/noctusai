"""`atendimento_blocos` -- the atendimento as a closed list of blocks + the handoff ledger (maya-blocks S2).

Contract: `products/social-wiring/projects/maya-blocks/CONTRACT.md`. Schema: migration 286.

  blocos.py      the closed block list, the default stage -> block map, the agent allowlist (pure)
  repository.py  `atendimento_blocos` reads/writes, the effective config, the derived current block (§1.1)
  service.py     GET/PUT behaviour (§4.1 / §4.2)
  handoffs.py    T1 `novo_lead` sink, T2 block-boundary hook, the emitido -> assumido | expirado machine (§2)
  router.py      `/api/atendimento-blocos`

Seam: `app/main.py` iterates `MODULES`; this module exposes `register()`. `/api/atendimento-blocos` is a unique
literal prefix with no 1-segment dynamic path, so its position in `MODULES` is free. No upload route, no job
(the S3 sweep schedules `handoffs.varrer`).
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    from app.main import ModuleRegistration
    from app.modules.atendimento_blocos.router import router

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
