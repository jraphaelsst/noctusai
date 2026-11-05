import pytest
from fastapi import HTTPException

from noctusai_lib.security.webhook_signatures import handle_unsigned_webhook


def test_default_logs_only(monkeypatch, caplog):
    monkeypatch.delenv("WEBHOOK_REQUIRE_SIGNATURE", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    handle_unsigned_webhook("t")
    assert any(r.levelname == "CRITICAL" for r in caplog.records)


def test_flag_refuses_in_prod(monkeypatch):
    monkeypatch.setenv("WEBHOOK_REQUIRE_SIGNATURE", "1")
    monkeypatch.delenv("DEBUG", raising=False)
    with pytest.raises(HTTPException) as e:
        handle_unsigned_webhook("t")
    assert e.value.status_code == 401


def test_flag_does_not_refuse_under_debug(monkeypatch):
    monkeypatch.setenv("WEBHOOK_REQUIRE_SIGNATURE", "1")
    monkeypatch.setenv("DEBUG", "true")
    handle_unsigned_webhook("t")
