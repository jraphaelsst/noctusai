"""SSO lifecycle S2 -- the mint writes a registry row; a registry failure never breaks the mint."""
from __future__ import annotations

import logging
import time
import uuid
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest

from app.services import product_sessions

SESSION_ID = str(uuid.uuid4())


def _access_token(session_id: str | None = SESSION_ID) -> str:
    claims = {"sub": "user-uid-123", "exp": int(time.time() + 3600)}
    if session_id:
        claims["session_id"] = session_id
    return pyjwt.encode(claims, "x" * 32, algorithm="HS256")


def _failures(caplog):
    return [r for r in caplog.records if r.getMessage().startswith("sso_registry_write_failed")]


def test_register_writes_one_row_keyed_by_the_session_id_claim(client):
    db = client.mock_supabase
    ok = product_sessions.register_product_session(
        db, access_token=_access_token(), user_id="user-uid-123", product_slug="agents", jti="jti-1",
    )
    assert ok is True
    assert db.table("sso_product_sessions").upserted_payloads == [
        {"session_id": SESSION_ID, "user_id": "user-uid-123", "product_slug": "agents", "jti": "jti-1"}
    ]


def test_write_failure_is_logged_loudly_and_returns_false(caplog):
    db = MagicMock()
    db.table.return_value.upsert.return_value.execute.side_effect = RuntimeError("pg down")
    with caplog.at_level(logging.ERROR):
        ok = product_sessions.register_product_session(
            db, access_token=_access_token(), user_id="u", product_slug="agents",
        )
    assert ok is False
    assert _failures(caplog)


@pytest.mark.parametrize("token,slug", [("not-a-jwt", "agents"), (_access_token(None), "agents"), (_access_token(), None)])
def test_unusable_inputs_log_and_never_raise(caplog, token, slug):
    with caplog.at_level(logging.ERROR):
        ok = product_sessions.register_product_session(MagicMock(), access_token=token, user_id="u", product_slug=slug)
    assert ok is False
    assert _failures(caplog)


def test_generate_session_registers_and_a_registry_failure_does_not_fail_the_mint(client, caplog):
    from app.routers import sso as sso_mod

    mock_sb = client.mock_supabase
    link = MagicMock()
    link.properties.email_otp = "123456"
    mock_sb.auth.admin.generate_link.return_value = link
    verify = MagicMock()
    verify.session.access_token = _access_token()
    verify.session.refresh_token = "r"
    verify.user.id = "user-uid-123"
    mock_sb.auth.verify_otp.return_value = verify

    out = sso_mod._generate_session("a@test.com", "org-1", "agents", jti="jti-9")
    assert out["access_token"] == verify.session.access_token
    rows = mock_sb.table("sso_product_sessions").upserted_payloads
    assert [r["session_id"] for r in rows] == [SESSION_ID] and rows[0]["jti"] == "jti-9"

    # Registry write fails: the mint still returns the session, and the failure is logged.
    original = mock_sb.table

    def broken(name):
        if name == "sso_product_sessions":
            raise RuntimeError("registry down")
        return original(name)

    mock_sb.table = broken
    try:
        with caplog.at_level(logging.ERROR):
            out2 = sso_mod._generate_session("a@test.com", "org-1", "agents", jti="jti-10")
    finally:
        mock_sb.table = original
    assert out2["access_token"] == verify.session.access_token
    assert _failures(caplog)
