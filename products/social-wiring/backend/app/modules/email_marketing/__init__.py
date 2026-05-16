"""``email_marketing`` — social-wiring product module (Wave 2.2).

Absorbs the (now-retired) standalone ``mailing`` product's UNIQUE
email-marketing domain into social-wiring as a self-contained module:
contacts · lists · templates · campaigns (lifecycle) · multi-step
automations · dynamic segmentation · analytics · public unsubscribe
(LGPD) · Resend webhook receiver · 7 AI features (subject-gen / template
draft / re-engagement / deliverability / translate / segmentation /
campaign-debrief).

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables, each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Adding it to the app is a single ``MODULES`` append in ``main.py`` (no
assembly-logic edit):

    from app.modules.email_marketing import register as _email_marketing
    MODULES = [_register_media_wiring, _email_marketing]

What ``register()`` does
────────────────────────
* Eagerly imports ``ai_consent_features`` so its ``register_feature(...)``
  calls populate the platform consent catalog at app boot (mailing did
  this via ``create_product_app(consent_features=...)``; social-wiring's
  ``main.py`` has that seam commented out and is out of this module's
  edit scope, so the module self-registers its features).
* Calls ``scheduler.configure()`` so the 3 send/automation jobs land on
  the seed scheduler before any ``start_scheduler()`` fires.
* Returns the module's routers + the seed standard-router names it needs.

Routers are all namespaced under ``/api/email-marketing/...`` to stay
collision-free with the W2.1 ``media_wiring`` module (which owns
``/api/settings``, ``/api/dashboard``, etc.) and the future W2.3
``scheduling`` module.

Seed primitives consumed
────────────────────────
* ``noctusai_lib.domain.digest.BaseDigestService`` + ``render_digest_pair``
  + ``narrative`` + ``build_and_send`` — campaign debrief (no per-product
  digest plumbing).
* ``noctusai_lib.integrations.llm.{chat_completion,generate_embedding}`` —
  all 7 AI features.
* ``noctusai_lib.domain.ai.{register_feature,get_feature,consent_required,
  AIOutput,persist_output}`` + ``…ai.tool_audit`` — consent + LLM audit.
* ``noctusai_lib.api.scheduler`` — send-loop / scheduled-campaign /
  automation jobs.
* ``noctusai_lib.api.crud_safety.delete_or_404`` — defense-in-depth deletes.
* ``noctusai_lib.security.webhook_signatures.webhook_endpoint`` — Resend
  Svix-protocol signature verification (5-pin contract).
* ``noctusai_lib.api.StrictHttpModel`` / ``noctusai_lib.primitives.*`` —
  schemas + responses + JSON parsing.
* ``app.dependencies.{get_current_user_org,get_org_id,get_admin_client,
  get_user_client}`` — the social-wiring seed-factory auth/db seam (NOT a
  re-vendored copy — the canonical late-binding/sqlite-aware helpers).

NOTE — the mailing-vendored ``app/scheduler.py`` wrapper, ``app/database.py``
``app/dependencies.py``, ``app/config.py``, ``app/rate_limit.py``, and the
``app/models`` package were NOT carried in: social-wiring already ships
those seams. Only the audit-writer ORM glue (``models/tool_call_audit``)
is module-local because the seed audit primitive requires a per-product
SQLAlchemy class bound to the product's schema.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`.

    Imported and invoked by the ``main.py`` assembly loop. ``app.main``
    is already imported by the time the loop runs, so importing
    ``ModuleRegistration`` here is not circular.
    """
    # Populate the consent catalog (mailing.* feature keys, kept verbatim
    # for behavioural parity with the AI router's consent_required(...)
    # gates). Side-effect import — register_feature(...) runs at import.
    from app.modules.email_marketing.services import (  # noqa: F401
        ai_consent_features,
    )
    from app.modules.email_marketing import scheduler as _scheduler
    from app.modules.email_marketing.routers import (
        ai,
        analytics,
        automations,
        campaigns,
        contacts,
        lists,
        settings as em_settings,
        templates,
        unsubscribe,
        webhooks,
    )

    # Register the send-loop / scheduled-campaign / automation jobs on the
    # seed scheduler. start_scheduler()/stop_scheduler() are wired in
    # app/lifespan.py (returned as a TEXT delta — out of this module's
    # file scope; ModuleRegistration has no lifespan seam).
    _scheduler.configure()

    from app.main import ModuleRegistration

    return ModuleRegistration(
        routers=[
            contacts.router,
            lists.router,
            templates.router,
            campaigns.router,
            automations.router,
            analytics.router,
            em_settings.router,
            unsubscribe.router,
            webhooks.router,
            ai.router,
        ],
        # mailing used ("health","notificacoes","team","ai_outputs",
        # "ai_feedback"); social-wiring's W2.1 already requests health/
        # notificacoes/team — the assembly loop de-dupes, so we only need
        # to add the AI-output surfaces the email-marketing AI features use.
        standard_routers=("ai_outputs", "ai_feedback"),
    )


__all__ = ["register"]
