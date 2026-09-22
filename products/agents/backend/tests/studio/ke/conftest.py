"""Shared fixtures for the BE-KE (knowledge + evals) router test suite.

Contract §J2.3: router registration is BE-RT's (``app/main.py``) — this
slice's own tests mount `studio_knowledge_router` + `studio_evals_router`
on a LOCAL, bare ``FastAPI()`` app instead of importing ``app.main.app``
(whose full router set isn't wired yet). Auth still goes through the
product's REAL ``require_member``/``require_admin`` deps
(``app.dependencies``) — same session-cookie / ``pk_*`` / legacy-JWT
resolution chain every other router test exercises, only patched at the
same ``noctusai_seed.database.DatabaseModule`` class level the root
``tests/conftest.py::client`` fixture uses (see that fixture's docstring
for why the class-level patch, not an instance-level one, is required —
``app.dependencies`` builds its OWN ``DatabaseModule`` instance separate
from ``app/database.py``'s).

Store dependencies (``get_studio_knowledge_store_dep`` /
``get_studio_definition_store_dep`` — the ONE agent resolver every studio
route uses — / ``get_eval_store_dep``) are overridden onto a single SHARED
Fake instance per store, per request — mirrors
``tests/routers/conftest.py::agents_client``'s ``_Stores`` bag pattern.
``get_current_hash_dep`` is bound to ``stores.current_hash`` (a Fake
compiler: a deterministic hash per version the test can change).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.testing import AuthClient, MockSupabaseClient, MockUser, MockUserResponse

# Re-exported — every BE-KE router test seeds roles / binds a second
# caller through these, same helpers the rest of the product's router
# suite uses (never duplicated locally).
from tests.routers.conftest import (  # noqa: F401
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    bind_user,
    seed_org_role,
)

from app.stores.studio_definitions import FakeStudioDefinitionStore
from app.stores.studio_evals import FakeEvalStore
from app.stores.studio_knowledge import FakeStudioKnowledgeStore


def _build_local_app() -> FastAPI:
    from fastapi import HTTPException

    from app.routers.studio_evals_router import router as evals_router
    from app.routers.studio_knowledge_router import router as knowledge_router
    from noctusai_lib.primitives.exceptions import http_exception_handler

    app = FastAPI()
    # The full `app.main.app` gets this handler from
    # `noctusai_lib.api.app_factory.create_product_app` — a bare `FastAPI()`
    # doesn't, so every `HTTPException(detail={"detail": ..., "code": ...})`
    # this slice's routers raise would come back double-nested
    # (`{"detail": {"detail": ..., "code": ...}}`) instead of the flat
    # `{"detail": ..., "code": ...}` shape contract §D documents and every
    # router test in this product asserts against.
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(knowledge_router)
    app.include_router(evals_router)
    return app


class _Stores:
    """Bag of the shared Fake store instances one test's HTTP requests all
    resolve to, via ``app.dependency_overrides`` — see module docstring."""

    def __init__(self) -> None:
        self.knowledge = FakeStudioKnowledgeStore()
        self.evals = FakeEvalStore()
        self.defs = FakeStudioDefinitionStore()
        #: version_id -> the hash the Fake compiler returns for it "now".
        self.hashes: dict[UUID, str] = {}

    def current_hash(self, org_id: UUID, agent, version) -> str:
        return self.hashes.get(version.id, f"sha256:{'0' * 56}{str(version.id)[:8]}")


@pytest.fixture
def ke_client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id="test-org-123"))
    )

    with patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):
        from app.routers.studio_agents_router import get_studio_definition_store_dep
        from app.routers.studio_evals_router import get_current_hash_dep, get_eval_store_dep
        from app.routers.studio_knowledge_router import get_studio_knowledge_store_dep

        app = _build_local_app()
        stores = _Stores()
        app.dependency_overrides[get_studio_knowledge_store_dep] = lambda: stores.knowledge
        app.dependency_overrides[get_studio_definition_store_dep] = lambda: stores.defs
        app.dependency_overrides[get_eval_store_dep] = lambda: stores.evals
        app.dependency_overrides[get_current_hash_dep] = lambda: stores.current_hash

        tc = TestClient(app)
        with tc:
            client = AuthClient(tc, mock_sb)
            client.stores = stores
            yield client


def seed_studio_agent(
    ke_client, *, key: str = "isaia", org_id: UUID = DEFAULT_ORG_ID, agent_id: UUID | None = None,
    definition_mode: str = "studio", ativo: bool = True, publicacao_limiar: float = 0.800,
):
    """The minimum fixture every BE-KE router test needs: a studio agent
    the routers can resolve by ``(org_id, key)``."""
    return ke_client.stores.defs.seed_agent(
        org_id, key, agent_id=agent_id, definition_mode=definition_mode,
        ativo=ativo, publicacao_limiar=publicacao_limiar,
    )


def seed_draft(ke_client, agent, *, org_id: UUID = DEFAULT_ORG_ID, created_by: UUID = DEFAULT_USER_ID):
    """A draft version of ``agent`` in the shared definitions Fake."""
    return ke_client.stores.defs.create_draft(org_id, agent.id, None, created_by)


__all__ = [
    "DEFAULT_ORG_ID",
    "DEFAULT_USER_ID",
    "bind_user",
    "ke_client",
    "seed_org_role",
    "seed_studio_agent",
    "seed_draft",
]
