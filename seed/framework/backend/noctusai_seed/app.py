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
import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional

from fastapi import FastAPI

from noctusai_shared.logging_config import configure_logging
from noctusai_shared.app_factory import configure_app

from noctusai_seed.database import create_database_module
from noctusai_seed.dependencies import create_dependencies
from noctusai_seed.routers import create_standard_routers

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
) -> FastAPI:
    """Create a fully configured FastAPI app for a NoctusAI product.

    This sets up everything structural:
      - Logging (JSON in prod, human-readable in dev)
      - Database clients (product schema + core schema)
      - Auth dependencies (get_current_user, get_org_id, etc.)
      - Standard routers (health, notifications, team)
      - CORS, Sentry, exception handlers, middleware, rate limiting
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

    Returns:
        Configured FastAPI application instance.

    The app instance has extra attributes for product code to access:
      - app.state.db: DatabaseModule instance
      - app.state.deps: ProductDependencies instance
    """
    # 1. Configure logging
    app_name = schema.replace("_", "-").replace(" ", "-").lower()
    configure_logging(debug=settings.debug, json_logs=not settings.debug, app_name=app_name)

    # 2. Create database module and dependencies
    db = create_database_module(settings, schema)
    deps = create_dependencies(db)

    # 3. Create lifespan if startup/shutdown hooks provided
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if lifespan_startup:
            await lifespan_startup() if _is_coroutine(lifespan_startup) else lifespan_startup()
        yield
        if lifespan_shutdown:
            await lifespan_shutdown() if _is_coroutine(lifespan_shutdown) else lifespan_shutdown()

    has_lifespan = lifespan_startup or lifespan_shutdown

    # 4. Create the FastAPI app
    app = FastAPI(
        title=f"NoctusAI {name} API",
        description=f"Backend API for {name}",
        version=version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan if has_lifespan else None,
    )

    # 5. Attach db and deps to app state for product code access
    app.state.db = db
    app.state.deps = deps

    # 6. Apply shared configuration (Sentry, CORS, exceptions, middleware, rate limiting)
    configure_app(app, settings, limiter=limiter)

    # 7. Register standard routers (health, notifications, team)
    for router in create_standard_routers(deps, settings, product_name=name, version=version):
        app.include_router(router)

    # 8. Register product-specific routers
    if routers:
        for router in routers:
            app.include_router(router)

    logger.info("Product app '%s' created (schema=%s)", name, schema)
    return app


def _is_coroutine(fn) -> bool:
    """Check if a function is a coroutine function."""
    import asyncio
    return asyncio.iscoroutinefunction(fn)
