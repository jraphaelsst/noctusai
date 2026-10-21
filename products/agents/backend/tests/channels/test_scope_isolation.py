"""The channel scopes open ONLY the channel routes, and nothing else opens them.

Derived from the live route table (never a hand list), like the package-scope
matrix: a new route can never silently become reachable with a channel token,
and a new channel route can never silently accept another kind of token."""
from __future__ import annotations

import pytest

from app.dependencies import CHANNEL_TOKEN_SCOPES, PACKAGE_TOKEN_SCOPES
from tests.channels.conftest import BOTH
from tests.studio.pkg.test_scope_matrix import BUSINESS_PREFIXES, _fill

CHANNEL_PREFIX = "/api/channels"


def _routes(prefixes):
    from app.main import app

    seen = set()
    for r in app.routes:
        path = getattr(r, "path", "")
        if path.startswith(prefixes):
            for method in sorted(getattr(r, "methods", None) or ()):
                if method not in ("HEAD", "OPTIONS"):
                    seen.add((method, path))
    return sorted(seen)


def _code(resp) -> str | None:
    body = resp.json()
    return body.get("code") or (body.get("detail") or {}).get("code") if isinstance(body, dict) else None


def test_the_channel_route_set_is_exactly_the_documented_ones(chan):
    assert _routes((CHANNEL_PREFIX,)) == [
        ("DELETE", "/api/channels/conversations"),
        ("DELETE", "/api/channels/ferramentas-token"),
        ("DELETE", "/api/channels/leads/{ref}"),
        ("GET", "/api/channels/agents/{agent_key}/controle"),
        ("GET", "/api/channels/agents/{agent_key}/qualificacao/estagios"),
        ("GET", "/api/channels/agents/{agent_key}/status"),
        ("GET", "/api/channels/handoffs/{handoff_id}"),
        ("GET", "/api/channels/leads/{lead_ref}/identificacao"),
        ("GET", "/api/channels/leads/{lead_ref}/qualificacao"),
        ("GET", "/api/channels/leads/{ref}/consentimento"),
        ("GET", "/api/channels/opt-outs"),
        ("GET", "/api/channels/threads"),
        ("GET", "/api/channels/threads/{thread_id}"),
        ("GET", "/api/channels/threads/{thread_id}/handoffs"),
        ("GET", "/api/channels/uso"),
        ("PATCH", "/api/channels/threads/{thread_id}/participantes/{agent_key}"),
        ("POST", "/api/channels/agents/{agent_key}/decisoes/{chave}"),
        ("POST", "/api/channels/conversations/{conversation_id}/resumo"),
        ("POST", "/api/channels/handoffs/{handoff_id}/aceite"),
        ("POST", "/api/channels/leads/{lead_ref}/descarte/confirmar"),
        ("POST", "/api/channels/leads/{ref}/opt-out"),
        ("POST", "/api/channels/leads/{ref}/reativar"),
        ("POST", "/api/channels/opt-outs/{evento_id}/notificar"),
        ("POST", "/api/channels/threads/{thread_id}/mensagens"),
        ("POST", "/api/channels/threads/{thread_id}/resumo"),
        ("POST", "/api/channels/turns"),
        ("PUT", "/api/channels/ferramentas-token"),
        ("PUT", "/api/channels/leads/{ref}/opt-in"),
    ]


@pytest.mark.parametrize("method,path", _routes((CHANNEL_PREFIX,)))
def test_channel_routes_refuse_a_token_with_only_package_scopes(chan, method, path):
    chan.seed_agent()
    with chan.as_token(*sorted(PACKAGE_TOKEN_SCOPES)):
        resp = chan.request(method, _fill(path), json={})
    assert resp.status_code == 403 and _code(resp) == "scope_missing"


@pytest.mark.parametrize("method,path", _routes((CHANNEL_PREFIX,)))
def test_channel_routes_refuse_a_human_session(chan, method, path):
    chan.seed_agent()
    # the default user bearer of the `client` fixture ("test-token-valid")
    resp = chan.request(method, _fill(path), json={}, headers={"Authorization": "Bearer test-token-valid"})
    assert resp.status_code == 403 and _code(resp) == "product_required"


@pytest.mark.parametrize(
    "method,path",
    [r for r in _routes(BUSINESS_PREFIXES) if not r[1].startswith(CHANNEL_PREFIX)],
)
def test_no_other_business_route_accepts_a_channel_token(chan, method, path):
    chan.seed_agent()
    with chan.as_token(*sorted(CHANNEL_TOKEN_SCOPES)):
        resp = chan.request(method, _fill(path), json={})
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code} {resp.text[:160]}"
    assert _code(resp) in ("user_required", "platform_admin_required", "scope_missing"), f"{method} {path}"
