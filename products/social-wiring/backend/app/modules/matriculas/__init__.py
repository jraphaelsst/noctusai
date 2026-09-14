"""``matriculas`` — Extrator de Matrículas, ported from erp-imobiliario.

WHAT THIS IS
────────────
Upload a matrícula PDF, get its FULL TEXT back. One table
(``social_wiring.matricula_extracoes``) holding one row per upload, with a
status lifecycle ``pendente → processando → concluida|erro`` and the
transcribed text.

THE ONE MATRÍCULA TEXT PIPELINE — AND WHERE ``imovel_hub`` FITS
────────────────────────────────────────────────────────────────
Migration 109 links this module to the imóvel. A matrícula uploaded with a
``codigo`` is kept as that imóvel's ``imovel_documentos`` row (the ONE storage
home, LGPD-logged), and an imóvel's already-stored matrícula PDF can be
transcribed without re-uploading (``/extracoes/de-documento``). Either way the
text goes through ONE pipeline — ``service.processar_extracao`` — which also
persists the acts (``estrutura_service.persistir_atos``, offsets from the seed
segmenter).

``app/modules/imovel_hub/matricula_extracao_service.py`` still reads the
número de matrícula off the same PDF with its own seed ladder
(``make_matricula_extractor``). This module queues THAT job rather than
copying it, but a scanned PDF is still read twice.

NOC-REMEDIATE[matricula-pipeline-consolidation]: collapse the número read
onto this module's single transcription. Blocked on the seed: the
vision-source tempering that makes a número ``persistable`` lives only inside
``LadderMatriculaExtractor._temper``, so deriving ``MatriculaFields`` from an
existing ``Transcription`` product-side would fork that safety rule. Named
destination: a seed ``matricula_fields_from_transcription(Transcription)``,
after which ``imovel_hub.matricula_extracao_service.extrair`` becomes a
projection of the matrícula extraction and its ``extracao_*`` columns stop
being a second pipeline's state. — 2026-09-14

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables, each
returning a ``ModuleRegistration``. This module exposes :func:`register` and is
registered there, together with the ``"/api/matriculas/extrair"`` entry in
``_MAX_BODY_PATH_OVERRIDES`` that ``noctusai_seed.upload_route_overrides``
requires (20 MB = :data:`app.modules.matriculas.router.MAX_FILE_SIZE`, so a
file the handler would reject is rejected one layer earlier instead of being
read into memory first). The routes 109 added take no upload.

Routes
──────
    POST   /api/matriculas/extrair                  upload (+ optional ``codigo``)
    POST   /api/matriculas/extracoes/de-documento   transcribe an imóvel's stored PDF
    GET    /api/matriculas/extracoes                history (no text; ``?codigo=``)
    GET    /api/matriculas/extracoes/{id}           one, WITH ``texto_extraido``
    DELETE /api/matriculas/extracoes/{id}           delete (409 while quoted)
    GET    /api/matriculas/extracoes/{id}/atos      acts, as literal slices
    GET    /api/matriculas/extracoes/{id}/fontes    título/ônus suggestions + pointers
    PUT    /api/matriculas/extracoes/{id}/fontes    operator confirms título/ônus acts
    GET    /api/matriculas/contratos/{id}/atos      a contract's quoted acts
    PUT    /api/matriculas/contratos/{id}/atos      replace a contract's quoted acts
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
