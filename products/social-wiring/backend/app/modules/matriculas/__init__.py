"""``matriculas`` — Extrator de Matrículas, ported from erp-imobiliario.

WHAT THIS IS
────────────
Upload a matrícula PDF, get its FULL TEXT back. One table
(``social_wiring.matricula_extracoes``) holding one row per upload, with a
status lifecycle ``pendente → processando → concluida|erro`` and the
transcribed text.

🔴 NOT THE SAME THING AS ``imovel_hub``'s matrícula extraction.
``app/modules/imovel_hub/matricula_extracao_service.py`` reads STRUCTURED
FIELDS (the número de matrícula) off a document already attached to an
imóvel, and writes them onto that imóvel. This module transcribes an
arbitrary uploaded PDF to raw text with its own upload history, attached to
nothing. Same domain word, different workflow, different seed adapter
(``make_document_transcriber`` here, ``make_matricula_extractor`` there).
Both are deliberate.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables, each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Wiring it in is a single ``MODULES`` append in ``main.py`` at integration
time (deliberately NOT done by this slice — peer branches are live in that
file concurrently; the tech-lead registers it when merging).

🔴 THE INTEGRATION STEP IS TWO EDITS, NOT ONE.
``POST /api/matriculas/extrair`` declares an ``UploadFile`` parameter, and
``noctusai_seed.upload_route_overrides`` REFUSES TO BOOT the app when a
mounted upload route has no entry in ``_MAX_BODY_PATH_OVERRIDES``. So the
``MODULES`` append must land together with::

    "/api/matriculas/extrair": 20 * 1024 * 1024,  # 20 MB

in ``main.py``'s ``_MAX_BODY_PATH_OVERRIDES``. 20 MB because that is the
ceiling :data:`app.modules.matriculas.router.MAX_FILE_SIZE` enforces in the
handler — the middleware bound and the handler bound are the same number by
intent, so a file the handler would reject is rejected one layer earlier
instead of being read into memory first.

Routes
──────
    POST   /api/matriculas/extrair             upload + background extraction
    GET    /api/matriculas/extracoes           history (no ``texto_extraido``)
    GET    /api/matriculas/extracoes/{id}      one, WITH ``texto_extraido``
    DELETE /api/matriculas/extracoes/{id}      delete
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Also configures the stranded-extraction recovery sweep as a side effect
    at import time — before ``start_scheduler()`` fires in
    ``app/lifespan.py``, which is the only moment it can be registered.
    Mirrors ``imovel_hub.register()`` / ``card_hub.register()``.

    ``app.main`` is already imported by the time the assembly loop runs, so
    importing ``ModuleRegistration`` here is not circular (same pattern as
    ``app.modules.n8n.register``).
    """
    from app.main import ModuleRegistration
    from app.modules.matriculas import extracao_scheduler
    from app.modules.matriculas.router import router

    extracao_scheduler.configure()

    return ModuleRegistration(routers=[router], standard_routers=())


__all__ = ["register"]
