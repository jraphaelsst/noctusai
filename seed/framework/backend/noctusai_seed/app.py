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
import os
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Optional, Sequence

from fastapi import FastAPI

from noctusai_lib.domain.ai.consent import configure_consent_module
from noctusai_lib.logging_config import configure_logging, resolve_json_logs
from noctusai_lib.api.app_factory import configure_app
from noctusai_lib.api.middleware import MaxBodyOverrideValue
from noctusai_lib.config.credentials import configure_credentials
from noctusai_lib.config.deploy_config import (
    baseline_required_prod_env,
    require_prod_config,
)
from noctusai_lib.integrations.llm import LLMConfig
from noctusai_lib.integrations.llm.budget import configure_budget_module
from noctusai_lib.integrations.llm.client import configure_llm, shutdown_llm

from noctusai_seed.database import create_database_module
from noctusai_seed.dependencies import create_dependencies
from noctusai_seed.health import HealthEndpointConfig, mount_health_endpoints
from noctusai_seed.llm_defaults import default_llm_config
from noctusai_seed.routers import build_standard_routers
from noctusai_seed.upload_route_overrides import enforce_upload_route_overrides

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
    health_config: Optional[HealthEndpointConfig] = None,
    serve_spa: Optional[str] = None,
    required_prod_config: Optional[list[str]] = None,
    max_body_path_overrides: Optional[Mapping[str, MaxBodyOverrideValue]] = None,
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
        health_config: Optional `HealthEndpointConfig` declaring liveness +
            readiness hooks for the seed-baked `/_health` and `/_ready`
            endpoints. Default `None` → empty config → both endpoints exist
            and always return `{ok: true, checks: []}` (the polite seed
            default). Products opt-in to richer probes by passing a
            populated config::

                from noctusai_seed import HealthEndpointConfig

                async def db_ping() -> tuple[bool, str | None]:
                    try:
                        db.get_admin_client().table("notifications") \
                            .select("id").limit(1).execute()
                        return (True, None)
                    except Exception as exc:
                        return (False, str(exc))

                app = create_product_app(
                    ...,
                    health_config=HealthEndpointConfig(
                        readiness_hooks=[db_ping],
                    ),
                )

            Liveness checks should be FAST + light (process responsiveness
            only — keep them network-free); readiness checks may include
            DB / Redis / vendor pings. Hook exceptions are caught + logged
            at WARN, never escalated to a 500.
        serve_spa: Single-container mode. Absolute/relative path to a built
            SPA bundle directory (must contain `index.html`). When set (or
            when the `SERVE_SPA_DIR` env var is set — the param wins), the
            built frontend is mounted at `/` AFTER every API/ops route, with
            an SPA fallback (unknown *extension-less* path → `index.html` so
            client-side routing works; a missing *asset* path → real 404 so
            broken bundles surface). `/api/*`, `/_health`, `/_ready`,
            `/docs` keep priority — mounts are matched after routes.
            Default `None` → no mount (two-container / `native` dev mode,
            where Vite serves the frontend on its own port). If set but the
            directory has no `index.html`, the framework logs a WARNING and
            continues serving the API only (no silent failure, no crash).

    Returns:
        Configured FastAPI application instance.

    The app instance has extra attributes for product code to access:
      - app.state.db: DatabaseModule instance
      - app.state.deps: ProductDependencies instance
        required_prod_config: Optional list of env var names that MUST be set in
            a deploy context (``is_deploy_context()`` True). Boot aborts loudly
            via ``MissingProdConfigError`` listing every missing key; no-op in
            dev. Opt-in (default None) — the deploy-config-contract seam every
            product inherits. See ``KB § PATTERNS/deploy-config-contract.md``.
        max_body_path_overrides: Per-route request-body-size cap, layered on
            top of the app-wide ``settings.max_body_bytes`` (default 1 MB —
            right for webhooks, wrong for uploads). ``{"<path-prefix-or-*-pattern>":
            <max-bytes-or-KEEP_DEFAULT_MAX_BODY>, ...}``; the longest matching
            prefix (or an exact ``*``-wildcard pattern) wins, everything else
            keeps the app-wide default. Falls back to
            ``settings.max_body_path_overrides`` when the kwarg is omitted, so
            a product can declare it via its settings class instead if that
            fits its wiring better. Default `None` — no overrides, unchanged
            behavior. See ``noctusai_lib.api.middleware.MaxBodySizeMiddleware``.

            **Enforced at boot, not left to hand-maintenance:** every route
            (across ``routers`` and ``standard_routers``) whose endpoint
            declares an ``UploadFile`` parameter — in any annotation shape,
            recursively unwrapped — MUST have a matching entry here or
            ``create_product_app`` raises ``RuntimeError`` and refuses to
            finish booting. Map a route that should genuinely stay at the
            default to ``noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY``
            instead of omitting it. See
            ``noctusai_seed.upload_route_overrides``.
    """
    # 1. Configure logging
    app_name = schema.replace("_", "-").replace(" ", "-").lower()
    # Format is resolved SEPARATELY from level. `not settings.debug` stays the
    # default (JSON in prod, readable in dev), but `NOCTUSAI_JSON_LOGS` can
    # override it without touching `DEBUG` — which also gates the log level and
    # `/docs` exposure. Wanting readable prod logs must never cost an exposed
    # OpenAPI schema, which is precisely what it cost until 2026-08-24.
    configure_logging(
        debug=settings.debug,
        json_logs=resolve_json_logs(default=not settings.debug),
        app_name=app_name,
    )

    # 1a. Deploy-config guard — fail loud at boot if a required-in-prod config
    #     key is unset in a deploy context (no-op in dev). The seam every product
    #     inherits with zero per-product code; a missing key aborts the boot
    #     listing every gap at once, never a half-booted app silently serving dev
    #     values. Two sources fold together:
    #       • the fleet-wide baseline (`REDIS_SESSION_ENCRYPTION_KEY`) — added
    #         only when this product runs against a real Redis session store
    #         (`settings.redis_url` set), exactly when the auth_router's
    #         `make_session_store(require_encryption=True)` would otherwise fail
    #         lazily on first session read; declaring it here fails fast + is the
    #         same list `noctus.dev.predeploy_check` audits pre-deploy.
    #       • the per-product opt-in `required_prod_config=[...]`.
    #     → KB § PATTERNS/deploy-config-contract.md
    _required_prod_keys: list[str] = list(required_prod_config or [])
    if getattr(settings, "redis_url", None):
        for _k in baseline_required_prod_env():
            if _k not in _required_prod_keys:
                _required_prod_keys.append(_k)
    if _required_prod_keys:
        require_prod_config(_required_prod_keys)

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
        # Local-dev SQLite backend — materialize the pre-seeded file on
        # every boot (idempotent) so a scaffolded product runs
        # end-to-end day-one with NO Supabase project. Double-gated:
        # only when DATABASE_BACKEND=sqlite (the config validator
        # already fails loud if that is set in a prod-shaped env), so
        # this is dead code in every prod/CI boot — parallel,
        # never-modify. Zero per-product code (single seed seam).
        if getattr(settings, "database_backend", "supabase") == "sqlite":
            from noctusai_seed.apply_sqlite_migrations import (
                apply_sqlite_migrations as _apply_sqlite,
            )

            _apply_sqlite(settings)

        # A product startup hook is a SIDE EFFECT (recover stuck rows, schedule
        # pending jobs, start a scheduler) — never a precondition for serving.
        # Letting it raise out of `lifespan` makes uvicorn print "Application
        # startup failed. Exiting." and kill the process, so ONE transient
        # upstream hiccup (a PostgREST TLS reset, Redis not up yet) takes the
        # whole product down and it never recovers on its own. That is exactly
        # what stranded erp-imobiliario on the dev fleet for 13 days
        # (2026-08-10) while prod — same code, healthy network — served fine.
        #
        # This is NOT a silent fallback: the failure is logged at ERROR with
        # the full traceback AND parked on `app.state.startup_hook_error`,
        # which `/api/health` reports verbatim (see
        # `noctusai_seed.routers._create_health_router`). The named destination
        # is that field — an operator reading health sees a degraded boot
        # instead of a container that merely refuses to exist.
        # → KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md
        app.state.startup_hook_error = None
        if lifespan_startup:
            try:
                await lifespan_startup() if _is_coroutine(lifespan_startup) else lifespan_startup()
            except Exception as exc:  # noqa: BLE001 — see the block comment above
                app.state.startup_hook_error = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "%s: lifespan_startup hook %r FAILED — the API is starting "
                    "anyway and serving DEGRADED; /api/health reports "
                    "startup_hook_error. Whatever this hook was supposed to do "
                    "(recovery / scheduling) did NOT happen.",
                    name,
                    getattr(lifespan_startup, "__name__", lifespan_startup),
                )
        try:
            yield
        finally:
            if lifespan_shutdown:
                # Same reasoning on the way out, plus one more: an exception
                # here would skip `shutdown_llm()` below and leak the provider
                # pools on every shutdown.
                try:
                    await lifespan_shutdown() if _is_coroutine(lifespan_shutdown) else lifespan_shutdown()
                except Exception:  # noqa: BLE001 — see above
                    logger.exception(
                        "%s: lifespan_shutdown hook %r FAILED — continuing "
                        "framework cleanup so LLM provider pools still close.",
                        name,
                        getattr(lifespan_shutdown, "__name__", lifespan_shutdown),
                    )
            # Framework-level cleanup — release LLM provider pools.
            await shutdown_llm()

    has_lifespan = True  # now always true — we own shutdown_llm

    # 6. Create the FastAPI app
    app = FastAPI(
        title=f"NoctusAI {name} API",
        description=f"Backend API for {name}",
        version=version,
        # All THREE, not two. `docs_url=None` only removes the Swagger *page*;
        # FastAPI keeps serving `openapi_url` regardless, and that is the half
        # that matters — the browsable page is a convenience, the JSON schema is
        # the machine-readable map of every route, parameter, and response model.
        # Prod had all three open (2026-08-24); gating only the first two would
        # have closed the door and left the blueprint on the step.
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan if has_lifespan else None,
    )

    # 7. Attach db and deps to app state for product code access
    app.state.db = db
    app.state.deps = deps

    # 8. Apply shared configuration (Sentry, CORS, exceptions, middleware, rate limiting)
    _effective_max_body_path_overrides = configure_app(
        app, settings, limiter=limiter,
        max_body_path_overrides=max_body_path_overrides,
    )

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

    # 10a. Boot-time refusal: every route mounted above (9 + 10) whose
    #      endpoint declares an UploadFile parameter MUST have a matching
    #      entry in max_body_path_overrides. MUST run here — after every
    #      router is mounted — not inside `configure_app` (step 8), which
    #      builds MaxBodySizeMiddleware before any router exists, so
    #      `app.routes` is empty at that point and there would be nothing
    #      to check. `_effective_max_body_path_overrides` (not the raw
    #      `max_body_path_overrides` param) is used so this validates
    #      against the SAME map the middleware is actually enforcing,
    #      including when a product declares overrides via
    #      `settings.max_body_path_overrides` instead of the kwarg. See
    #      `noctusai_seed.upload_route_overrides` /
    #      `KB § PATTERNS/backend/upload-route-body-override-derivation.md`.
    enforce_upload_route_overrides(
        app, _effective_max_body_path_overrides, product_name=name,
    )

    # 11. Mount the seed-baked /_health + /_ready ops endpoints. Idempotent
    #     by design (raises if mounted twice on the same app). An empty
    #     `HealthEndpointConfig()` is the polite default — every product
    #     gets the endpoints, and a product that doesn't opt-in still
    #     answers 200 with `checks=[]`. Mounted last so probe URLs sit
    #     alongside the product's routes (no path conflicts: `/_*`
    #     prefix is reserved for ops surfaces).
    mount_health_endpoints(app, health_config or HealthEndpointConfig())

    # 12. Single-container mode — serve the built SPA from this process.
    #     Mounted LAST so every API/ops route (steps 9-11) wins; the mount
    #     only catches what no route matched. `serve_spa=` param beats the
    #     `SERVE_SPA_DIR` env var (compose injects the env in the prod
    #     image; tests/products may pass the param explicitly).
    spa_dir = serve_spa or os.environ.get("SERVE_SPA_DIR")
    if spa_dir:
        _mount_spa(app, Path(spa_dir))

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


def _mount_spa(app: FastAPI, spa_dir: Path) -> None:
    """Mount a built SPA bundle at ``/`` with client-side-routing fallback.

    Single-container mode (Phase 1 of ``containerization-single-container``):
    uvicorn serves both the API and the frontend so each product is one
    container on one port. Behaviour:

    - ``/`` and real files under ``spa_dir`` → served by StaticFiles.
    - An unknown *extension-less* path (e.g. ``/dashboard/clients``) → the
      SPA's ``index.html`` so the client-side router can take over.
    - An unknown path that *looks like an asset* (has a filename extension,
      e.g. ``/assets/app-abc123.js``) → real 404. Returning ``index.html``
      for a missing ``.js`` would hand the browser HTML with a JS MIME type
      and produce a confusing parse error instead of a clean 404.
    - An unknown ``/api/...`` or ``/_<ops>`` path → real 404, NEVER
      ``index.html``. Without this carve-out a stale FE bundle calling a
      route the deployed backend doesn't have triggers the SPA fallback
      (200 + HTML), which the shared API client tries to ``response.json()``
      and explodes with ``SyntaxError: Unexpected token '<', "<!doctype "...``.
      Identified 2026-05-20 — an FE shipped a new ``GET /api/profiles/me/roles``
      hook that hit a stale image and broke every Dashboard query.
      (Registered ops routes like ``/_health`` already win via route order;
      the prefix guard also covers the case where ops routes are missing.)

    **Race-safe (the startup-only-resilience fix, 2026-05-19):** always
    mount, never early-return. `runtime-watch`'s `vite --watch` can
    briefly empty `dist/` on its initial pass AFTER `local-watch.sh`'s
    blocking build — racing this startup check. The old startup-only
    decision left `/` permanently unrouted for the container's life even
    when `dist` filled seconds later. Now the mount is registered with
    `check_dir=False`, the StaticFiles per-request FS read does the
    real work, and the extension-less fallback re-checks `index.html`
    at request time. dist appearing/disappearing/rebuilding is
    transparent. Fail-loud at startup (operator sees the warning) but
    never skip the mount.
    """
    index_file = spa_dir / "index.html"
    if not (spa_dir.is_dir() and index_file.is_file()):
        logger.warning(
            "serve_spa=%s but %s currently missing — mounting anyway "
            "(runtime-watch race-safe; will serve when dist appears)",
            spa_dir,
            index_file,
        )

    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.responses import FileResponse, PlainTextResponse
    from starlette.staticfiles import StaticFiles

    def _no_cache(response):
        # The SPA shell (index.html) must NEVER be browser-cached: it references
        # content-hashed asset filenames, so a stale shell points at an OLD
        # bundle → after a deploy a returning visitor's cached shell loads the
        # pre-deploy JS, the new route silently misses, and the auth gate
        # redirects to /landing ("noctusai.com serves a stale page after deploy"
        # — observed on the apex). The hashed assets under /assets/ are immutable
        # (new build ⇒ new filename), so they keep StaticFiles' default caching;
        # only the shell is no-cache.
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    def _no_store(response):
        # STRONGER than `no-cache` — for a service-worker script that must be
        # fetched fresh from origin every time and NEVER stored by any cache.
        # WHY not `no-cache`: a CDN (CloudFlare) treats `no-cache` LOOSELY for
        # static file EXTENSIONS (.js) — it still edge-caches the response and
        # stamps its own Browser-Cache-TTL (observed 2026-07-08: erp `sw.js`
        # came back `cf-cache-status: HIT, max-age=14400` despite the origin
        # sending `no-cache`, while the `.html` shell — not a default-cached
        # extension — kept its `no-cache`). `no-store` is the unambiguous HTTP
        # directive that forbids ANY cache (browser or shared/CDN) from storing
        # the response, which CloudFlare's default behavior honors — so the
        # origin stays the SINGLE SOURCE OF TRUTH for the SW update path,
        # fleet-wide, with NO per-file CDN rule. See
        # `KB § PATTERNS/frontend/spa-cache-and-service-worker.md`.
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    def _is_service_worker(path: str) -> bool:
        # A service-worker script (and its registration/workbox helpers) must
        # be fetched fresh every time — it is the ONLY update path for a PWA,
        # and unlike a hashed asset its FILENAME is stable across builds. Served
        # `no-store` (see `_no_store`) so no browser OR CDN can pin a STALE
        # sw.js and strand a client on an old bundle FOREVER (the
        # erp-imobiliario / Marina incident, 2026-07-08); also lets a
        # `selfDestroying` retirement worker reach stuck clients.
        leaf = path.rsplit("/", 1)[-1]
        return (
            leaf in ("sw.js", "service-worker.js", "registerSW.js")
            or (leaf.startswith("workbox-") and leaf.endswith(".js"))
        )

    class _SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                response = await super().get_response(path, scope)
                # html=True serves index.html for "/" (path == "") and for a
                # direct /index.html — that's the shell; never cache it.
                if path in ("", ".", "index.html") or path.endswith("/index.html"):
                    return _no_cache(response)
                # The service-worker script is the PWA update path — no cache
                # (browser OR CDN) may store it (see `_no_store`).
                if _is_service_worker(path):
                    return _no_store(response)
                return response
            except StarletteHTTPException as exc:
                # Compose both protections:
                # - api/ and _ops paths NEVER get HTML-rescued (prevents
                #   the SyntaxError-parsing-HTML class on a stale FE
                #   bundle hitting an unknown API route).
                # - Per-request index.html re-check — dist may have just
                #   been rewritten by vite --watch; if absent at request
                #   time, 503 (build-in-progress) is honest, not 404.
                is_api_or_ops = path.startswith("api/") or path.startswith("_")
                if exc.status_code == 404 and not PurePosixPath(path).suffix and not is_api_or_ops:
                    if index_file.is_file():
                        # SPA fallback always serves the shell → no-cache too.
                        return _no_cache(FileResponse(index_file))
                    return PlainTextResponse(
                        "SPA bundle not yet built (vite build in progress).",
                        status_code=503,
                    )
                raise

    # check_dir=False — let an absent-at-startup directory still mount;
    # StaticFiles probes per-request and returns 404 cleanly if absent.
    app.mount(
        "/",
        _SPAStaticFiles(directory=str(spa_dir), html=True, check_dir=False),
        name="spa",
    )
    logger.info("SPA mount registered for %s (single-container mode)", spa_dir)


def _is_coroutine(fn) -> bool:
    """Check if a function is a coroutine function."""
    import asyncio
    return asyncio.iscoroutinefunction(fn)
