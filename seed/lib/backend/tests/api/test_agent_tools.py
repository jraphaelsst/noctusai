"""`make_agent_tools_router`: the product-token gate + error envelope shared by every agent-tools surface."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.agent_tools import AgentTool, ToolResult, make_agent_tools_router
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.primitives.exceptions import AppException

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_SCOPE = "x:tools"


class _Args(StrictHttpModel):
    n: int = 1


def _ctx(**over):
    base = dict(org_id=_ORG, caller_kind="product", user_id=None, scopes=[_SCOPE], raw_token="t", api_token_id=uuid4(), issuer="agents")
    base.update(over)
    return AuthContext(**base)


def _app(ctx_holder, after=None):
    def get_ctx():
        return ctx_holder["ctx"]

    def get_client():
        return "client"

    seen = {}

    def eco(client, org, args):
        seen["org"] = org
        return ToolResult({"n": args["n"], "client": client}, {"extra": True})

    router = make_agent_tools_router(
        "/api/t", _SCOPE, {"eco": AgentTool(_Args, eco)}, get_auth_context=get_ctx, get_client=get_client, after_call=after,
    )
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(AppException)
    async def _h(_req, exc):  # minimal envelope for the test app
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code}})

    return TestClient(app), seen


def test_ok_envelope_meta_and_org_from_token():
    c, seen = _app({"ctx": _ctx()})
    r = c.post("/api/t/eco", json={"n": 3})
    assert r.status_code == 200 and r.json() == {"data": {"n": 3, "client": "client"}, "extra": True}
    assert seen["org"] == _ORG


def test_gate_matrix():
    c, _ = _app({"ctx": _ctx(scopes=["other"])})
    assert c.post("/api/t/eco").status_code == 403
    c, _ = _app({"ctx": _ctx(issuer="x")})
    r = c.post("/api/t/eco")
    assert r.status_code == 403 and "issuer_not_allowed" in r.text
    c, _ = _app({"ctx": _ctx(caller_kind="user", api_token_id=None, user_id=uuid4())})
    assert c.post("/api/t/eco").status_code == 403


def test_unknown_tool_and_bad_body_and_after_call():
    calls = []
    c, _ = _app({"ctx": _ctx()}, after=lambda *a: calls.append(a))
    assert c.post("/api/t/nope").status_code == 404
    assert c.post("/api/t/eco", json={"n": 1, "org_id": "x"}).status_code == 422
    assert not calls
    c.post("/api/t/eco", json={"n": 2})
    assert len(calls) == 1 and calls[0][2] == "eco"
