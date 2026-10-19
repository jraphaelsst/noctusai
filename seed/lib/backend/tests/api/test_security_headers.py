from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from noctusai_lib.api.security_headers import SecurityHeadersMiddleware


def _client():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/j")
    def j():
        return {"a": 1}

    @app.get("/h")
    def h():
        return HTMLResponse("<html></html>")

    return TestClient(app)


def test_headers_on_json_https():
    r = _client().get("/j", headers={"x-forwarded-proto": "https"})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "max-age=31536000" in r.headers["strict-transport-security"]
    assert "includeSubDomains" in r.headers["strict-transport-security"]
    assert "permissions-policy" in r.headers
    assert "content-security-policy-report-only" not in r.headers


def test_no_hsts_on_plain_http_and_csp_ro_on_html():
    r = _client().get("/h")
    assert "strict-transport-security" not in r.headers
    assert "content-security-policy-report-only" in r.headers
    assert "content-security-policy" not in r.headers
