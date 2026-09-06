"""``permutas`` — property swapping, matched by the shared engine.

WHAT THIS IS
────────────
The absorption of the legacy Permutas platform into social-wiring. Its DATA
came (migration 101 + the backfill); its CODE deliberately did not — the
Django app was reverted off `dev` on 2026-09-06 carrying 100 open
HIGH/CRITICAL CVEs, and its matching was hard filters over near-empty columns,
which is why its funnel closed 74 of 82 matches as rejected.

What replaced it is the bilateral scorer already built in erp-imobiliario,
promoted in the same slice to
``noctusai_lib.domain.real_estate.matching`` so both products read one copy.

THE THREE PIECES
────────────────
    adapter.py     projects our rows into the scorer's vocabulary. The
                   `imovel` side is assembled at read time from
                   `permuta_ativos` + Vista-synced `imoveis`, because 219 of
                   the 271 legacy refs are already in the catalog with far
                   richer data than the legacy app ever held.
    embeddings.py  writes BOTH vectors per ativo — the profile and the wants.
    service.py     the queries, the protected upsert, the funnel.

🔴 WHY THE SEMANTIC HALF IS THE POINT, NOT A GARNISH
In this corpus the structured criteria are nearly empty — `cidade` is set on
0 of 135 legacy interest rows — while the free text carries the actual
constraints: "casa sem escada", "rua do condomínio sem ladeira", "quintal
amplo", "estuda permuta de 30% a 50% do valor". A rule score cannot read any
of that. `gerar_matches` therefore RETURNS `sem_semantica` (how many pairs
scored without vectors) rather than logging it, because a run with no
embeddings still produces a full list of plausible-looking matches — which is
precisely how erp shipped a dead composite path for months without noticing.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — zero-arg callables each returning a
``ModuleRegistration``. This module exposes :func:`register`. Wiring it in is
a single ``MODULES`` append.

Declares no ``UploadFile`` route (so no ``_MAX_BODY_PATH_OVERRIDES`` entry)
and schedules no sweep, so registration is a ONE-edit step — same shape as
``agentes_financeiros``.

Routes
──────
    GET    /api/permutas                  list the swap registry
    POST   /api/permutas                  register an intent (+ interests)
    GET    /api/permutas/{id}             one intent
    PATCH  /api/permutas/{id}             edit (interests REPLACE)
    DELETE /api/permutas/{id}             remove
    POST   /api/permutas/gerar            run the engine
    POST   /api/permutas/embeddings       vectorise profiles + wants
    GET    /api/permutas/matches          scored pairs, best first
    PATCH  /api/permutas/matches/{id}     move through the funnel
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.main import ModuleRegistration
    from app.modules.permutas.router import router

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
