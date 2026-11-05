import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.security.webhook_signatures import (
    handle_unsigned_webhook,
    static_secret_resolver,
    webhook_endpoint,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("WEBHOOK_REQUIRE_SIGNATURE", "DEBUG", "APP_ENV"):
        monkeypatch.delenv(k, raising=False)
    import os

    for k in [k for k in os.environ if k.startswith("PRODUCT_URL_")]:
        monkeypatch.delenv(k, raising=False)


def _client(**kw):
    app = FastAPI()

    @app.post("/wh")
    async def wh(v=webhook_endpoint(
        secret_resolver=static_secret_resolver(None),
        scheme="sha256_prefixed",
        bypass_when_unset=True,
        **kw,
    )):
        return {"ok": True}

    return TestClient(app)


def test_dev_context_logs_only_and_accepts(caplog):
    handle_unsigned_webhook("t")
    assert any(r.levelname == "CRITICAL" for r in caplog.records)
    assert _client().post("/wh", content=b"{}").status_code == 200


def test_deploy_context_refuses_by_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(HTTPException) as e:
        handle_unsigned_webhook("t")
    assert e.value.status_code == 401
    assert _client().post("/wh", content=b"{}").status_code == 401


def test_product_url_marker_is_a_deploy_context(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SEED", "https://seed.example.com")
    assert _client().post("/wh", content=b"{}").status_code == 401


def test_declared_per_mount_opt_out_accepts_in_deploy_context(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert _client(allow_unsigned_in_prod=True).post("/wh", content=b"{}").status_code == 200


def test_force_flag_refuses_even_with_opt_out(monkeypatch):
    monkeypatch.setenv("WEBHOOK_REQUIRE_SIGNATURE", "1")
    with pytest.raises(HTTPException) as e:
        handle_unsigned_webhook("t", allow_unsigned_in_prod=True)
    assert e.value.status_code == 401


def test_debug_never_refuses(monkeypatch):
    monkeypatch.setenv("WEBHOOK_REQUIRE_SIGNATURE", "1")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    handle_unsigned_webhook("t")
