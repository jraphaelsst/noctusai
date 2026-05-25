"""
NoctusAI Seed Framework — structural bones for all products.

The seed is the spine of every product. All products inherit their
structural infrastructure from here. Change the seed, change all products.

Two layers:
  - seed/lib/ (noctusai_lib)        = reusable code library (auth, roles, llm, utils)
  - seed/framework/ (noctusai_seed) = structural framework (app factory, database, deps)

Products import from both. Domain-specific code lives in the product only.
"""
from noctusai_lib.integrations.llm import LLMConfig
from noctusai_lib.integrations.llm.client import configure_llm, get_llm_config, shutdown_llm

from noctusai_seed._version import __seed_version__
from noctusai_seed.app import create_product_app
from noctusai_seed.config import ProductSettings, make_get_settings
from noctusai_seed.database import create_database_module
from noctusai_seed.dependencies import create_dependencies
from noctusai_seed.apply_sqlite_migrations import apply_sqlite_migrations
from noctusai_seed.dev_auth import (
    dev_auth_enabled,
    make_dev_auth_get_current_user,
    select_get_current_user,
)
from noctusai_seed.health import (
    HealthCheckHook,
    HealthEndpointConfig,
    mount_health_endpoints,
)
from noctusai_seed.llm_defaults import DEFAULT_LLM_CONFIG, default_llm_config

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
    # LLM inheritance (re-exported so products can do one-stop imports)
    "LLMConfig",
    "default_llm_config",
    "DEFAULT_LLM_CONFIG",
    "configure_llm",
    "get_llm_config",
    "shutdown_llm",
    # Runtime propagation breadcrumb (see `seed-inheritance-hardening` Phase 3)
    "__seed_version__",
]
