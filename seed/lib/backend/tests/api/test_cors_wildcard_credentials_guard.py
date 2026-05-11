"""Unit tests for the CORS wildcard+credentials guard in
`noctusai_lib.api.app_factory.configure_app`.

Asserts:
  - Wildcard `cors_origins=['*']` + `allow_credentials=True` → RuntimeError
    at boot (the auth-replay vulnerability is refused by construction).
  - Enumerated origins + `allow_credentials=True` → boots fine.
  - Wildcard + `allow_credentials=False` → boots fine (legitimate
    public-read API shape with no credentialed requests).
  - `NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS=1` env override → boots
    with LOUD warning (escape hatch for local dev).
  - Product name surfaced in the RuntimeError message for debuggability.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI


def _make_settings(
    cors_origins_list: list[str],
    *,
    product_name: str | None = None,
) -> SimpleNamespace:
    """Build a minimal settings stub. Mirrors the shape `configure_app`
    actually reads (cors_origins_list / sentry_dsn / is_production / debug).
    """
    kwargs = dict(
        cors_origins_list=cors_origins_list,
        sentry_dsn="",
        is_production=False,
        debug=True,
    )
    if product_name is not None:
        kwargs["product_name"] = product_name
    return SimpleNamespace(**kwargs)


def test_wildcard_with_credentials_raises_at_boot():
    """The canonical vulnerability — refused at boot, not at request time."""
    from noctusai_lib.api.app_factory import configure_app

    app = FastAPI()
    settings = _make_settings(["*"])

    with pytest.raises(RuntimeError) as excinfo:
        configure_app(app, settings, allow_credentials=True)

    msg = str(excinfo.value)
    assert "CORS misconfiguration" in msg
    assert "auth-replay" in msg
    assert "Enumerate cors_origins" in msg


def test_enumerated_origins_with_credentials_boots_fine():
    """The legitimate production shape — enumerate origins, credentials on."""
    from noctusai_lib.api.app_factory import configure_app

    app = FastAPI()
    settings = _make_settings([
        "https://app.example.com",
        "https://admin.example.com",
    ])

    # Must not raise.
    configure_app(app, settings, allow_credentials=True)


def test_wildcard_without_credentials_boots_fine():
    """Legitimate public-read shape: `*` + credentials=False is browser-safe."""
    from noctusai_lib.api.app_factory import configure_app

    app = FastAPI()
    settings = _make_settings(["*"])

    # Must not raise — wildcard alone is fine without credentials.
    configure_app(app, settings, allow_credentials=False)


def test_default_localhost_with_credentials_boots_fine():
    """Seed-default localhost CSV does NOT contain '*' — must boot cleanly."""
    from noctusai_lib.api.app_factory import configure_app

    app = FastAPI()
    settings = _make_settings([
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
    ])

    # Default behavior: allow_credentials=True implicit. Must not raise.
    configure_app(app, settings)


def test_env_override_allows_wildcard_with_credentials(monkeypatch, caplog):
    """Escape hatch for genuine local-dev scenarios. LOUD warning required."""
    import logging

    from noctusai_lib.api.app_factory import configure_app

    monkeypatch.setenv("NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS", "1")

    app = FastAPI()
    settings = _make_settings(["*"], product_name="test-product")

    with caplog.at_level(logging.WARNING, logger="noctusai_lib.api.app_factory"):
        configure_app(app, settings, allow_credentials=True)

    # Verify the LOUD warning was emitted.
    warning_records = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "CORS wildcard+credentials override ACTIVE" in r.getMessage()
    ]
    assert warning_records, (
        "expected LOUD WARN log when override env var is set; "
        f"got records: {[r.getMessage() for r in caplog.records]}"
    )
    # Product name surfaced for traceability.
    assert "test-product" in warning_records[0].getMessage()


def test_env_override_false_value_still_blocks(monkeypatch):
    """Override must require an opt-in truthy value — '0' / 'false' / '' must
    NOT activate the escape hatch.
    """
    from noctusai_lib.api.app_factory import configure_app

    for falsy in ("0", "false", "no", "", "  "):
        monkeypatch.setenv("NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS", falsy)
        app = FastAPI()
        settings = _make_settings(["*"])

        with pytest.raises(RuntimeError):
            configure_app(app, settings, allow_credentials=True)


def test_env_override_accepts_truthy_variants(monkeypatch):
    """'1' / 'true' / 'yes' (any case) activate the override."""
    from noctusai_lib.api.app_factory import configure_app

    for truthy in ("1", "true", "True", "TRUE", "yes", "Yes"):
        monkeypatch.setenv("NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS", truthy)
        app = FastAPI()
        settings = _make_settings(["*"])

        # Must not raise.
        configure_app(app, settings, allow_credentials=True)


def test_product_name_surfaced_in_error(monkeypatch):
    """The explicit `product_name=` arg wins over settings.product_name."""
    from noctusai_lib.api.app_factory import configure_app

    # Make sure the override is NOT set (test isolation).
    monkeypatch.delenv("NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS", raising=False)

    app = FastAPI()
    settings = _make_settings(["*"], product_name="from-settings")

    with pytest.raises(RuntimeError) as excinfo:
        configure_app(
            app,
            settings,
            allow_credentials=True,
            product_name="explicit-override",
        )
    assert "explicit-override" in str(excinfo.value)
    assert "from-settings" not in str(excinfo.value)


def test_product_name_falls_back_to_settings(monkeypatch):
    """When the explicit kwarg is None, settings.product_name is used."""
    from noctusai_lib.api.app_factory import configure_app

    monkeypatch.delenv("NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS", raising=False)

    app = FastAPI()
    settings = _make_settings(["*"], product_name="from-settings")

    with pytest.raises(RuntimeError) as excinfo:
        configure_app(app, settings, allow_credentials=True)
    assert "from-settings" in str(excinfo.value)


def test_product_name_unknown_when_no_signal(monkeypatch):
    """No explicit arg, no settings field → '<unknown>' label."""
    from noctusai_lib.api.app_factory import configure_app

    monkeypatch.delenv("NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS", raising=False)

    app = FastAPI()
    settings = _make_settings(["*"])  # no product_name

    with pytest.raises(RuntimeError) as excinfo:
        configure_app(app, settings, allow_credentials=True)
    assert "<unknown>" in str(excinfo.value)
