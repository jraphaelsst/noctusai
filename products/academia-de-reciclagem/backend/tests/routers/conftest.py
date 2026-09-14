"""Shared fixtures for the contract §B.1–§B.5 router test suite.

`store` overrides `app.dependencies.get_store` with a fresh
`FakeKnowledgeStore()` per test (state persists across the multiple
requests one test typically issues, since the override closes over the
SAME instance every call — see `app.dependencies.get_store`'s own
docstring).

`set_auth` overrides `app.dependencies.get_auth_context` with a
caller-supplied `AuthContext` — the DI seam for constructing arbitrary
SSO-user / product-token / human_personal scenarios without minting a
real session or token. `require_scopes`'s OWN role/scope check (NOT
overridden) still runs against the substituted context, so 403
`role_missing` / `scope_missing` assertions exercise real code.

Both fixtures pop their override at teardown, and both are safe to use
INSIDE the `client` fixture from `tests/conftest.py` (same `app.main.app`
singleton — Python module caching guarantees one instance per test
session) — `client`'s `MockSupabaseClient` patches stay required for any
route that resolves org role via `get_core_client()` (`require_scopes`'s
user-role branch, and §D step 8's `approved_by` role check).

`sign_assertion` builds a real HS256 `X-Approval-Assertion` JWS with a
canonical-JSON `body_sha256` — tests MUST send the exact same canonical
bytes as the request body (`content=`, never `json=`, which does not
guarantee sorted-keys/compact-separator output) or the signed hash will
not match what `app.auth.assertion.canonical_body_sha256` re-derives.
"""
from __future__ import annotations

import json
import time
from uuid import UUID, uuid4

import jwt
import pytest

from app.auth.assertion import canonical_body_sha256
from app.dependencies import get_auth_context, get_store
from app.knowledge import FakeKnowledgeStore
from app.main import app


@pytest.fixture
def store():
    fake = FakeKnowledgeStore()
    app.dependency_overrides[get_store] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture
def set_auth():
    def _set(ctx):
        app.dependency_overrides[get_auth_context] = lambda: ctx

    yield _set
    app.dependency_overrides.pop(get_auth_context, None)


def canonical_body(payload: dict) -> bytes:
    """The EXACT bytes a test must send as the request body for a signed
    assertion's `body_sha256` to match — see module docstring."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sign_assertion(
    *,
    secret: str,
    org_id: UUID,
    agent_id: UUID,
    approved_by: UUID,
    tool: str,
    method: str,
    path: str,
    body: bytes,
    requested_by: UUID | None = None,
    aud: str = "academia-de-reciclagem",
    exp_delta: int = 60,
    jti: UUID | None = None,
    **claim_overrides,
) -> str:
    """Build a compact HS256 `X-Approval-Assertion` per contract §D."""
    now = int(time.time())
    claims = {
        "jti": str(jti or uuid4()),
        "iss": "agents",
        "aud": aud,
        "sub": str(agent_id),
        "org": str(org_id),
        "tool": tool,
        "method": method,
        "path": path,
        "body_sha256": canonical_body_sha256(body),
        "approved_by": str(approved_by),
        "requested_by": str(requested_by) if requested_by else str(approved_by),
        "iat": now,
        "exp": now + exp_delta,
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, secret, algorithm="HS256")


__all__ = ["canonical_body", "sign_assertion"]
