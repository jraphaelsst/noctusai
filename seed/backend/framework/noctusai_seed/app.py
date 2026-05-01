"""
Product application factory.

This is the core of the seed framework. Products call create_product_app()
to get a fully configured FastAPI application with all structural bones
already in place.

Usage::

    from noctusai_seed import create_product_app, ProductSettings

    class MailingSettings(ProductSettings):
        resend_api_key: str = ""

    settings = MailingSettings()

    app = create_product_app(
        name="Mailing",
        schema="mailing",
        settings=settings,
        routers=[contacts.router, campaigns.router],
        version="0.1.0",
    )
"""
import importlib
import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional, Sequence

from fastapi import FastAPI

from noctusai_lib.domain.ai.consent import configure_consent_module
from noctusai_lib.logging_config import configure_logging
from noctusai_lib.api.app_factory import configure_app
from noctusai_lib.config.credentials import configure_credentials
from noctusai_lib.integrations.llm import LLMConfig
from noctusai_lib.integrations.llm.budget import configure_budget_module
from noctusai_lib.integrations.llm.client import configure_llm, shutdown_llm

from noctusai_seed.database import create_database_module
from noctusai_seed.dependencies import create_dependencies
from noctusai_seed.llm_defaults import default_llm_config
from noctusai_seed.routers import build_standard_routers

logger = logging.getLogger(__name__)


def create_product_app(
    name: str,
    schema: str,
    settings,
    routers: Optional[list] = None,
    version: str = "0.1.0",
    lifespan_startup: Optional[Callable] = None,
    lifespan_shutdown: Optional[Callable] = None,
    limiter=None,
    llm_config: Optional[LLMConfig] = None,
    *,
    standard_routers: Sequence[str] = (),
    consent_features: Optional[str] = None,
) -> FastAPI:
    """Create a fully configured FastAPI app for a NoctusAI product.

    This sets up everything structural:
      - Logging (JSON in prod, human-readable in dev)
      - Database clients (product schema + core schema)
      - Auth dependencies (get_current_user, get_org_id, etc.)
      - Standard routers (health, notifications, team)
      - CORS, Sentry, exception handlers, middleware, rate limiting
      - **Credential resolution** via `noctusai_lib.config.credentials` (auto-configured
        from settings.supabase_*)
      - **Multi-provider LLM access** via `noctusai_lib.integrations.llm` (inherits
        `default_llm_config()` unless overridden via `llm_config=`)
      - Optional lifespan events (scheduler start/stop, recovery tasks)

    Args:
        name: Human-readable product name (e.g. "Mailing", "ERP Imobiliario")
        schema: Database schema name (e.g. "mailing", "erp")
        settings: Product settings instance (extends ProductSettings)
        routers: List of product-specific APIRouter instances
        version: API version string
        lifespan_startup: Async callable to run on startup (e.g. start scheduler)
        lifespan_shutdown: Async callable to run on shutdown (e.g. stop scheduler)
        limiter: Rate limiter instance (from create_limiter)
        llm_config: Override the default LLMConfig. Use `default_llm_config(
            **overrides)` from `noctusai_seed` when you want to tweak one or
            two fields; pass None to inherit the platform defaults verbatim.
        standard_routers: Which bundled routers to register. Valid names are
            the keys of `noctusai_seed.routers._STANDARD_ROUTERS`
            ("health", "notificacoes", "team", "llm"). Defaults to `()` —
            explicit opt-in, so a product that forgets to declare the kwarg
            gets none of the bundled capabilities rather than silently
            inheriting all four.
        consent_features: Dotted module path whose import-time side effect
            populates the `noctusai_lib.domain.ai.consent` catalog (each product
            calls `register_feature(...)` from this module). The framework
            imports it once per process via `importlib.import_module(...)`,
            after `configure_consent_module(...)`. Default `None` — products
            with no consent-gated AI features can omit the kwarg. **One named
            seam**, removes the per-product `from app.services import
            ai_consent_features  # noqa: F401` line in `app/main.py`. If the
            module cannot be imported, the framework logs a warning and
            continues — the catalog stays empty, which is the same posture
            as not setting the kwarg at all (fail-closed at request time
            via `is_granted` resolution rule 4: unknown feature → False).

    Returns:
        Configured FastAPI application instance.

    The app instance has extra attributes for product code to access:
      - app.state.db: DatabaseModule instance
      - app.state.deps: ProductDependencies instance
    """
    # 1. Configure logging
    app_name = schema.replace("_", "-").replace(" ", "-").lower()
    configure_logging(debug=settings.debug, json_logs=not settings.debug, app_name=app_name)

    # 2. Auto-wire credential resolution (Tier 1+2 need a public-schema client).
    #    Every product's settings carries the same Supabase URL + keys from the
    #    root .env — per the single-source-.env rule — so this one call at the
    #    framework level sets up credential resolution for every product.
    configure_credentials(
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
        supabase_service_role_key=settings.supabase_service_role_key,
    )

    # 3. Create database module first — the LLM usage sink (if opted in)
    #    needs a service-role client to write under RLS.
    db = create_database_module(settings, schema)
    deps = create_dependencies(db)

    # 4. Auto-wire LLM access. Products inherit platform defaults unless they
    #    override via the llm_config parameter. `REDIS_URL` flips the
    #    response cache on; `LLM_USAGE_TRACKING=1` flips the DB usage sink on.
    usage_db = None
    if getattr(settings, "llm_usage_tracking", False):
        try:
            usage_db = db.get_admin_client()
        except Exception as exc:
            logger.warning(
                "llm_usage_tracking=True but admin client unavailable: %s", exc,
            )
    effective_llm_config = llm_config or default_llm_config(
        redis_url=getattr(settings, "redis_url", None),
        usage_tracking_db=usage_db,
        usage_tracking_schema=schema if usage_db is not None else None,
    )
    configure_llm(effective_llm_config)

    # Phase 18 budget guardrails — wire the admin-client factory so
    # `chat_completion` can raise `LLMBudgetExceeded` before dispatch.
    # Only enable when LLM usage tracking is on (otherwise there's no
    # `<schema>.llm_usage` data to compute spend from).
    if usage_db is not None:
        try:
            configure_budget_module(admin_client_factory=db.get_admin_client)
        except Exception as exc:
            logger.warning(
                "configure_budget_module failed (budget guard disabled): %s", exc,
            )

    # consent-guard-rollout Phase 1 — wire the FastAPI deps the
    # `consent_required(feature_key)` factory uses to resolve user_id +
    # admin DB client at request time. Default ON: any product calling
    # `create_product_app` gets the guard primitive available; products
    # that don't import `consent_required(...)` pay zero overhead. Disable
    # with `settings.consent_gating = False` (rare — only useful when a
    # product needs to bypass consent entirely, e.g. internal tooling).
    if getattr(settings, "consent_gating", True):
        try:
            configure_consent_module(
                get_current_user=deps.get_current_user,
                admin_client_factory=db.get_admin_client,
            )
        except Exception as exc:
            logger.warning(
                "configure_consent_module failed (consent guard disabled): %s", exc,
            )

    # Auto-load the product's consent feature catalog. The dotted path's
    # `register_feature(...)` calls populate the platform-wide catalog at
    # boot — one named seam instead of an import-for-side-effects line in
    # every product's main.py. Failure is non-fatal: catalog stays empty
    # and `is_granted` fails-closed at request time per its resolution
    # rules (unknown feature → False).
    if consent_features:
        try:
            importlib.import_module(consent_features)
        except Exception as exc:
            logger.warning(
                "consent_features=%r could not be imported (catalog stays empty): %s",
                consent_features,
                exc,
            )

    # 5. Create lifespan — always active so we own shutdown_llm(). Product
    #    startup/shutdown hooks are composed with the framework's.
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if lifespan_startup:
            await lifespan_startup() if _is_coroutine(lifespan_startup) else lifespan_startup()
        try:
            yield
        finally:
            if lifespan_shutdown:
                await lifespan_shutdown() if _is_coroutine(lifespan_shutdown) else lifespan_shutdown()
            # Framework-level cleanup — release LLM provider pools.
            await shutdown_llm()

    has_lifespan = True  # now always true — we own shutdown_llm

    # 6. Create the FastAPI app
    app = FastAPI(
        title=f"NoctusAI {name} API",
        description=f"Backend API for {name}",
        version=version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan if has_lifespan else None,
    )

    # 7. Attach db and deps to app state for product code access
    app.state.db = db
    app.state.deps = deps

    # 8. Apply shared configuration (Sentry, CORS, exceptions, middleware, rate limiting)
    configure_app(app, settings, limiter=limiter)

    # 9. Register the standard routers the product opted into.
    #    `standard_routers` defaults to `()` — explicit opt-in per the
    #    "authorized/scoped access" rule set by the core-seed-wiring
    #    project. A product that forgets to declare the kwarg gets none
    #    of the bundled capabilities.
    for router in build_standard_routers(
        deps, settings, product_name=name, version=version, names=standard_routers,
    ):
        app.include_router(router)

    # 10. Register product-specific routers
    if routers:
        for router in routers:
            app.include_router(router)

    from noctusai_seed._version import __seed_version__
    from noctusai_lib._version import __lib_version__
    logger.info(
        "Product app '%s' created (schema=%s, seed_version=%s, lib_version=%s)",
        name,
        schema,
        __seed_version__,
        __lib_version__,
    )
    return app


def _is_coroutine(fn) -> bool:
    """Check if a function is a coroutine function."""
    import asyncio
    return asyncio.iscoroutinefunction(fn)
