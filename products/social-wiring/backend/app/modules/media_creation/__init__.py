"""``media_creation`` — social-wiring product module (Wave 2.4).

The **media-creation arm** of the social-media automation ecosystem. Where
the W2.1 base distributes media (YouTube upload, WhatsApp chatbot, intake),
W2.2 distributes email campaigns, W2.3 schedules real-estate appointments,
W2.4 PRODUCES the media that the rest of the product distributes.

A multi-tenant, API-driven, DB-backed content studio under the
``social_wiring`` schema. Every post is built on the in-home Método Audience
methodology (see :mod:`.prompts.methodology`) — a dominant attention trigger,
named headline template(s), and the capa→identificacao→virada→nome→prova→
valor→cta role skeleton. Fully self-contained: no external folder dependency.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables, each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Add it to the app by appending it to ``MODULES``:

    from app.modules.media_creation import register as _register_media_creation
    MODULES = [..., _register_media_creation]

What ``register()`` does
────────────────────────
* Imports the routers (brand_kits / branding / references / posts / generation / pesquisa / cerebro).
* Returns the ``ModuleRegistration`` with no extra standard-router needs
  (the routers all gate via ``Depends(get_current_user_org)``).

Routes are namespaced under ``/api/media-creation/...`` to stay collision-
free with the existing W2.1 (``/api/settings``, ``/api/videos``,
``/api/upload``, ...), W2.2 (``/api/email-marketing/...``), and W2.3
(``/api/scheduling/...``) modules.

Seed primitives consumed
────────────────────────
* ``noctusai_lib.integrations.llm.chat_completion`` — drives the 3-stage
  generation pipeline (storyboard / image prompts / copy).
* ``noctusai_lib.api.StrictHttpModel`` — Pydantic models with ``extra="forbid"``.
* ``noctusai_lib.primitives.responses.success_response`` — envelope shape.
* ``noctusai_lib.api.crud_safety.delete_or_404`` — defense-in-depth deletes.
* ``app.dependencies.{get_current_user_org,get_org_id,get_admin_client}`` —
  the social-wiring seed-factory auth/db seam.

What ships
──────────
* Image rendering — ``POST /render`` produces AI images via
  ``noctusai_lib.integrations.image_gen`` (Gemini) when an org Gemini key is
  configured, else falls back to a visible brand-locked SVG placeholder
  (``mode=svg_fallback``, ``configured=False``) per
  ``feedback_gated_capability_honesty`` — never a broken image.
* Formats — ``carousel`` / ``single`` / ``reels`` (9:16 script). ``video``
  remains accepted for forward compatibility.

What is NOT here (future)
─────────────────────────
* Direct publish to Meta / Instagram / Facebook write — out of scope of the
  current ``noctusai_lib.integrations.meta`` (read-only-v1).

Migrations
──────────
The W2.4 tables (``mc_brand_kits``, ``mc_brand_references``, ``mc_posts``,
``mc_post_slides``) live under the ``-- W2.4 media_creation`` section
marker in ``products/social-wiring/backend/migrations/001_social-wiring.sql``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    ``app.main`` is already imported by the time the assembly loop calls
    this, so importing ``ModuleRegistration`` from there is not circular.
    """
    from app.modules.media_creation.routers import (
        assuntos_virais,
        brand_kits,
        branding,
        cerebro,
        cerebro_fontes,
        generation,
        pesquisa,
        pesquisa_extracao,
        posts,
        references,
    )
    from app.modules.media_creation import cerebro_scheduler
    from app.modules.media_creation.services import cerebro_transcricao

    from app.main import ModuleRegistration

    # Import-time registration, BEFORE `start_scheduler()` — the stale-work sweep.
    cerebro_scheduler.configure()
    # Voice answers: the `cerebro_resposta` context of the shared transcription layer.
    cerebro_transcricao.register_contexto()
    # Geração: stale + dead-letter sweep (import-time, BEFORE `start_scheduler()`).
    from app.modules.media_creation import geracao_scheduler
    from app.modules.media_creation.services import geracao_jobs

    geracao_scheduler.configure()

    async def start_pesquisa_extracao_hook() -> None:
        """Its OWN seed Worker (types ["pesquisa.extrair"]), NOT the fotos one (that one's claim
        gate is the fotos pause). A wiring failure is logged at ERROR and never aborts startup."""
        from app.config import settings
        from app.modules.media_creation.services.pesquisa_extracao_worker import start_worker

        try:
            await start_worker(settings)
        except Exception:
            logger.exception("pesquisa_extracao: worker NÃO iniciado — as extrações ficam na fila.")

    async def stop_pesquisa_extracao_hook() -> None:
        from app.modules.media_creation.services.pesquisa_extracao_worker import stop_worker

        await stop_worker()

    return ModuleRegistration(
        routers=[
            brand_kits.router,
            branding.router,
            references.router,
            posts.router,
            generation.router,
            pesquisa.router,
            assuntos_virais.router,
            pesquisa_extracao.router,
            cerebro.router,
            cerebro_fontes.router,
        ],
        # No extra standard routers — the LLM seam is auto-wired by
        # create_product_app(); this module talks to chat_completion()
        # directly without needing the /api/llm standard router exposed.
        standard_routers=(),
        # The `geracao` + `biblioteca` workers (geracao_jobs) own their isolation per worker.
        startup=[start_pesquisa_extracao_hook, geracao_jobs.startup_hook],
        shutdown=[stop_pesquisa_extracao_hook, geracao_jobs.shutdown_hook],
    )


__all__ = ["register"]
