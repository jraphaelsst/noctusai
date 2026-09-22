"""``/api/studio/agents/{key}/clients`` (contract §D2, §H)."""
from __future__ import annotations

import pytest

BASE = "/api/studio/agents"


def _agent(studio, key="isa"):
    resp = studio.post(BASE, json={"key": key, "nome": key.title()})
    assert resp.status_code == 201, resp.text


def _client(studio, key="isa", slug="marca-x", **extra):
    resp = studio.post(f"{BASE}/{key}/clients", json={"slug": slug, "nome": "Marca X", **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAuthBoundary:
    @pytest.mark.parametrize(
        "method, path",
        [
            ("get", f"{BASE}/isa/clients"),
            ("post", f"{BASE}/isa/clients"),
            ("get", f"{BASE}/isa/clients/00000000-0000-0000-0000-000000000001"),
            ("patch", f"{BASE}/isa/clients/00000000-0000-0000-0000-000000000001"),
            ("post", f"{BASE}/isa/clients/00000000-0000-0000-0000-000000000001/entries"),
        ],
    )
    def test_unauthenticated_is_401(self, studio, method, path):
        resp = getattr(studio.raw, method)(path, **({} if method == "get" else {"json": {}}))
        assert resp.status_code == 401

    def test_member_reads_but_cannot_write(self, studio):
        _agent(studio)
        client = _client(studio)
        studio.as_role("member")
        assert studio.get(f"{BASE}/isa/clients").status_code == 200
        assert studio.get(f"{BASE}/isa/clients/{client['id']}").status_code == 200
        for resp in (
            studio.post(f"{BASE}/isa/clients", json={"slug": "y", "nome": "Y"}),
            studio.patch(f"{BASE}/isa/clients/{client['id']}", json={"nome": "Z"}),
            studio.post(f"{BASE}/isa/clients/{client['id']}/entries", json={"tipo": "nota", "titulo": "t"}),
        ):
            assert resp.status_code == 403
            assert resp.json()["code"] == "role_missing"

    def test_other_org_404(self, studio):
        _agent(studio)
        client = _client(studio)
        studio.as_other_org()
        _agent(studio)  # same key, other org
        resp = studio.get(f"{BASE}/isa/clients/{client['id']}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "client_not_found"
        assert studio.get(f"{BASE}/isa/clients").json()["items"] == []


class TestClients:
    def test_crud_and_counts(self, studio):
        _agent(studio)
        client = _client(studio, resumo="Marca de moda.")
        assert client["entradas"] == [] and client["ativo"] is True
        dup = studio.post(f"{BASE}/isa/clients", json={"slug": "marca-x", "nome": "Dup"})
        assert dup.status_code == 409 and dup.json()["code"] == "client_exists"

        e1 = studio.post(f"{BASE}/isa/clients/{client['id']}/entries",
                         json={"tipo": "marca", "titulo": "Tom", "conteudo": "leve"})
        assert e1.status_code == 201, e1.text
        assert e1.json()["status"] == "ativo"
        studio.post(f"{BASE}/isa/clients/{client['id']}/entries", json={"tipo": "decisao", "titulo": "D"})

        listed = studio.get(f"{BASE}/isa/clients").json()["items"]
        assert listed[0]["total_entradas"] == 2
        assert "entradas" not in listed[0]

        full = studio.get(f"{BASE}/isa/clients/{client['id']}").json()
        assert [e["titulo"] for e in full["entradas"]] == ["Tom", "D"]

        patched = studio.patch(f"{BASE}/isa/clients/{client['id']}", json={"resumo": "Novo.", "ativo": False}).json()
        assert (patched["resumo"], patched["ativo"]) == ("Novo.", False)

        entry = studio.patch(f"{BASE}/isa/clients/{client['id']}/entries/{e1.json()['id']}",
                             json={"status": "arquivado"}).json()
        assert entry["status"] == "arquivado"
        assert studio.delete(f"{BASE}/isa/clients/{client['id']}/entries/{e1.json()['id']}").status_code == 204
        assert len(studio.get(f"{BASE}/isa/clients/{client['id']}").json()["entradas"]) == 1

    @pytest.mark.parametrize(
        "body",
        [
            {"tipo": "inventado", "titulo": "x"},
            {"tipo": "nota", "titulo": ""},
            {"tipo": "nota", "titulo": "x", "extra": 1},
            {"tipo": "nota", "titulo": "x", "status": "apagado"},
        ],
    )
    def test_entry_validation_422(self, studio, body):
        _agent(studio)
        client = _client(studio)
        assert studio.post(f"{BASE}/isa/clients/{client['id']}/entries", json=body).status_code == 422

    def test_bad_slug_and_null_nome_422(self, studio):
        _agent(studio)
        assert studio.post(f"{BASE}/isa/clients", json={"slug": "Com Espaco", "nome": "x"}).status_code == 422
        client = _client(studio)
        resp = studio.patch(f"{BASE}/isa/clients/{client['id']}", json={"nome": None})
        assert resp.status_code == 422 and resp.json()["code"] == "invalid_field"

    def test_client_of_other_agent_is_404(self, studio):
        _agent(studio)
        _agent(studio, key="outro")
        foreign = _client(studio, key="outro")
        resp = studio.get(f"{BASE}/isa/clients/{foreign['id']}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "client_not_found"

    def test_entry_of_other_client_is_404(self, studio):
        _agent(studio)
        a = _client(studio, slug="a")
        b = _client(studio, slug="b")
        entry = studio.post(f"{BASE}/isa/clients/{a['id']}/entries", json={"tipo": "nota", "titulo": "t"}).json()
        resp = studio.patch(f"{BASE}/isa/clients/{b['id']}/entries/{entry['id']}", json={"titulo": "x"})
        assert resp.status_code == 404
        assert resp.json()["code"] == "entry_not_found"
        assert studio.delete(f"{BASE}/isa/clients/{b['id']}/entries/{entry['id']}").status_code == 404

    def test_unknown_agent_404(self, studio):
        resp = studio.get(f"{BASE}/nope/clients")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"
