"""PEP 562 lazy ``noctusai_seed`` package — API parity + laziness contract."""
from __future__ import annotations

import importlib
import subprocess
import sys
import textwrap

import pytest

import noctusai_seed

# name -> (module, attr) of the eager reference (what the old __init__ imported).
EAGER_REFERENCE: dict[str, tuple[str, str]] = {
    "create_product_app": ("noctusai_seed.app", "create_product_app"),
    "ProductSettings": ("noctusai_seed.config", "ProductSettings"),
    "make_get_settings": ("noctusai_seed.config", "make_get_settings"),
    "create_database_module": ("noctusai_seed.database", "create_database_module"),
    "create_dependencies": ("noctusai_seed.dependencies", "create_dependencies"),
    "make_dev_auth_get_current_user": ("noctusai_seed.dev_auth", "make_dev_auth_get_current_user"),
    "dev_auth_enabled": ("noctusai_seed.dev_auth", "dev_auth_enabled"),
    "select_get_current_user": ("noctusai_seed.dev_auth", "select_get_current_user"),
    "apply_sqlite_migrations": ("noctusai_seed.apply_sqlite_migrations", "apply_sqlite_migrations"),
    "HealthCheckHook": ("noctusai_seed.health", "HealthCheckHook"),
    "HealthEndpointConfig": ("noctusai_seed.health", "HealthEndpointConfig"),
    "mount_health_endpoints": ("noctusai_seed.health", "mount_health_endpoints"),
    "TeamPolicy": ("noctusai_seed.team_policy", "TeamPolicy"),
    "LLMConfig": ("noctusai_lib.integrations.llm", "LLMConfig"),
    "default_llm_config": ("noctusai_seed.llm_defaults", "default_llm_config"),
    "DEFAULT_LLM_CONFIG": ("noctusai_seed.llm_defaults", "DEFAULT_LLM_CONFIG"),
    "configure_llm": ("noctusai_lib.integrations.llm.client", "configure_llm"),
    "get_llm_config": ("noctusai_lib.integrations.llm.client", "get_llm_config"),
    "shutdown_llm": ("noctusai_lib.integrations.llm.client", "shutdown_llm"),
    "KEEP_DEFAULT_MAX_BODY": ("noctusai_lib.api.middleware", "KEEP_DEFAULT_MAX_BODY"),
    "__seed_version__": ("noctusai_seed._version", "__seed_version__"),
}


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, timeout=120,
    )


def test_reference_covers_exactly___all__():
    assert set(EAGER_REFERENCE) == set(noctusai_seed.__all__)


@pytest.mark.parametrize("name", sorted(EAGER_REFERENCE))
def test_public_name_is_identical_to_eager_object(name):
    module, attr = EAGER_REFERENCE[name]
    assert getattr(noctusai_seed, name) is getattr(importlib.import_module(module), attr)


def test_dir_lists_every_public_name():
    assert set(noctusai_seed.__all__) <= set(dir(noctusai_seed))


def test_star_import_yields_all():
    ns: dict = {}
    exec("from noctusai_seed import *", ns)  # noqa: S102
    ns.pop("__builtins__", None)
    assert set(ns) == set(noctusai_seed.__all__)


def test_unknown_name_raises_standard_attribute_error():
    with pytest.raises(AttributeError, match="module 'noctusai_seed' has no attribute 'nope_x'"):
        noctusai_seed.nope_x  # noqa: B018


def test_attribute_is_cached_in_module_globals():
    value = noctusai_seed.TeamPolicy
    assert vars(noctusai_seed)["TeamPolicy"] is value


def test_submodule_attribute_access_works():
    r = _run("""
        import noctusai_seed
        from noctusai_seed import apply_sqlite_migrations
        assert noctusai_seed.mfa_router.__name__ == "noctusai_seed.mfa_router"
        assert noctusai_seed.app.create_product_app is noctusai_seed.create_product_app
        # function (not module) wins the name it shares with its submodule
        assert callable(apply_sqlite_migrations)
        import noctusai_seed.apply_sqlite_migrations
        assert callable(noctusai_seed.apply_sqlite_migrations)
    """)
    assert r.returncode == 0, r.stderr


def test_bare_import_does_not_load_heavy_submodules():
    r = _run("""
        import sys
        import noctusai_seed
        loaded = {m for m in sys.modules if m.startswith("noctusai_seed.")}
        forbidden = {"noctusai_seed.mfa_router", "noctusai_seed.app",
                     "noctusai_seed.routers", "noctusai_seed.health",
                     "noctusai_seed.dependencies", "noctusai_seed.database"}
        bad = loaded & forbidden
        assert not bad, bad
        # touching one name loads only what it needs
        noctusai_seed.TeamPolicy
        assert "noctusai_seed.team_policy" in sys.modules
        assert "noctusai_seed.mfa_router" not in sys.modules
    """)
    assert r.returncode == 0, r.stderr
