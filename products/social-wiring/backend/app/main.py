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
W2.3 scheduling / Phase 8 youtube)
────────────────────────────────────────────────────────────────────────
``main.py`` does NOT hard-list routers. It iterates ``MODULES`` — a list
of zero-arg callables, one per product module, each returning a
``ModuleRegistration`` (its routers + the standard-router names it
needs). A new module is added by:

  1. Creating ``app/modules/<name>/__init__.py`` exporting a
     ``register() -> ModuleRegistration`` callable.
  2. Appending ``from app.modules.<name> import register as _<name>``
     + ``_<name>`` to ``MODULES`` below.

W2.2 / W2.3 / Phase 8 add their module WITHOUT editing the assembly
logic — only the ``MODULES`` list grows. Their migration tables go into
the single canonical ``migrations/001_social-wiring.sql`` under the
``-- W2.2 email_marketing`` / ``-- W2.3 scheduling`` section markers
already present in that file. The Phase 8 ``youtube`` module adds no new
DDL — it folds existing W2.1 tables (``video_cache``, ``upload_jobs``)
unchanged.

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
    intake-monitor / non-youtube settings + the W2 auth-router pair
    (login/me/logout + api-token management).

    The auth-router pair is consumed directly from the seed's
    ``noctusai_seed.auth_router.create_auth_router(deps, settings)``
    factory (promoted from this product's own former
    ``app/routers/auth.py`` fork per the ``erp-httponly-cookie-session-
    2026-07`` roadmap, Slice 1b) — NOT via ``standard_routers=["auth"]``.
    The registry's ``_build_auth_router(deps, settings, product_name,
    version)`` builder has a fixed 4-arg signature shared by every
    standard router, with no seam to thread this product's REAL
    ``SupabaseApiTokenResolver`` / legacy-JWT bridge through; calling the
    factory directly here passes both, so ``pk_*`` bearer + legacy-JWT
    callers of ``/api/auth/me``, ``/logout``, and the api-token endpoints
    keep resolving exactly as they did under the fork (the bare registry
    entry defaults to the seed's always-empty ``FakeApiTokenResolver()``
    + no bridge — a real regression for THIS product, see
    ``create_auth_router``'s docstring).

    YouTube footprint (videos / upload / dashboard / YouTube tab + OAuth
    callback) moved to ``app.modules.youtube`` in Phase 8 and is
    registered as its own ``MODULES`` entry below."""
    from noctusai_seed.auth_router import create_auth_router

    from app.dependencies import (
        _LazyApiTokenResolver,
        _legacy_jwt_resolver,
        auth_router_deps,
    )
    from app.routers.calendar_router import router as calendar_router
    from app.routers.chat_router import router as chat_router
    from app.routers.google_router import router as google_router
    from app.routers.intake_monitor_router import router as intake_monitor_router
    from app.routers.meta_comments_router import router as meta_comments_router
    from app.routers.meta_content_router import router as meta_content_router
    from app.routers.meta_context_router import router as meta_context_router
    from app.routers.meta_dms_router import router as meta_dms_router
    from app.routers.meta_insights_router import router as meta_insights_router
    from app.routers.settings_router import router as settings_router
    from app.routers.whatsapp_router import router as whatsapp_router
    from app.routers.whatsapp_connections_router import (
        router as whatsapp_connections_router,
    )

    from app.routers.integration_accounts_router import (
        router as integration_accounts_router,
    )
    from app.routers.clients_router import (
        router as clients_router,
    )
    from app.services.meta import scheduler as meta_insights_scheduler

    # Register the daily IG-snapshot job on the seed scheduler now (import
    # time) so it lands before `start_scheduler()` fires in app/lifespan.py
    # — mirrors `app.modules.email_marketing.register()`'s
    # `scheduler.configure()` call.
    meta_insights_scheduler.configure()

    # ONE combined router (`/api/auth` + `/api/settings/api-tokens`) —
    # see the module docstring above for why this calls the factory
    # directly instead of opting into `standard_routers=["auth"]`.
    #
    # `_LazyApiTokenResolver()` (NOT `_get_api_token_resolver()` called
    # eagerly here) — the real resolver construction touches
    # `get_admin_client()` -> `DatabaseModule.get_admin_client()`, which
    # the test conftest only patches AFTER `app.main` starts importing
    # (`tests/conftest.py::client`'s `with patch(...)` wraps `from
    # app.main import app`). Building the real resolver at MODULE-IMPORT
    # time here (this function runs during that import, via the MODULES
    # assembly loop) would race that patch — resolving too early against
    # an unpatched `DatabaseModule`. The lazy proxy defers to
    # `_get_api_token_resolver()` on the FIRST per-request `.resolve()`
    # call instead, matching the same lazy-singleton shape
    # `app.dependencies.get_auth_context` already uses.
    auth_router = create_auth_router(
        auth_router_deps,
        settings,
        api_token_resolver=_LazyApiTokenResolver(),
        legacy_jwt_resolver=_legacy_jwt_resolver,
    )

    return ModuleRegistration(
        routers=[
            auth_router,
            settings_router,
            whatsapp_router,
            whatsapp_connections_router,
            intake_monitor_router,
            chat_router,
            calendar_router,
            google_router,
            meta_insights_router,
            meta_context_router,
            meta_content_router,
            meta_comments_router,
            meta_dms_router,
            integration_accounts_router,
            clients_router,
        ],
        standard_routers=("health", "notificacoes", "team"),
    )


from app.modules.email_marketing import register as _register_email_marketing
from app.modules.leads import register as _leads
from app.modules.mailchimp import register as _mailchimp
from app.modules.media_creation import register as _register_media_creation
from app.modules.meta_ads import register as _meta_ads
from app.modules.n8n import register as _n8n
from app.modules.pipeline import register as _pipeline
from app.modules.scheduling import register as _scheduling
from app.modules.youtube import register as _youtube

# Append W2.2 (email_marketing) / W2.3 (scheduling) / W2.4 (media_creation)
# / Phase 8 (youtube) / Leads-module (leads) / Meta-Ads-console (meta_ads)
# module ``register`` callables here — the assembly loop below needs NO
# edit.
MODULES = [
    _register_media_wiring,
    _youtube,
    _register_email_marketing,
    _scheduling,
    _register_media_creation,
    _mailchimp,
    _leads,
    _meta_ads,
    _pipeline,
    _n8n,
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

# Static, keeper-auditable literal of the standard-router set the MODULES
# seam resolves at runtime. The MODULES registration stays the runtime
# source-of-truth; this asserts they agree (loud — no silent drift).
#
# NOTE: this is the MODULE-CONTRIBUTED base only. Product-GLOBAL standard
# routers (page-visibility, etc.) are NOT module-contributed — they are added
# on top in the create_product_app `standard_routers` literal below. So that
# opt-in list = _STANDARD_ROUTERS ∪ {product-global additions}; the two
# literals intentionally differ. The create_product_app call site remains a
# plain string-list literal so check_standard_routers_audit can parse it.
_STANDARD_ROUTERS = ["health", "notificacoes", "team", "ai_outputs", "ai_feedback"]
assert _standard == _STANDARD_ROUTERS, (
    f"standard_routers drift: MODULES resolved {_standard!r} but the "
    f"keeper-audited literal is {_STANDARD_ROUTERS!r}. Update _STANDARD_ROUTERS "
    f"to match the MODULES seam (and re-audit)."
)

app = create_product_app(
    name="Social Wiring",
    schema="social_wiring",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    # Module-contributed base (_STANDARD_ROUTERS) + product-global "status_paginas".
    standard_routers=["health", "notificacoes", "team", "ai_outputs", "ai_feedback", "status_paginas"],
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
