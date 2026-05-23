"""Unit tests for `noctusai_lib.config.deploy_config`.

Exercises the deploy-context-aware required-config primitive:

- :func:`is_deploy_context` across dev / explicit-``APP_ENV`` / ``PRODUCT_URL_*``.
- :func:`resolve_config` — dev fallback, env-value win, required-in-prod raise.
- :func:`require_prod_config` — dev no-op + aggregated prod failure.

Env isolation: every test runs through the ``clean_env`` fixture, which scrubs
the deploy signals (``APP_ENV`` + any ``PRODUCT_URL_*``) so the host's real
environment can't leak a deploy context into a "dev" assertion. Tests set the
signals they need via the **real** env API (``monkeypatch.setenv`` /
``monkeypatch.delenv``) — never by patching our own module (no monkey-patching
our code, per platform rule).
"""

from __future__ import annotations

import os

import pytest

from noctusai_lib.config.deploy_config import (
    MissingProdConfigError,
    is_deploy_context,
    require_prod_config,
    resolve_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scrub all deploy signals so each test starts from a dev-shaped env.

    Removes ``APP_ENV`` and every ``PRODUCT_URL_*`` key the host might carry
    (the local MCP runtime can export them). ``raising=False`` keeps it a no-op
    when a key is already absent. ``monkeypatch`` restores the original env
    after each test.
    """
    monkeypatch.delenv("APP_ENV", raising=False)
    for key in [k for k in os.environ if k.startswith("PRODUCT_URL_")]:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# is_deploy_context
# ---------------------------------------------------------------------------


def test_is_deploy_context_false_in_clean_env() -> None:
    assert is_deploy_context() is False


def test_is_deploy_context_true_via_app_env_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    assert is_deploy_context() is True


def test_is_deploy_context_true_via_app_env_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    assert is_deploy_context() is True


def test_is_deploy_context_true_via_product_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_URL_FOO", "https://foo.example.com")
    assert is_deploy_context() is True


def test_is_deploy_context_ignores_product_url_pattern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PRODUCT_URL_PATTERN is a fleet knob, not a per-product override → not a
    # deploy signal on its own.
    monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.example.com")
    assert is_deploy_context() is False


def test_is_deploy_context_ignores_empty_product_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_URL_FOO", "")
    assert is_deploy_context() is False


# ---------------------------------------------------------------------------
# resolve_config
# ---------------------------------------------------------------------------


def test_resolve_config_returns_canonical_default_in_dev_when_unset() -> None:
    assert resolve_config("SOME_KEY", canonical_default="canonical") == "canonical"


def test_resolve_config_default_is_none_when_unset_and_no_default() -> None:
    assert resolve_config("SOME_KEY") is None


def test_resolve_config_returns_env_value_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOME_KEY", "from-env")
    assert resolve_config("SOME_KEY", canonical_default="canonical") == "from-env"


def test_resolve_config_empty_env_value_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An empty env value is treated as unset (mirrors product_urls).
    monkeypatch.setenv("SOME_KEY", "")
    assert resolve_config("SOME_KEY", canonical_default="canonical") == "canonical"


def test_resolve_config_required_in_prod_unset_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(MissingProdConfigError) as excinfo:
        resolve_config("DATABASE_URL", required_in_prod=True)
    assert "DATABASE_URL" in str(excinfo.value)
    assert excinfo.value.missing_keys == ["DATABASE_URL"]


def test_resolve_config_required_in_prod_set_returns_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgres://prod")
    assert (
        resolve_config("DATABASE_URL", required_in_prod=True) == "postgres://prod"
    )


def test_resolve_config_required_in_prod_is_noop_in_dev() -> None:
    # required_in_prod has no effect outside a deploy context: dev gets the
    # canonical default, never an exception.
    assert (
        resolve_config(
            "DATABASE_URL", canonical_default="postgres://localhost",
            required_in_prod=True,
        )
        == "postgres://localhost"
    )


# ---------------------------------------------------------------------------
# require_prod_config
# ---------------------------------------------------------------------------


def test_require_prod_config_noop_in_dev() -> None:
    # Clean env (dev) → no raise even though the key is absent.
    assert require_prod_config(["X"]) is None


def test_require_prod_config_aggregates_all_missing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    # Two of three keys are missing; the third is set and must NOT appear.
    monkeypatch.setenv("PRESENT_KEY", "value")
    with pytest.raises(MissingProdConfigError) as excinfo:
        require_prod_config(["MISSING_A", "PRESENT_KEY", "MISSING_B"])

    message = str(excinfo.value)
    assert "MISSING_A" in message
    assert "MISSING_B" in message
    assert "PRESENT_KEY" not in message
    assert excinfo.value.missing_keys == ["MISSING_A", "MISSING_B"]


def test_require_prod_config_passes_when_all_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("KEY_A", "a")
    monkeypatch.setenv("KEY_B", "b")
    assert require_prod_config(["KEY_A", "KEY_B"]) is None


def test_require_prod_config_deploy_signal_via_product_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The PRODUCT_URL_* deploy signal (not just APP_ENV) drives the check.
    monkeypatch.setenv("PRODUCT_URL_CORE", "https://core.example.com")
    with pytest.raises(MissingProdConfigError) as excinfo:
        require_prod_config(["NEEDED"])
    assert excinfo.value.missing_keys == ["NEEDED"]
