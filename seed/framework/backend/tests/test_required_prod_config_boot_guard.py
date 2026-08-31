"""Regression tests: `create_product_app(required_prod_config=[...])`.

WHAT THIS PINS. `app/services/credential_vault.py` (social-wiring) and its
p-studio sibling REFUSE to write a credential without `ENCRYPTION_KEY`
(`EncryptionNotConfigured` -> 503) rather than storing an OAuth token in
plaintext. Without the key, every integration that touches the vault is
silently inoperative — and the symptom appears one integration at a time, at
each first OAuth, never at deploy. `required_prod_config=[...]` turns that
into a loud boot-time abort (`MissingProdConfigError`) in a deploy context,
aggregated (every missing key at once), and a no-op everywhere else.

Same fixture shape as `test_lifespan_hooks.py` (`minimal_settings` + a thin
`_app()` helper) — no DB / vendor wiring needed, because the guard fires in
step "1a" of `create_product_app`, before any of that wiring happens.

Env isolation mirrors `seed/lib/backend/tests/config/test_deploy_config.py`:
`clean_env` scrubs `APP_ENV` + any `PRODUCT_URL_*` so the host environment
can never leak a deploy context into a "dev" assertion.
"""
from __future__ import annotations

import os

import pytest

from noctusai_lib.config.deploy_config import MissingProdConfigError


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    for key in [k for k in os.environ if k.startswith("PRODUCT_URL_")]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def minimal_settings():
    """Same shape `test_lifespan_hooks.py` / `test_health.py` use."""

    class _S:
        cors_origins = "http://localhost:3000"
        cors_origins_list = ["http://localhost:3000"]
        debug = True
        is_production = False
        sentry_dsn = None
        product_slug = "test"
        supabase_url = "http://localhost:54321"
        supabase_anon_key = "anon"
        supabase_service_role_key = "service"
        consent_gating = False
        llm_usage_tracking = False
        redis_url = None

    return _S()


def _app(minimal_settings, **kwargs):
    from noctusai_seed import create_product_app

    return create_product_app(
        name="Test",
        schema="test",
        settings=minimal_settings,
        routers=None,
        version="9.9.9",
        standard_routers=["health"],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# The boot guard itself
# ---------------------------------------------------------------------------


def test_missing_declared_keys_abort_boot_in_deploy_context(
    minimal_settings, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(MissingProdConfigError) as excinfo:
        _app(minimal_settings, required_prod_config=["ENCRYPTION_KEY"])
    assert excinfo.value.missing_keys == ["ENCRYPTION_KEY"]


def test_missing_declared_keys_names_every_missing_key_not_just_the_first(
    minimal_settings, monkeypatch: pytest.MonkeyPatch
):
    """Aggregated, not first-fail — a misconfigured deploy surfaces every gap
    at once. Also proves a PRESENT key does not get flagged alongside the
    absent ones."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("P_STUDIO_ORG_ID", "00000000-0000-0000-0000-000000000000")
    with pytest.raises(MissingProdConfigError) as excinfo:
        _app(
            minimal_settings,
            required_prod_config=["ENCRYPTION_KEY", "P_STUDIO_ORG_ID", "SOME_OTHER_KEY"],
        )
    assert excinfo.value.missing_keys == ["ENCRYPTION_KEY", "SOME_OTHER_KEY"]


def test_present_declared_keys_do_not_abort_boot(
    minimal_settings, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENCRYPTION_KEY", "a-real-fernet-key")
    app = _app(minimal_settings, required_prod_config=["ENCRYPTION_KEY"])
    assert app is not None


def test_declared_keys_are_a_noop_outside_a_deploy_context(minimal_settings):
    # Clean env (no APP_ENV, no PRODUCT_URL_*) => dev. Missing keys must NOT
    # abort — dev legitimately leaves them unset.
    app = _app(minimal_settings, required_prod_config=["ENCRYPTION_KEY", "P_STUDIO_ORG_ID"])
    assert app is not None


# ---------------------------------------------------------------------------
# Back-compat — a product declaring nothing behaves exactly as before
# ---------------------------------------------------------------------------


def test_omitting_the_kwarg_never_aborts_boot_even_in_deploy_context(
    minimal_settings, monkeypatch: pytest.MonkeyPatch
):
    """12 other products don't declare `required_prod_config` at all. The
    kwarg MUST default safely: omitting it must not change boot behavior for
    a product that never opted in, even in a deploy context with a real
    Redis unset (so the baseline fold-in also stays inert)."""
    monkeypatch.setenv("APP_ENV", "production")
    app = _app(minimal_settings)  # no required_prod_config kwarg at all
    assert app is not None


def test_explicit_none_behaves_identically_to_omitting_the_kwarg(
    minimal_settings, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APP_ENV", "production")
    app = _app(minimal_settings, required_prod_config=None)
    assert app is not None


def test_empty_list_behaves_identically_to_omitting_the_kwarg(
    minimal_settings, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("APP_ENV", "production")
    app = _app(minimal_settings, required_prod_config=[])
    assert app is not None
