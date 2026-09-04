"""``agentes_financeiros`` — the per-org registry of financing agents.

WHAT THIS IS
────────────
One table (``social_wiring.agentes_financeiros``, migration 100) holding the
banks an agency actually works with, managed on its own page and offered as
the dropdown on the card's Financiamento tab.

🔴 WHY A REGISTRY AND NOT A ``banco TEXT`` COLUMN
An agency works with the same four or five agents over and over, each with a
manager, a branch and a phone number the operator reaches for on every deal.
Typed per deal, "Caixa Econômica Federal" becomes "CAIXA", "Caixa Econômica"
and "caixa economica federal" inside a month — and "how many deals went
through Caixa this quarter" stops having an answer. Migration 100's header
carries the full argument.

🔴 RETIRE, NEVER DELETE
``atendimento_financiamento.agente_financeiro_id`` references this table with
``ON DELETE RESTRICT``, so an agent attached to a deal cannot be removed. That
is deliberate: CASCADE would destroy the deals and SET NULL would silently
blank which bank financed them, on a click that reads as tidying a list.
``ativo = false`` takes an agent out of the dropdown while every deal it
already finances keeps rendering it.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — zero-arg callables each returning a
``ModuleRegistration``. This module exposes :func:`register`. Wiring it in is
a single ``MODULES`` append in ``main.py``.

Unlike ``matriculas``/``certidoes``, registration here is a ONE-edit step:
this module declares no ``UploadFile`` route, so it needs no
``_MAX_BODY_PATH_OVERRIDES`` entry, and it schedules no sweep.

Routes
──────
    GET    /api/agentes-financeiros          list (``?incluir_inativos=``)
    POST   /api/agentes-financeiros          create
    PATCH  /api/agentes-financeiros/{id}     update (including ``ativo``)
    DELETE /api/agentes-financeiros/{id}     delete — 409 when in use
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    ``app.main`` is already imported by the time the assembly loop runs, so
    importing ``ModuleRegistration`` here is not circular — same pattern as
    ``app.modules.matriculas.register``.
    """
    from app.main import ModuleRegistration
    from app.modules.agentes_financeiros.router import router

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
