"""Cookie logout must not revoke the GoTrue session the SPA is still using."""
import base64
import json

from noctusai_lib.api.auth.session.session_revoke import jwt_session_id


def _jwt(sid):
    body = base64.urlsafe_b64encode(json.dumps({"session_id": sid}).encode()).decode().rstrip("=")
    return f"h.{body}.s"


def test_jwt_session_id_reads_claim():
    assert jwt_session_id(_jwt("abc")) == "abc"


def test_jwt_session_id_unreadable_is_none():
    assert jwt_session_id("garbage") is None
    assert jwt_session_id(None) is None
