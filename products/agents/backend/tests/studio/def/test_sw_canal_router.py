"""Staff status + test of the onboarding channel to social-wiring: auth strict 401/403, the status never provisions, the
test provisions then proves the wire, and no response ever carries the token."""
from __future__ import annotations

import json

import pytest

from app.routers.sw_canal_router import get_sw_canal_dep
from tests.onboarding.sw_canal_kit import build_kit

URL = "/api/studio/plataforma/sw-canal"


@pytest.fixture
def canal(studio):
    kit = build_kit()
    studio.raw.app.dependency_overrides[get_sw_canal_dep] = lambda: kit.canal
    studio.kit = kit
    return studio


def test_unauthenticated_is_strictly_401(canal):
    assert canal.raw.get(URL).status_code == 401
    assert canal.raw.post(f"{URL}/testar").status_code == 401


def test_a_non_platform_org_admin_is_403_and_nothing_is_provisioned(canal):
    canal.as_org_admin_only("owner")
    for r in (canal.get(URL), canal.post(f"{URL}/testar")):
        assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"
    assert canal.kit.linhas() == [] and canal.kit.seen == []


def test_status_before_any_use_is_ausente_and_does_not_provision(canal):
    r = canal.get(URL)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    j = r.json()
    assert j["estado"] == "ausente" and j["escopo"] == "social-wiring:onboarding-settings" and j["emissor"] == "noctus-platform"
    assert canal.kit.linhas() == [] and canal.kit.seen == []


def test_test_connection_provisions_proves_the_wire_and_reports_success(canal):
    r = canal.post(f"{URL}/testar")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["status"]["estado"] == "provisionado" and j["status"]["expira_em"]
    assert j["status"]["ultima_chamada_ok"]["evento"] == "sw_canal_conexao_testada"
    assert j["status"]["ultimo_erro"] is None
    assert canal.get(URL).json()["estado"] == "provisionado"


def test_test_connection_failure_returns_the_named_reason_in_ptbr(canal):
    canal.kit.admin.fail_mint = True
    j = canal.post(f"{URL}/testar").json()
    assert j["ok"] is False and j["codigo"] == "emissao_falhou" and "social-wiring" in j["motivo"]
    assert j["status"]["ultimo_erro"]["codigo"] == "emissao_falhou" and j["status"]["ultimo_erro"]["em"]


def test_a_wire_that_refuses_the_token_is_shown_as_the_last_error(canal):
    assert canal.post(f"{URL}/testar").json()["ok"] is True
    canal.kit.forcar["/api/julia/onboarding/whoami"] = 401
    j = canal.post(f"{URL}/testar").json()
    assert j["ok"] is False and j["codigo"] == "sw_unauthorized"
    assert canal.get(URL).json()["ultimo_erro"]["codigo"] == "sw_unauthorized"


def test_an_unreadable_event_store_is_a_visible_502_not_a_blank_card(canal):
    def quebra(*, ok):
        raise RuntimeError("db down")

    canal.kit.eventos.ultimo = quebra
    r = canal.get(URL)
    assert r.status_code == 502 and r.json()["code"] == "status_indisponivel"


def test_no_response_ever_contains_the_token(canal):
    corpos = [canal.post(f"{URL}/testar").text, canal.get(URL).text]
    canal.kit.forcar["/api/julia/onboarding/whoami"] = 403
    corpos.append(canal.post(f"{URL}/testar").text)
    segredo = canal.kit.guardado()
    assert segredo
    for corpo in corpos:
        assert segredo not in corpo
    for k in ("token", "secret", "segredo", "prefixo", "prefix"):
        assert all(k not in json.loads(c) for c in corpos)
