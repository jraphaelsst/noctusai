"""
NoctusAI Social Wiring — media-wiring-into-one-place CMS.

A seed-factory product. The cross-product capabilities (chatbot,
WhatsApp, Google, Meta, multimodal, credential store) are inherited from
``noctusai_lib`` / ``noctusai_seed``; this app composes them into the
Social Wiring product surface.

Run with: uvicorn app.main:app --reload --port 8011

LLM access is inherited automatically — ``create_product_app()``
auto-wires credential resolution + the default multi-provider LLMConfig.

────────────────────────────────────────────────────────────────────────
MODULE-REGISTRATION SEAM (W2.1 contract — for W2.2 email_marketing /
W2.3 scheduling)
────────────────────────────────────────────────────────────────────────
``main.py`` does NOT hard-list routers. It iterates ``MODULES`` — a list
of zero-arg callables, one per product module, each returning a
``ModuleRegistration`` (its routers + the standard-router names it
needs). A new module is added by:

  1. Creating ``app/modules/<name>/__init__.py`` exporting a
     ``register() -> ModuleRegistration`` callable.
  2. Appending ``from app.modules.<name> import register as _<name>``
     + ``_<name>`` to ``MODULES`` below.

W2.2 / W2.3 add their module WITHOUT editing the assembly logic — only
the ``MODULES`` list grows. Their migration tables go into the single
canonical ``migrations/001_social-wiring.sql`` under the
``-- W2.2 email_marketing`` / ``-- W2.3 scheduling`` section markers
already present in that file.

``ModuleRegistration``:
  - ``routers``: list[APIRouter] — included after the standard routers.
  - ``standard_routers``: tuple[str, ...] — names from the seed
    ``_STANDARD_ROUTERS`` registry this module needs (health /
    notificacoes / team / llm / ai_outputs / ai_feedback / scheduler);
    de-duplicated across modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from noctusai_seed import create_product_app

from app.config import settings
from app.lifespan import on_shutdown, on_startup
from app.rate_limit import limiter

# ─── Module-registration seam ────────────────────────────────────────


@dataclass
class ModuleRegistration:
    """What a product module contributes to the app.

    Returned by each module's ``register()`` callable; consumed by the
    assembly loop below. Adding a module never edits the loop — only
    ``MODULES`` grows.
    """

    routers: list = field(default_factory=list)
    standard_routers: tuple[str, ...] = ()


def _register_media_wiring() -> ModuleRegistration:
    """The W2.1 base module — chatbot / WhatsApp / Google / Meta /
    upload / videos / dashboard / intake-monitor / settings."""
    from app.routers.calendar_router import router as calendar_router
    from app.routers.chat_router import router as chat_router
    from app.routers.dashboard_router import router as dashboard_router
    from app.routers.google_router import router as google_router
    from app.routers.intake_monitor_router import router as intake_monitor_router
    from app.routers.meta_router import router as meta_router
    from app.routers.settings_router import oauth_router
    from app.routers.settings_router import router as settings_router
    from app.routers.upload_router import router as upload_router
    from app.routers.videos_router import router as videos_router
    from app.routers.whatsapp_router import router as whatsapp_router

    return ModuleRegistration(
        routers=[
            settings_router,
            oauth_router,
            upload_router,
            videos_router,
            dashboard_router,
            whatsapp_router,
            intake_monitor_router,
            chat_router,
            calendar_router,
            google_router,
            meta_router,
        ],
        standard_routers=("health", "notificacoes", "team"),
    )


# Append W2.2 (email_marketing) / W2.3 (scheduling) module ``register``
# callables here — the assembly loop below needs NO edit.
MODULES = [
    _register_media_wiring,
]

# ─── Assembly (module-agnostic — do not special-case modules here) ───

_routers: list = []
_standard: list[str] = []
for _register in MODULES:
    _reg = _register()
    _routers.extend(_reg.routers)
    for _name in _reg.standard_routers:
        if _name not in _standard:
            _standard.append(_name)

app = create_product_app(
    name="Social Wiring",
    schema="social_wiring",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=_standard,
    routers=_routers,
    # Conversation buffer + worker — boots the seed-backed
    # ConversationBufferService and the polling worker that drains the
    # debounce queue. See app/lifespan.py for the contract.
    lifespan_startup=on_startup,
    lifespan_shutdown=on_shutdown,
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py`:
    # consent_features="app.services.ai_consent_features",
)
