"""
NoctusAI Seed Framework — structural bones for all products.

The seed is the spine of every product. All products inherit their
structural infrastructure from here. Change the seed, change all products.

Two layers:
  - seed/lib/ (noctusai_lib)        = reusable code library (auth, roles, llm, utils)
  - seed/framework/ (noctusai_seed) = structural framework (app factory, database, deps)

Products import from both. Domain-specific code lives in the product only.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

# PEP 562 lazy package: ``import noctusai_seed`` no longer imports every
# submodule. Each public name resolves on first access to the IDENTICAL object
# the eager import produced, and is cached in module globals. This keeps the
# import graph (and gate_sweep's reverse-closure fan-out) reflecting real use.
# Audited: no noctusai_seed module has import-time registration side effects
# (routes/models/hooks/logging/env/monkeypatching) -- see the commit message.
# EAGER on purpose: the function ``apply_sqlite_migrations`` shares its name with
# its submodule. A lazy resolution would let a first ``import
# noctusai_seed.apply_sqlite_migrations`` bind the MODULE over the function name
# (the import system setattr's the submodule on the parent after load). Eager
# import-then-rebind (as before) pins the function. The module is stdlib-only.
from noctusai_seed.apply_sqlite_migrations import apply_sqlite_migrations  # noqa: E402

if TYPE_CHECKING:
    from noctusai_lib.api.middleware import KEEP_DEFAULT_MAX_BODY
    from noctusai_lib.integrations.llm import LLMConfig
    from noctusai_lib.integrations.llm.client import configure_llm
    from noctusai_lib.integrations.llm.client import get_llm_config
    from noctusai_lib.integrations.llm.client import shutdown_llm
    from noctusai_seed._version import __seed_version__
    from noctusai_seed.app import create_product_app
    from noctusai_seed.config import ProductSettings
    from noctusai_seed.config import make_get_settings
    from noctusai_seed.database import create_database_module
    from noctusai_seed.dependencies import create_dependencies
    from noctusai_seed.dev_auth import dev_auth_enabled
    from noctusai_seed.dev_auth import make_dev_auth_get_current_user
    from noctusai_seed.dev_auth import select_get_current_user
    from noctusai_seed.health import HealthCheckHook
    from noctusai_seed.health import HealthEndpointConfig
    from noctusai_seed.health import mount_health_endpoints
    from noctusai_seed.llm_defaults import DEFAULT_LLM_CONFIG
    from noctusai_seed.llm_defaults import default_llm_config
    from noctusai_seed.team_policy import TeamPolicy

_LAZY_ATTRS: dict[str, str] = {
    "KEEP_DEFAULT_MAX_BODY": "noctusai_lib.api.middleware",
    "LLMConfig": "noctusai_lib.integrations.llm",
    "configure_llm": "noctusai_lib.integrations.llm.client",
    "get_llm_config": "noctusai_lib.integrations.llm.client",
    "shutdown_llm": "noctusai_lib.integrations.llm.client",
    "__seed_version__": "noctusai_seed._version",
    "create_product_app": "noctusai_seed.app",
    "ProductSettings": "noctusai_seed.config",
    "make_get_settings": "noctusai_seed.config",
    "create_database_module": "noctusai_seed.database",
    "create_dependencies": "noctusai_seed.dependencies",
    "dev_auth_enabled": "noctusai_seed.dev_auth",
    "make_dev_auth_get_current_user": "noctusai_seed.dev_auth",
    "select_get_current_user": "noctusai_seed.dev_auth",
    "HealthCheckHook": "noctusai_seed.health",
    "HealthEndpointConfig": "noctusai_seed.health",
    "mount_health_endpoints": "noctusai_seed.health",
    "DEFAULT_LLM_CONFIG": "noctusai_seed.llm_defaults",
    "default_llm_config": "noctusai_seed.llm_defaults",
    "TeamPolicy": "noctusai_seed.team_policy",
}

# Submodules reachable as attributes (``noctusai_seed.app`` ...). Resolved
# via importlib on first access; ``_version`` etc. are real submodules too.
_SUBMODULES = frozenset(
    {
        "ai_feedback_router", "ai_router", "api_keys_router", "app",
        "auth_router", "config", "database",
        "dependencies", "dev_auth", "health", "llm_defaults", "llm_router",
        "me_router", "mfa_router", "rate_limit", "routers", "scheduler_router",
        "status_pagina_router", "team_policy", "upload_route_overrides",
        "whatsapp_connections_router", "_version", "_version_static",
    }
)


def __getattr__(name: str) -> Any:
    module_path = _LAZY_ATTRS.get(name)
    if module_path is not None:
        value = getattr(importlib.import_module(module_path), name)
        globals()[name] = value
        return value
    if name in _SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__) | _SUBMODULES)


__all__ = [
    # Framework bones
    "create_product_app",
    "ProductSettings",
    "make_get_settings",
    "create_database_module",
    "create_dependencies",
    # Dev-only pre-seeded auth + SQLite backend (double-gated; hard-off
    # in production). `select_get_current_user` is the seam the
    # canonical product `dependencies.py` calls to pick dev vs prod.
    "make_dev_auth_get_current_user",
    "dev_auth_enabled",
    "select_get_current_user",
    "apply_sqlite_migrations",
    # Ops endpoints (`/_health` + `/_ready` baked into create_product_app)
    "HealthCheckHook",
    "HealthEndpointConfig",
    "mount_health_endpoints",
    # Named seam for the "team" standard router (create_product_app(team=...))
    "TeamPolicy",
    # LLM inheritance (re-exported so products can do one-stop imports)
    "LLMConfig",
    "default_llm_config",
    "DEFAULT_LLM_CONFIG",
    "configure_llm",
    "get_llm_config",
    "shutdown_llm",
    # Explicit opt-out sentinel for `max_body_path_overrides` — a route
    # that deliberately stays at the app-wide default. See
    # `noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY`.
    "KEEP_DEFAULT_MAX_BODY",
    # Runtime propagation breadcrumb (see `seed-inheritance-hardening` Phase 3)
    "__seed_version__",
]
