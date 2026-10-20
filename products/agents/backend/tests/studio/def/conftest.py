"""Fixtures for the BE-DEF studio suite (contract §J2.3: wave-1 routers are
NOT in ``main.py`` yet — they are mounted on a local test app).

``studio_client`` builds a bare FastAPI app, applies the seed's
``configure_app`` (the SAME exception handlers ``create_product_app``
installs — so the flat ``{"detail", "code"}`` error body is what production
returns) and mounts the two BE-DEF routers. Every seam is a real
``app.dependency_overrides`` binding onto a shared in-memory double:
``FakeStudioDefinitionStore``, ``FakeEvalGate`` and ``FakeKnowledgeCatalog``
(§J2.1: "returning FakeEvalGate() ONLY under the test app").

Auth rides the root ``client`` fixture's patched Supabase mock (the same
legacy-JWT bridge every other router test in this product uses).

NB: this package is named ``def`` (a Python keyword) per the contract, so
nothing here can be imported with an ``import`` statement — shared helpers
are exposed as fixtures instead.
"""
from __future__ import annotations

from uuid import NAMESPACE_OID, UUID, uuid5

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers.skills_biblioteca_router import router as skills_biblioteca_router
from app.routers.studio_agents_router import (
    get_eval_gate_dep,
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
    router as studio_agents_router,
)
from app.routers.studio_clients_router import router as studio_clients_router
from app.routers.studio_conteudo_router import router as studio_conteudo_router
from app.routers.studio_evals_router import router as studio_evals_router
from app.routers.studio_knowledge_router import router as studio_knowledge_router
from app.routers.studio_package_sync_router import router as studio_package_sync_router
from app.routers.studio_padrao_router import router as studio_padrao_router
from app.routers.studio_ui_router import router as studio_ui_router
from app.routers.qualificacao_router import get_padrao_store_dep
from app.qualificacao.store import FakePadraoStore
from app.stores.conformidade import FakeConformidadeStore
from app.dependencies import get_conformidade_store_dep
from app.studio import bundles as studio_bundles
from app.stores.studio_definitions import FakeStudioDefinitionStore
from app.studio.models import FakeEvalGate, FakeKnowledgeCatalog
from noctusai_lib.api.app_factory import configure_app
from noctusai_lib.testing import AuthClient
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, bind_user, seed_org_role

OTHER_ORG_ID: UUID = uuid5(NAMESPACE_OID, "studio-other-org")
OTHER_USER_ID: UUID = uuid5(NAMESPACE_OID, "studio-other-user")


class StudioHarness:
    """What a router test needs: the authed client, the unauthenticated raw
    client, the shared doubles, and the role/org helpers."""

    def __init__(self, client: AuthClient, raw: TestClient, mock_supabase) -> None:
        self.client = client
        self.raw = raw
        self.mock_supabase = mock_supabase
        self.store = FakeStudioDefinitionStore()
        self.gate = FakeEvalGate()
        self.catalog = FakeKnowledgeCatalog()
        #: the qualification standards (A-RT2): a platform definition publishes only with a published standard
        self.padroes = FakePadraoStore()
        self.conformidade = FakeConformidadeStore()
        self.org_id = DEFAULT_ORG_ID
        self.user_id = DEFAULT_USER_ID

    def as_role(self, role: str) -> "StudioHarness":
        """The caller's org role. Owners/admins are ALSO platform admins here (the studio's definition
        reads are platform-admin-only) — use :meth:`as_org_admin_only` for the plain org admin."""
        seed_org_role(self, role=role)
        if role in ("owner", "admin"):
            self.mock_supabase.set_table_data("noctus_users", [{
                "id": str(self.user_id), "org_id": str(self.org_id), "org_role": role, "role": "admin",
            }])
        return self

    def as_org_admin_only(self, role: str = "owner") -> "StudioHarness":
        """An org owner/admin that is NOT a platform admin (`noctus_users.role == 'user'`)."""
        self.mock_supabase.set_table_data("noctus_users", [{
            "id": str(self.user_id), "org_id": str(self.org_id), "org_role": role, "role": "user",
        }])
        return self

    def as_other_org(self, role: str = "owner", *, platform: bool = False) -> "StudioHarness":
        bind_user(self, user_id=OTHER_USER_ID, org_id=OTHER_ORG_ID)
        self.mock_supabase.set_table_data("noctus_users", [{
            "id": str(OTHER_USER_ID), "org_id": str(OTHER_ORG_ID), "org_role": role, "role": "admin" if platform else "user",
        }])
        return self

    # `seed_org_role` / `bind_user` expect `.mock_supabase` on the object.

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, **kw):
        return self.client.post(url, **kw)

    def put(self, url, **kw):
        return self.client.put(url, **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, **kw)


def _build_app() -> FastAPI:
    app = FastAPI()
    configure_app(app, settings)
    app.include_router(studio_agents_router)
    app.include_router(studio_clients_router)
    app.include_router(studio_conteudo_router)
    app.include_router(skills_biblioteca_router)

    app.include_router(studio_padrao_router)
    app.include_router(studio_ui_router)
    # mounted for the visibility-tier matrix only (their seams stay unbound: auth answers first)
    app.include_router(studio_knowledge_router)
    app.include_router(studio_evals_router)
    app.include_router(studio_package_sync_router)
    return app


@pytest.fixture
def studio(client) -> StudioHarness:
    app = _build_app()
    raw = TestClient(app)
    harness = StudioHarness(AuthClient(raw, client.mock_supabase), raw, client.mock_supabase)
    app.dependency_overrides[get_studio_definition_store_dep] = lambda: harness.store
    app.dependency_overrides[get_eval_gate_dep] = lambda: harness.gate
    app.dependency_overrides[get_knowledge_catalog_dep] = lambda: harness.catalog
    app.dependency_overrides[get_padrao_store_dep] = lambda: harness.padroes
    app.dependency_overrides[get_conformidade_store_dep] = lambda: harness.conformidade
    from tests.channels.julia_v2 import publicar_padrao

    harness.padrao_versao_id = publicar_padrao(harness.padroes)
    harness.as_role("owner")
    try:
        yield harness
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def studio_com_padrao(studio):
    """``studio`` with the studio COMPILE covering the pinned qualification standard (what production does)."""
    saved = studio_bundles._padrao_reader
    studio_bundles.configure_padrao_reader(studio.padroes)
    try:
        yield studio
    finally:
        studio_bundles.configure_padrao_reader(saved)


@pytest.fixture
def bare_studio_app(client) -> TestClient:
    """The routers with NO seam overrides except the store — proves the
    gate/catalog defaults fail closed."""
    app = _build_app()
    store = FakeStudioDefinitionStore()
    app.dependency_overrides[get_studio_definition_store_dep] = lambda: store
    seed_org_role(client, role="owner")
    tc = TestClient(app)
    try:
        yield AuthClient(tc, client.mock_supabase), store
    finally:
        app.dependency_overrides.clear()
