"""The session cookie is set and cleared with the SAME attributes — a browser
only drops a cookie when the clearing Set-Cookie matches the one that set it
(logout once cleared it without secure/httponly/samesite)."""
from fastapi.responses import Response

from noctusai_lib.api.auth.session.cookie import (
    clear_session_cookie,
    session_cookie_clear_header,
    set_session_cookie,
)


def _attrs(header: str) -> set[str]:
    return {p.strip().lower() for p in header.split(";")[1:] if not p.strip().lower().startswith(("max-age", "expires"))}


def test_set_and_clear_share_attributes():
    set_resp, clear_resp = Response(), Response()
    set_session_cookie(set_resp, "nai_session", "sid", 60)
    clear_session_cookie(clear_resp, "nai_session")

    assert _attrs(set_resp.headers["set-cookie"]) == _attrs(clear_resp.headers["set-cookie"])
    assert {"httponly", "secure", "path=/", "samesite=strict"} <= _attrs(clear_resp.headers["set-cookie"])


def test_clear_header_deletes_the_named_cookie():
    header = session_cookie_clear_header("nai_session")

    assert header.startswith('nai_session=""') and "max-age=0" in header.lower()
