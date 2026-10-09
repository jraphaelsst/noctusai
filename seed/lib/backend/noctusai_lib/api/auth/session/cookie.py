"""The session cookie's attributes — ONE definition for set and clear.

A browser only drops a cookie when the clearing ``Set-Cookie`` matches the
one that set it, so the login route, logout, and the dependency's
cookie/bearer-mismatch 401 must agree on every attribute. They had three
hand-written copies (logout's already lacked ``secure``/``httponly``/
``samesite``) — this module is the only place they live now.
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import Response

#: Attributes the session cookie is set AND cleared with.
SESSION_COOKIE_ATTRS: dict[str, Any] = {
    "path": "/",
    "secure": True,
    "httponly": True,
    "samesite": "strict",
}


def set_session_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    """Set the session cookie on ``response``."""
    response.set_cookie(key=name, value=value, max_age=max_age, **SESSION_COOKIE_ATTRS)


def clear_session_cookie(response: Response, name: str) -> None:
    """Delete the session cookie on ``response`` (same attributes it was set with)."""
    response.delete_cookie(name, **SESSION_COOKIE_ATTRS)


def session_cookie_clear_header(name: str) -> str:
    """The ``Set-Cookie`` header value that deletes the session cookie — for
    responses built as an ``HTTPException`` (no ``Response`` object to call)."""
    resp = Response()
    clear_session_cookie(resp, name)
    return resp.headers["set-cookie"]
