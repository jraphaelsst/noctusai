"""A bearer token in a path (approval link, webhook routing token) never reaches the audit row (round 3, R4)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api.audit.middleware import AuditMiddleware
from noctusai_lib.api.audit.sink import FakeAuditSink, _to_row
from noctusai_lib.api.audit.types import redact_path_params
from noctusai_lib.api.token_link import token_fingerprint

RAW = "s3cr3t-approval-token-0123456789abcdef"


def _app(sink):
    app = FastAPI()
    app.add_middleware(AuditMiddleware, sink=sink, product_slug="p", enabled=True)

    @app.post("/api/content/approve/{token}")
    async def approve(token: str):
        return {"ok": True}

    @app.post("/api/things/{thing_id}")
    async def thing(thing_id: str):
        return {"ok": True}

    return app


def test_the_approve_route_row_has_no_raw_token():
    sink = FakeAuditSink()
    TestClient(_app(sink)).post(f"/api/content/approve/{RAW}")
    (entry,) = sink.entries
    row = _to_row(entry)
    assert RAW not in repr(entry) and RAW not in repr(row)
    assert row["path_params"] == {"token": token_fingerprint(RAW)}
    assert row["resource_id"] == token_fingerprint(RAW)


def test_ordinary_ids_are_recorded_as_before():
    sink = FakeAuditSink()
    TestClient(_app(sink)).post("/api/things/abc-123")
    assert _to_row(sink.entries[0])["resource_id"] == "abc-123"


def test_redaction_is_by_name_and_idempotent():
    out = redact_path_params({"token": RAW, "webhook_secret": "x", "api_key": "y", "signature": "z", "id": "7"})
    assert out["id"] == "7" and all(v.startswith("tok:") for k, v in out.items() if k != "id")
    assert redact_path_params(out) == out


def test_identifier_names_that_merely_contain_a_secret_word_stay_readable():
    """The match is on whole name segments, not substrings: an id OF a token/key/credential is an identifier, not a secret, and
    the audit trail must still say WHICH resource changed (feature_key, token_id, signup_id, assignments, sigla, keyword...)."""
    ids = {n: "v" for n in ("feature_key", "module_key", "period_key", "item_key", "key", "keyword", "token_id", "old_token_id",
                            "key_id", "credential_id", "signup_id", "sigla", "assignments", "assignee_id", "design_id")}
    assert redact_path_params(ids) == ids


def test_secret_shaped_names_are_redacted():
    names = ("token", "invite_token", "portal_token", "webhook_token", "access_token", "refresh_token", "secret", "app_secret",
             "webhook_secret", "signature", "sig", "hmac", "password", "api_key", "service_role_key", "secret_key", "private_key")
    out = redact_path_params({n: RAW for n in names})
    assert all(v == token_fingerprint(RAW) for v in out.values()), out
