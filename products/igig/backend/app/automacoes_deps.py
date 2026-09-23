"""FastAPI providers for the automation engine's ports (`app/services/automacoes.py`).

Three scopes, like the repositories in `app/store.py`:

* :func:`get_portas_automacao` — AUTHENTICATED Comercial routes (moves,
  negócio creation). Pipeline tables go through the caller's RLS client — the
  same `db` the move itself used, so the engine sees exactly what the move
  wrote — plus the service-role client the negócio CARD HUB writes through
  by construction (`app/card_hub.py`: `criar_checklist` / `criar_tarefa`).
* :func:`get_portas_automacao_esteira` — the AUTHENTICATED Esteira move. NO
  service-role client at all: the esteira has no card hub, and
  `tests/routers/test_esteira_router.py` pins that its authed routes never
  resolve `get_admin_db`. A card-hub action there is refused by the engine.
* :func:`get_portas_automacao_admin` — the PUBLIC lead webhooks (no noc session,
  so no RLS org). Everything on the igig service-role client; `org_id` comes
  from the verified webhook and is filtered on every query.

All three are dependencies (not module globals) so tests override `get_db` /
`get_admin_db` / `get_core_db` / `get_settings` and the engine follows.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.config import get_settings
from app.pipelines import get_admin_db, get_core_db, get_db
from app.services.automacoes import PortasAutomacao

__all__ = ["get_portas_automacao", "get_portas_automacao_admin", "get_portas_automacao_esteira"]


def get_portas_automacao(
    db: Any = Depends(get_db),
    admin_db: Any = Depends(get_admin_db),
    core_db: Any = Depends(get_core_db),
    cfg: Any = Depends(get_settings),
) -> PortasAutomacao:
    return PortasAutomacao(db=db, admin_db=admin_db, core_db=core_db, cfg=cfg)


def get_portas_automacao_esteira(
    db: Any = Depends(get_db),
    core_db: Any = Depends(get_core_db),
    cfg: Any = Depends(get_settings),
) -> PortasAutomacao:
    return PortasAutomacao(db=db, admin_db=None, core_db=core_db, cfg=cfg)


def get_portas_automacao_admin(
    admin_db: Any = Depends(get_admin_db),
    core_db: Any = Depends(get_core_db),
    cfg: Any = Depends(get_settings),
) -> PortasAutomacao:
    return PortasAutomacao(db=admin_db, admin_db=admin_db, core_db=core_db, cfg=cfg)
