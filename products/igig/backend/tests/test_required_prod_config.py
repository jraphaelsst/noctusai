"""Regression: `IGIG_COFRE_KEY` is declared in `app/main.py`'s
`required_prod_config=[...]`, and the boot guard it feeds actually refuses
to come up in a deploy context without it.

See `products/igig/backend/app/main.py` for the reasoning: the key was
verified LIVE in production (real Fernet roundtrip inside the running
container) before being declared here — an undeclared-but-missing key
silently 409s every Cofre / Integrações save (that was the bug, weeks
silent); a declared-but-missing key aborts boot loudly instead.

Two legs:
  1. STATIC — the literal list in `app/main.py` actually names the key.
     Parsed via `ast`, mirroring how `noctus.dev.predeploy_check`'s
     `load_product_required_prod_config` reads every product's declaration
     (never by importing `app.main`, which would execute the full
     `create_product_app` wiring just to answer a question about a literal
     list — AST-first, `KB § PATTERNS/common/ast.md`). Not importing that
     MCP helper directly from a product test on purpose: this suite runs
     under a PYTHONPATH scoped to `products/igig/backend` (see
     `noctus.dev.pytest`'s docstring), not the platform's `mcp/` tree.
  2. FUNCTIONAL — the underlying guard, exercised with that exact literal
     key, actually raises `MissingProdConfigError` in a deploy context when
     unset, and is a no-op everywhere else. Same fixture shape as
     `seed/framework/backend/tests/test_required_prod_config_boot_guard.py`
     (which proves the MECHANISM); this proves IGIG'S OWN wiring of it,
     without paying to boot the real app (Supabase/DB/LLM wiring) twice.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from noctusai_lib.config.deploy_config import MissingProdConfigError

_MAIN_PY = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _required_prod_config_literal(main_py: Path) -> list[str]:
    """The literal `required_prod_config=[...]` passed to `create_product_app`
    in `main_py`, read via `ast` — never by importing the module."""
    tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "create_product_app":
            continue
        for kw in node.keywords:
            if kw.arg != "required_prod_config":
                continue
            assert isinstance(kw.value, (ast.List, ast.Tuple)), (
                "required_prod_config must be a literal list — this test "
                "(and noctus.dev.predeploy_check) read it statically."
            )
            return [
                elt.value
                for elt in kw.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    return []


class TestDeclaration:
    def test_igig_declares_igig_cofre_key(self):
        assert "IGIG_COFRE_KEY" in _required_prod_config_literal(_MAIN_PY)


# ---------------------------------------------------------------------------
# Functional leg — same fixture shape as the seed's boot-guard suite.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("IGIG_COFRE_KEY", raising=False)
    for key in [k for k in os.environ if k.startswith("PRODUCT_URL_")]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def minimal_settings():
    class _S:
        cors_origins = "http://localhost:3000"
        cors_origins_list = ["http://localhost:3000"]
        debug = True
        is_production = False
        sentry_dsn = None
        product_slug = "igig"
        supabase_url = "http://localhost:54321"
        supabase_anon_key = "anon"
        supabase_service_role_key = "service"
        consent_gating = False
        llm_usage_tracking = False
        redis_url = None

    return _S()


def _app(minimal_settings, required_prod_config):
    from noctusai_seed import create_product_app

    return create_product_app(
        name="Test",
        schema="test",
        settings=minimal_settings,
        routers=None,
        version="9.9.9",
        standard_routers=["health"],
        required_prod_config=required_prod_config,
    )


class TestBootGuard:
    def test_boot_refuses_in_a_prod_context_without_the_key(
        self, minimal_settings, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("APP_ENV", "production")
        keys = _required_prod_config_literal(_MAIN_PY)
        with pytest.raises(MissingProdConfigError) as excinfo:
            _app(minimal_settings, keys)
        assert "IGIG_COFRE_KEY" in excinfo.value.missing_keys

    def test_boot_succeeds_in_a_prod_context_with_the_key_present(
        self, minimal_settings, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("IGIG_COFRE_KEY", "a-real-fernet-key")
        keys = _required_prod_config_literal(_MAIN_PY)
        app = _app(minimal_settings, keys)
        assert app is not None

    def test_declared_key_is_a_noop_outside_a_deploy_context(
        self, minimal_settings
    ):
        # Clean env (no APP_ENV) => dev. Missing IGIG_COFRE_KEY must NOT
        # abort — dev legitimately leaves it unset.
        keys = _required_prod_config_literal(_MAIN_PY)
        app = _app(minimal_settings, keys)
        assert app is not None
