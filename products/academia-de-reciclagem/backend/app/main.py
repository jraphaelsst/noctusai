"""
NoctusAI Academia de Reciclagem — Julia's knowledge-base backend.

Run with: uvicorn app.main:app --reload --port 8015

SEED-1 (``project-history/roadmaps/julia-agents-academia-2026-09.md``,
slice A1b) mounts the contract §B.1–§B.5 knowledge-API routers over A1's
``KnowledgeStore`` (``app/knowledge/``), plus the seed's ``/api/auth`` +
``/api/settings/api-tokens`` router (the mint route an org admin uses to
issue the `agents` product's academia token — contract §B.0's "How the
agents product gets its academia token"). The scaffold's placeholder
``example_router`` / ``webhook_router`` skeletons are retired — this
product no longer has a "generic CRUD demo" surface, only the real API.

A1c adds the contract §B.6 admin import route (``import_router``),
``POST /api/import`` — a JSONL-or-multipart knowledge-bundle upload, so
it needs its own ``max_body_path_overrides`` entry (see
``_MAX_BODY_PATH_OVERRIDES`` below); the platform's 1 MB default exists
to DoS-guard inbound webhooks, and a legitimate bundle upload can
legitimately approach the route's own 20 MB business cap
(``app/importer/bundle.py::MAX_BUNDLE_BYTES``).

LLM access is inherited automatically — `create_product_app()` auto-wires
credential resolution + the default multi-provider LLMConfig. This
product currently has no LLM-backed feature.
"""
from noctusai_lib.api.auth.session import ApiTokenAuditMiddleware
from noctusai_seed import create_product_app
from noctusai_seed.auth_router import create_auth_router

from app.config import settings
from app.dependencies import (
    _LazyApiTokenResolver,
    _LazyAuditWriter,
    _legacy_jwt_resolver,
    auth_router_deps,
)
from app.rate_limit import limiter
from app.routers.content_router import router as content_router
from app.routers.decisions_router import router as decisions_router
from app.routers.import_router import router as import_router
from app.routers.interessados_router import router as interessados_router
from app.routers.kb_router import router as kb_router
from app.routers.questions_router import router as questions_router
from app.routers.roadmap_router import router as roadmap_router
from app.routers.sources_router import router as sources_router
from app.routers.timeline_router import router as timeline_router

# Contract §B.6: the import route's own business cap is 20 MB
# (`app/importer/bundle.py::MAX_BUNDLE_BYTES`) — this outer bound sits
# ~25% above it so a clear ``422 bundle_too_large`` (raised once the
# route reads the body) is what a caller sees for an over-cap upload,
# never an opaque 413 from the outer middleware. No dynamic path
# segment here, so the plain exact path is enough (see
# `products/igig/backend/app/main.py`'s `_MAX_BODY_PATH_OVERRIDES` for
# the wildcard-pattern footgun this avoids when a route DOES have one).
_MAX_BODY_PATH_OVERRIDES = {
    "/api/import": 25 * 1024 * 1024,  # 25 MB
}

# ONE combined router (`/api/auth` + `/api/settings/api-tokens`) — built
# directly via the factory (NOT `standard_routers=["auth"]`) so it gets
# THIS product's real `SupabaseApiTokenResolver` (via the lazy proxy —
# see `app.dependencies`'s own docstring for why eager construction here
# would race a test conftest's post-import patch) + legacy-JWT bridge,
# instead of the registry's Fake-resolver default. Mirrors
# `products/social-wiring/backend/app/main.py`'s "why the factory, not
# the registry" wiring.
_auth_router = create_auth_router(
    auth_router_deps,
    settings,
    api_token_resolver=_LazyApiTokenResolver(),
    legacy_jwt_resolver=_legacy_jwt_resolver,
)

app = create_product_app(
    name="Academia de Reciclagem",
    schema="academia_de_reciclagem",
    settings=settings,
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "team"],
    routers=[
        _auth_router,
        kb_router,
        decisions_router,
        questions_router,
        roadmap_router,
        content_router,
        timeline_router,
        sources_router,
        import_router,
        interessados_router,
    ],
    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,
    # Contract §D: a missing/empty approval-assertion key list must
    # refuse to boot in prod — a product-token write with no key
    # configured to verify against would otherwise 500 (or worse,
    # silently accept) on the very first assertion.
    required_prod_config=["APPROVAL_ASSERTION_SECRETS"],
    # Uncomment when this product registers AI features in
    # `app/services/ai_consent_features.py` (each product owns its
    # consent catalog — see KB § PATTERNS/lgpd.md § 9):
    # consent_features="app.services.ai_consent_features",
)

# Contract §B.0: audit every resolved product-token call
# (`api_token_audit`, best-effort, logged loudly on failure — never
# altering the response). Added AFTER `create_product_app` builds the
# app (before it serves any request) so it wraps every route,
# including the standard + auth routers above.
app.add_middleware(ApiTokenAuditMiddleware, audit_writer=_LazyAuditWriter())
