"""``media_creation`` — social-wiring product module (Wave 2.4).

The **media-creation arm** of the social-media automation ecosystem. Where
the W2.1 base distributes media (YouTube upload, WhatsApp chatbot, intake),
W2.2 distributes email campaigns, W2.3 schedules real-estate appointments,
W2.4 PRODUCES the media that the rest of the product distributes.

Ports the abstraction proven by the sibling ``media-creator/`` repo (an
agent-driven, file-based, single-tenant prototype) into a multi-tenant,
API-driven, DB-backed module under the ``social_wiring`` schema.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables, each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Add it to the app by appending it to ``MODULES``:

    from app.modules.media_creation import register as _register_media_creation
    MODULES = [..., _register_media_creation]

What ``register()`` does
────────────────────────
* Imports the four routers (brand_kits / references / posts / generation).
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

What is NOT here (phase-2 / future)
───────────────────────────────────
* Image rendering — needs a new seed adapter
  (``noctusai_lib.integrations.image_gen``). The ``POST /render`` endpoint
  ships a typed ``gate=image_generation_not_configured`` signal per
  ``feedback_gated_capability_honesty`` until that adapter lands. Filed as
  the follow-up project ``image-gen-seed-adapter``.
* Video generation — schema accepts ``format=video`` for forward
  compatibility; no logic.
* Direct publish to Meta / Instagram / Facebook write — out of scope of the
  current ``noctusai_lib.integrations.meta`` (read-only-v1).
* Eval loop — media-creator's ``evals/`` is empty; we don't pre-build what
  upstream hasn't validated yet.

Migrations
──────────
The W2.4 tables (``mc_brand_kits``, ``mc_brand_references``, ``mc_posts``,
``mc_post_slides``) live under the ``-- W2.4 media_creation`` section
marker in ``products/social-wiring/backend/migrations/001_social-wiring.sql``.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    ``app.main`` is already imported by the time the assembly loop calls
    this, so importing ``ModuleRegistration`` from there is not circular.
    """
    from app.modules.media_creation.routers import (
        brand_kits,
        generation,
        posts,
        references,
    )

    from app.main import ModuleRegistration

    return ModuleRegistration(
        routers=[
            brand_kits.router,
            references.router,
            posts.router,
            generation.router,
        ],
        # No extra standard routers — the LLM seam is auto-wired by
        # create_product_app(); this module talks to chat_completion()
        # directly without needing the /api/llm standard router exposed.
        standard_routers=(),
    )


__all__ = ["register"]
