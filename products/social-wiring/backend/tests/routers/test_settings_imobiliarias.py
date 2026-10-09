"""`/api/settings/imobiliarias` — the org's registry of signing companies
(migration 215), plus the narrowed org-wide `/imobiliaria` form.

Same DI-seam fixture shape as `test_settings_testemunhas.py` (a real
`Depends()` override, not a patch of our own code).
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.dependencies import coerce_org_uuid, get_social_wiring_client

ORG_ID = str(coerce_org_uuid("test-org-123"))
CNPJ_1 = "11.222.333/0001-81"
CNPJ_2 = "06.057.235/0001-04"


@pytest.fixture
def scoped_sw(client):
    from app.main import app

    scoped = client.mock_supabase.schema("social_wiring")
    prev = app.dependency_overrides.get(get_social_wiring_client)
    app.dependency_overrides[get_social_wiring_client] = lambda: scoped
    scoped.set_table_data("atendimento_contratos", [])
    yield scoped
    if prev is None:
        app.dependency_overrides.pop(get_social_wiring_client, None)
    else:
        app.dependency_overrides[get_social_wiring_client] = prev


def _criar(client, **extra):
    body = {"razao_social": "Imobiliária Um Ltda", "cnpj": CNPJ_1, **extra}
    return client.post("/api/settings/imobiliarias", json=body)


class TestAuth:
    def test_every_route_requires_auth(self, anon_client):
        i = str(uuid4())
        for method, path, kw in (
            ("get", "/api/settings/imobiliarias", {}),
            ("post", "/api/settings/imobiliarias", {"json": {"razao_social": "x", "cnpj": CNPJ_1}}),
            ("patch", f"/api/settings/imobiliarias/{i}", {"json": {"nome_fantasia": "x"}}),
            ("delete", f"/api/settings/imobiliarias/{i}", {}),
        ):
            r = getattr(anon_client, method)(path, **kw)
            assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"


class TestCrud:
    def test_empty_list(self, client, scoped_sw):
        r = client.get("/api/settings/imobiliarias")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

    def test_create_round_trips_with_faltando(self, client, scoped_sw):
        r = _criar(client, creci_pj_regiao="CRECI/SP")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["razao_social"] == "Imobiliária Um Ltda"
        assert body["creci_pj_regiao"] == "CRECI/SP"
        assert body["faltando"] == ["responsavel_nome", "responsavel_creci", "endereco_cidade"]
        listed = client.get("/api/settings/imobiliarias").json()
        assert listed["total"] == 1
        assert listed["items"][0]["id"] == body["id"]
        assert listed["items"][0]["contratos_em_uso"] == 0

    def test_invalid_cnpj_and_unknown_field_are_422(self, client, scoped_sw):
        assert _criar(client, cnpj="11.222.333/0001-82").status_code == 422
        assert _criar(client, org_id=str(uuid4())).status_code == 422
        assert client.post("/api/settings/imobiliarias", json={"cnpj": CNPJ_1}).status_code == 422

    def test_duplicate_active_cnpj_is_409_with_error_body(self, client, scoped_sw):
        assert _criar(client).status_code == 201
        r = _criar(client, razao_social="Outra", cnpj="11222333000181")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "IMOBILIARIA_CNPJ_DUPLICADO"
        assert r.json()["error"]["message"] == "Já existe uma imobiliária ativa com este CNPJ."

    def test_patch_changes_only_sent_fields(self, client, scoped_sw):
        i = _criar(client, nome_fantasia="Um").json()["id"]
        r = client.patch(f"/api/settings/imobiliarias/{i}", json={"responsavel_nome": "Fulano"})
        assert r.status_code == 200, r.text
        assert r.json()["responsavel_nome"] == "Fulano"
        assert r.json()["nome_fantasia"] == "Um"

    def test_patch_empty_is_400_unknown_is_404_dup_is_409(self, client, scoped_sw):
        a = _criar(client).json()["id"]
        b = _criar(client, razao_social="Dois", cnpj=CNPJ_2).json()["id"]
        assert client.patch(f"/api/settings/imobiliarias/{a}", json={}).status_code == 400
        assert client.patch(f"/api/settings/imobiliarias/{uuid4()}", json={"email": "a@b.c"}).status_code == 404
        r = client.patch(f"/api/settings/imobiliarias/{b}", json={"cnpj": CNPJ_1})
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "IMOBILIARIA_CNPJ_DUPLICADO"
        assert client.patch(f"/api/settings/imobiliarias/{a}", json={"razao_social": ""}).status_code == 422

    def test_delete_is_soft_and_frees_the_cnpj(self, client, scoped_sw):
        i = _criar(client).json()["id"]
        assert client.delete(f"/api/settings/imobiliarias/{i}").status_code == 204
        assert client.get("/api/settings/imobiliarias").json()["total"] == 0
        rows = scoped_sw.table("org_imobiliarias").select("*").eq("id", i).execute().data
        assert rows and rows[0]["excluida_em"]
        assert client.delete(f"/api/settings/imobiliarias/{i}").status_code == 404
        assert _criar(client).status_code == 201

    def test_contratos_em_uso_counts_live_contracts(self, client, scoped_sw):
        i = _criar(client).json()["id"]
        scoped_sw.set_table_data("atendimento_contratos", [
            {"id": str(uuid4()), "org_id": ORG_ID, "imobiliaria_id": i, "deleted_at": None},
            {"id": str(uuid4()), "org_id": ORG_ID, "imobiliaria_id": i, "deleted_at": None},
            {"id": str(uuid4()), "org_id": ORG_ID, "imobiliaria_id": i, "deleted_at": "2026-01-01T00:00:00+00:00"},
            {"id": str(uuid4()), "org_id": ORG_ID, "imobiliaria_id": None, "deleted_at": None},
        ])
        assert client.get("/api/settings/imobiliarias").json()["items"][0]["contratos_em_uso"] == 2


class TestOrgWideFormNarrowed:
    def test_identity_fields_are_now_422(self, client, scoped_sw):
        for campo in ("razao_social", "cnpj", "creci_pj", "endereco_cidade"):
            r = client.put("/api/settings/imobiliaria", json={campo: "x"})
            assert r.status_code == 422, campo

    def test_get_carries_only_org_wide_fields(self, client, scoped_sw):
        scoped_sw.set_table_data("org_dados_cadastrais", [])
        body = client.get("/api/settings/imobiliaria").json()
        assert "razao_social" not in body and "cnpj" not in body
        assert {"plataforma_assinatura_nome", "posse_multa_diaria", "suporte_email", "updated_at"} <= set(body)
