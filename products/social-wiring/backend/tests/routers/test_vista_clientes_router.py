"""`/api/leads/vista-clientes/*`: org-admin for everything that calls Vista or writes (strict 403 for a member), strict 401 without a
session, dry-run by default (nothing written), the per-org rate budget handed to the adapter. The caller's role is the TRUSTED
`noctus_users` row (never user_metadata)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.integrations.vista import FakeVistaAdapter
from noctusai_lib.testing import TEST_USER_ID, MockSupabaseClient, MockUser, MockUserResponse, bind_consent_module_to_mock

ORG = "00000000-0000-4000-8000-0000000000b1"
CLI = "00000000-0000-4000-8000-0000000000c1"
BASE = "/api/leads/vista-clientes"
H = {"Authorization": "Bearer test-token"}


class Scene:
    def __init__(self, tc, db, rates):
        self.tc, self.db, self.rates = tc, db, rates

    def req(self, m, url, json=None):
        return getattr(self.tc, m)(url, headers=H, **({"json": json} if json is not None else {}))


def _scene(org_role, monkeypatch):
    core = MockSupabaseClient()
    core.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(id=TEST_USER_ID, org_id=ORG, org_role=org_role)))
    core.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG, "org_role": org_role}])
    core.set_table_data("notifications", [])
    db = MockSupabaseClient().schema("social_wiring")
    db.set_table_data("clientes", [{"id": CLI, "org_id": ORG, "nome": "Ana", "chave_canonica": "+5511999990001", "chave_tipo": "telefone", "ativo": True}])
    for t in ("vista_cliente_links", "vista_cliente_avisos"):
        db.set_table_data(t, [])
    db.set_table_data("vista_clientes_sync_estado", [{"org_id": ORG, "vista_rps": 2.5, "importar_identidade": False}])
    rates: list = []

    def fabrica(org_id, *, rate_per_sec=None):
        rates.append(rate_per_sec)
        return FakeVistaAdapter(clientes=[{"Codigo": "100", "Nome": "Ana Maria", "Celular": "11 99999-0001", "Cliente": "Sim"}])

    from app.services import vista_credenciais

    monkeypatch.setattr(vista_credenciais, "adapter_ou_503", fabrica)  # Vista (a network edge) is faked; the auth guard is the real one
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=core),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=core),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=core),
    ):
        from app.dependencies import get_current_user_org_unified
        from app.main import app
        from app.modules.leads.deps import get_leads_client
        from app.modules.leads.routers.vista_clientes import get_vista_clientes_core

        bind_consent_module_to_mock(core)
        # Session resolution is faked (the first test's mock is what the app singleton's auth gate captured); the ROLE guard under test
        # (`require_org_admin_for`) is the real one, reading the trusted `noctus_users` row of `core`.
        app.dependency_overrides[get_current_user_org_unified] = lambda: (MockUser(id=TEST_USER_ID, org_id=ORG), "test-token", ORG)
        app.dependency_overrides[get_vista_clientes_core] = lambda: core
        app.dependency_overrides[get_leads_client] = lambda: db
        yield Scene(TestClient(app), db, rates)
        app.dependency_overrides.clear()


@pytest.fixture
def cena(monkeypatch):
    yield from _scene("owner", monkeypatch)


@pytest.fixture
def cena_membro(monkeypatch):
    yield from _scene(None, monkeypatch)


# strict 401 without a session: `tests/modules/leads/test_auth_boundary.py` (every vista-clientes route is listed there).


def test_a_member_may_read_but_is_403_on_every_write_or_vista_call(cena_membro):
    assert cena_membro.req("get", f"{BASE}/resumo").status_code == 200
    assert cena_membro.req("post", f"{BASE}/sync").status_code == 403
    assert cena_membro.req("put", f"{BASE}/config", {"vista_rps": 1.0, "importar_identidade": False}).status_code == 403
    assert cena_membro.req("post", f"{BASE}/avisos/00000000-0000-4000-8000-0000000000a1/resolver", {"acao": "ignorada"}).status_code == 403
    assert cena_membro.rates == []  # Vista was never reached


def test_an_admin_dry_run_is_the_default_writes_nothing_and_uses_the_org_budget(cena):
    r = cena.req("post", f"{BASE}/sync")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["dry_run"] is True and d["casados"] == 1
    assert cena.rates == [2.5]  # the org's own Vista budget reached the adapter
    assert cena.db.table("vista_cliente_links").select("*").execute().data == []


def test_an_admin_real_run_writes_and_the_resumo_reflects_it(cena):
    assert cena.req("post", f"{BASE}/sync?dry_run=false").status_code == 200
    assert cena.req("get", f"{BASE}/resumo").json()["data"]["vinculados"] == 1


def test_config_rejects_an_unreasonable_budget_and_the_identity_flag_defaults_off(cena):
    assert cena.req("get", f"{BASE}/config").json()["data"]["importar_identidade"] is False
    assert cena.req("put", f"{BASE}/config", {"vista_rps": 99, "importar_identidade": False}).status_code == 422
    assert cena.req("put", f"{BASE}/config", {"vista_rps": 1.0, "importar_identidade": True}).status_code == 200
