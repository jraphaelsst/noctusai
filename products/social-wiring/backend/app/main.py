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
    from app.routers.marcas_router import (
        router as marcas_router,
    )
    from app.routers.imoveis_router import (
        router as imoveis_router,
    )
    from app.routers.campanhas_router import (
        router as campanhas_router,
    )
    from app.routers.portal_roi_router import (
        router as portal_roi_router,
    )
    from app.routers.clientes_router import (
        router as clientes_router,
    )
    from app.routers.painel_router import (
        router as painel_router,
    )
    from app.services.meta import scheduler as meta_insights_scheduler
    from app.services import (
        clientes_backfill_job,
        clientes_inactivity_service,
        imoveis_sync_scheduler,
        whatsapp_backfill,
    )

    # Register the daily IG-snapshot job on the seed scheduler now (import
    # time) so it lands before `start_scheduler()` fires in app/lifespan.py
    # — mirrors `app.modules.email_marketing.register()`'s
    # `scheduler.configure()` call.
    meta_insights_scheduler.configure()
    # Same pattern for the WhatsApp inbox history backfill (W4.6,
    # whatsapp-realtime-inbox) — must be registered before
    # `start_scheduler()` fires or the job never runs.
    whatsapp_backfill.configure()
    # lead-card-hub Phase 1 steady state — attaches intake that landed after
    # the one-shot backfill to its cliente. Same import-time registration
    # rule as the two jobs above: before `start_scheduler()` in lifespan.
    clientes_backfill_job.configure()
    # lead-card-hub P1.5 (D16) — the 180-day inactivity sweep. Same
    # import-time registration rule; see
    # `app/services/clientes_inactivity_service.py`'s module docstring for
    # why `048` shipping the columns did NOT mean this was already wired.
    clientes_inactivity_service.configure()
    # Daily 00:05 America/Sao_Paulo refresh of the Vista catalog mirror.
    # Same import-time registration rule as the four jobs above. Until this
    # landed the mirror only moved when a human pressed the sync button —
    # it had gone 17 days stale.
    imoveis_sync_scheduler.configure()
    # Recovers identity extractions stranded in `pendente`/`processando` by a
    # process that died mid-read (a deploy, an OOM kill). Same import-time
    # registration rule as the five jobs above — see the module docstring for
    # why an unregistered sweep is a silent error rather than a missing
    # nicety.
    from app.modules.card_hub import extracao_scheduler as card_hub_extracao_scheduler

    card_hub_extracao_scheduler.configure()

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
            marcas_router,
            imoveis_router,
            campanhas_router,
            portal_roi_router,
            clientes_router,
            painel_router,
        ],
        standard_routers=("health", "notificacoes", "team"),
    )


from app.modules.card_hub import register as _card_hub
from app.modules.email_marketing import register as _register_email_marketing
from app.modules.imovel_hub import register as _imovel_hub
from app.modules.leads import register as _leads
from app.modules.mailchimp import register as _mailchimp
from app.modules.media_creation import register as _register_media_creation
from app.modules.meta_ads import register as _meta_ads
from app.modules.n8n import register as _n8n
from app.modules.pipeline import register as _pipeline
from app.modules.portal_leads import register as _portal_leads
from app.modules.scheduling import register as _scheduling
from app.modules.youtube import register as _youtube

# Append W2.2 (email_marketing) / W2.3 (scheduling) / W2.4 (media_creation)
# / Phase 8 (youtube) / Leads-module (leads) / Meta-Ads-console (meta_ads)
# module ``register`` callables here — the assembly loop below needs NO
# edit.
#
# 🔴 `_card_hub` is placed FIRST, deliberately BEFORE
# `_register_media_wiring` — route-ordering hazard, not an arbitrary
# choice. `_register_media_wiring`'s ``clientes_router`` declares a bare
# ``GET/PATCH /{cliente_id}`` (one path segment, plain-string matcher —
# FastAPI/Starlette do not auto-derive a UUID regex from the Python type
# hint). `card_hub`'s ``GET/POST /api/clientes/tags`` is a literal
# 1-segment path with the SAME shape, and Starlette matches the app's
# route table in REGISTRATION order across every mounted router, not
# just within one — the first structural match wins even if its own
# type coercion then 422s (this is exactly why ``clientes_router.py``
# itself declares ``/revisao`` before its own ``/{cliente_id}``; the
# same hazard now spans two routers, so it is resolved at the MODULES
# level instead of inside either router). Every other card_hub path is
# disambiguated by segment count or a distinct literal 2nd segment, so
# no other module needs reordering for this.
MODULES = [
    _card_hub,
    _register_media_wiring,
    _imovel_hub,
    _youtube,
    _register_email_marketing,
    _scheduling,
    _register_media_creation,
    _mailchimp,
    _leads,
    _meta_ads,
    _pipeline,
    _n8n,
    _portal_leads,
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

# Per-route body-size cap. The app-wide default (`settings.max_body_bytes`,
# 1 MB — see `noctusai_seed.ProductSettings`) exists to DoS-guard inbound
# webhooks; browser uploads legitimately exceed it and need their own,
# larger, per-route ceiling instead of weakening the default everywhere.
# The longest matching prefix wins (see
# `noctusai_lib.api.middleware.MaxBodySizeMiddleware`).
_MAX_BODY_PATH_OVERRIDES = {
    # Browser drag-and-drop video upload (POST /api/videos/upload[/from-code]).
    # `stage_browser_upload` streams straight to disk (no full-body
    # buffering), so the ceiling only needs to bound worst-case disk use
    # per upload, not memory — 500 MB comfortably covers a phone/drone
    # property walkthrough video (typically 100-300 MB for a few minutes
    # of 1080p/4K) while still refusing an unbounded multi-GB stream.
    "/api/videos/upload": 500 * 1024 * 1024,  # 500 MB
    # Client document/photo upload (POST /api/clientes/{cliente_id}/documentos
    # — card_hub, lead-card-hub Phase 2, migration 057). `{cliente_id}` is a
    # dynamic UUID path param BEFORE the segment that needs the bigger cap,
    # so a plain prefix can't express this: `/api/clientes` alone would also
    # raise the cap on every JSON clientes route (list/create/tags/timeline/
    # notas/...), silently weakening the guard everywhere else under this
    # router. The `*` wildcard matches exactly that one dynamic segment and
    # nothing else (see `noctusai_lib.api.middleware.MaxBodySizeMiddleware`'s
    # docstring). Unlike the video path, `upload_documento_route` reads the
    # WHOLE file into memory (`await file.read()`) before handing it to
    # storage, so this ceiling bounds memory, not just disk — 30 MB covers a
    # phone photo (3-8 MB) and a larger HDR/RAW-derived export (brief:
    # "25 MB+") with headroom, while staying far below the video path's
    # disk-bound 500 MB. `documentos_service.MAX_UPLOAD_BYTES` (25 MB) is the
    # real business-policy limit and stays comfortably under this outer
    # bound — the middleware is the platform-wide safety net, not the policy.
    "/api/clientes/*/documentos": 30 * 1024 * 1024,  # 30 MB
    # Imóvel document upload (POST /api/imoveis/{codigo}/documentos —
    # imovel_hub, migration 075). Same `*` wildcard reasoning as the clientes
    # path above: `{codigo}` is a dynamic segment BEFORE the one that needs
    # the bigger cap, so a plain `/api/imoveis` prefix would also raise the
    # ceiling on every JSON imoveis route (list/filtros/caracteristicas/sync),
    # weakening the guard where it is doing real work.
    #
    # 50 MB rather than the clientes path's 30: a certidão de matrícula with
    # decades of averbações is routinely 20-40 pages of scan, where an RG is
    # one photo. `imovel_hub.documentos_service.MAX_UPLOAD_BYTES` (40 MB) is
    # the business-policy limit and stays under this outer bound — the
    # middleware is the platform-wide safety net, not the policy.
    "/api/imoveis/*/documentos": 50 * 1024 * 1024,  # 50 MB
    # Financiamento/escritura upload (POST
    # /api/clientes/{cliente_id}/financiamento/documentos — migration 078).
    # A SEPARATE entry from the `/api/clientes/*/documentos` one above even
    # though both sit under `/api/clientes/{id}`: the wildcard matches exactly
    # one dynamic segment, so `/api/clientes/*/documentos` does not cover
    # `/api/clientes/*/financiamento/documentos`. Without this line the
    # financing uploads would silently fall back to the platform default and
    # reject an ordinary imposto de renda PDF.
    #
    # 30 MB, same as the clientes path: `financiamento_service`'s own
    # MAX_UPLOAD_BYTES (25 MB) is the business-policy limit and stays under it.
    "/api/clientes/*/financiamento/documentos": 30 * 1024 * 1024,  # 30 MB
    # Checklist-extra upload (POST
    # /api/clientes/{cliente_id}/checklist-extras/{extra_id}/documento —
    # card_hub, migration 083). A THIRD `/api/clientes` entry, for the same
    # reason the financiamento one is a second: pattern keys match on exact
    # segment count, so neither of the entries above covers this five-segment
    # shape. It routes through `documentos_service.upload_documento` — the same
    # 25 MB business-policy limit and the same whole-file-into-memory read — so
    # it gets the same 30 MB outer bound as the plain clientes path. Without
    # this line an operator attaching an ordinary phone photo (3-8 MB) to a
    # checklist line would get a 413 from the middleware, before the route that
    # would have accepted it ever ran.
    "/api/clientes/*/checklist-extras/*/documento": 30 * 1024 * 1024,  # 30 MB
}

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
    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py`:
    # consent_features="app.services.ai_consent_features",
)
