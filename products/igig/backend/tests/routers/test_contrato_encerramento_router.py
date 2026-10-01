"""Contratos — encerrar + editar (never deleted).

Admin-gated writes; `encerrado` freezes the contrato (409); org-scoped (another
org's contrato is a 404); billing's single rule (`vigentes_em`) stops counting an
encerrado contrato from the month after its `data_encerramento`.
"""
from datetime import timedelta
from uuid import uuid4

import pytest

from app.dependencies import coerce_org_uuid
from app.services.orcamentos import hoje_local

ORG = str(coerce_org_uuid("test-org-123"))
OUTRA_ORG = str(uuid4())


@pytest.fixture
def admin(crm_api):
    from app.main import app
    from app.pipelines import exigir_admin_da_org

    app.dependency_overrides[exigir_admin_da_org] = lambda: None
    yield crm_api
    app.dependency_overrides.pop(exigir_admin_da_org, None)


def _contrato(igig_db, org=ORG, **extra) -> dict:
    linha = {
        "id": str(uuid4()), "org_id": org, "cliente_id": str(uuid4()),
        "valor_mensal": 1500, "posts_por_mes": 12, "valor_excedente": 80,
        "dia_vencimento": 10, "data_inicio": "2026-01-01", "status": "ativo",
    }
    linha.update(extra)
    igig_db.table("contrato").insert(linha).execute()
    return linha


def _linha(igig_db, contrato_id) -> dict:
    return next(r for r in igig_db.table("contrato")._data if r["id"] == contrato_id)


class TestEncerrar:
    def test_happy_path(self, admin, igig_db):
        c = _contrato(igig_db)
        resp = admin.post(f"/api/contratos/{c['id']}/encerrar",
                          json={"data_encerramento": "2026-02-10", "motivo": "Cliente saiu"})
        assert resp.status_code == 200, resp.text
        dados = resp.json()["data"]
        assert dados["status"] == "encerrado"
        assert dados["data_encerramento"] == "2026-02-10"
        assert _linha(igig_db, c["id"])["motivo_encerramento"] == "Cliente saiu"

    def test_date_defaults_to_today(self, admin, igig_db):
        c = _contrato(igig_db)
        resp = admin.post(f"/api/contratos/{c['id']}/encerrar", json={"motivo": "Fim"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["data_encerramento"] == hoje_local().isoformat()

    def test_motivo_is_required(self, admin, igig_db):
        c = _contrato(igig_db)
        assert admin.post(f"/api/contratos/{c['id']}/encerrar", json={}).status_code == 422
        resp = admin.post(f"/api/contratos/{c['id']}/encerrar", json={"motivo": "   "})
        assert resp.status_code == 422
        assert _linha(igig_db, c["id"])["status"] == "ativo"

    def test_future_date_is_422(self, admin, igig_db):
        c = _contrato(igig_db)
        futuro = (hoje_local() + timedelta(days=3)).isoformat()
        resp = admin.post(f"/api/contratos/{c['id']}/encerrar",
                          json={"data_encerramento": futuro, "motivo": "x"})
        assert resp.status_code == 422
        assert resp.json()["code"] == "data_encerramento_invalida"

    def test_double_encerrar_is_409(self, admin, igig_db):
        c = _contrato(igig_db)
        body = {"data_encerramento": "2026-02-10", "motivo": "Fim"}
        assert admin.post(f"/api/contratos/{c['id']}/encerrar", json=body).status_code == 200
        resp = admin.post(f"/api/contratos/{c['id']}/encerrar", json=body)
        assert resp.status_code == 409
        assert resp.json()["code"] == "contrato_encerrado"

    def test_other_org_is_404(self, admin, igig_db):
        c = _contrato(igig_db, org=OUTRA_ORG)
        resp = admin.post(f"/api/contratos/{c['id']}/encerrar", json={"motivo": "x"})
        assert resp.status_code == 404
        assert _linha(igig_db, c["id"])["status"] == "ativo"

    def test_non_admin_is_403(self, crm_api, igig_db):
        c = _contrato(igig_db)
        resp = crm_api.post(f"/api/contratos/{c['id']}/encerrar", json={"motivo": "x"})
        assert resp.status_code == 403
        assert _linha(igig_db, c["id"])["status"] == "ativo"

    def test_unauthenticated_is_401(self, crm_api):
        resp = crm_api.raw().post(f"/api/contratos/{uuid4()}/encerrar", json={"motivo": "x"})
        assert resp.status_code == 401


class TestEditar:
    def test_patch_updates_commercial_fields(self, admin, igig_db):
        c = _contrato(igig_db)
        resp = admin.patch(f"/api/contratos/{c['id']}",
                           json={"valor_mensal": 2000, "posts_por_mes": 20, "dia_vencimento": 5})
        assert resp.status_code == 200, resp.text
        linha = _linha(igig_db, c["id"])
        assert (linha["valor_mensal"], linha["posts_por_mes"], linha["dia_vencimento"]) == (2000, 20, 5)
        assert linha["valor_excedente"] == 80

    def test_unknown_or_invalid_field_is_422(self, admin, igig_db):
        c = _contrato(igig_db)
        assert admin.patch(f"/api/contratos/{c['id']}", json={"status": "ativo"}).status_code == 422
        assert admin.patch(f"/api/contratos/{c['id']}", json={"dia_vencimento": 40}).status_code == 422

    def test_encerrado_is_409(self, admin, igig_db):
        c = _contrato(igig_db, status="encerrado", data_encerramento="2026-02-10")
        resp = admin.patch(f"/api/contratos/{c['id']}", json={"valor_mensal": 1})
        assert resp.status_code == 409
        assert resp.json()["code"] == "contrato_encerrado"

    def test_other_org_is_404(self, admin, igig_db):
        c = _contrato(igig_db, org=OUTRA_ORG)
        assert admin.patch(f"/api/contratos/{c['id']}", json={"valor_mensal": 1}).status_code == 404

    def test_non_admin_is_403(self, crm_api, igig_db):
        c = _contrato(igig_db)
        assert crm_api.patch(f"/api/contratos/{c['id']}", json={"valor_mensal": 1}).status_code == 403

    def test_unauthenticated_is_401(self, crm_api):
        resp = crm_api.raw().patch(f"/api/contratos/{uuid4()}", json={"valor_mensal": 1})
        assert resp.status_code == 401


class TestBillingRule:
    """`vigentes_em`: encerrado counts only for periods starting on/before its end."""

    def test_vigentes_em(self, igig_db):
        from noctusai_lib.integrations.persistence import SupabaseRecordStore

        from app.repositories import Repositorios

        ativo = _contrato(igig_db)
        enc = _contrato(igig_db, status="encerrado", data_encerramento="2026-02-10")
        repos = Repositorios(SupabaseRecordStore(igig_db))
        ids = lambda desde: {c["id"] for c in repos.contrato.vigentes_em(ORG, desde)}  # noqa: E731
        assert ids("2026-02-01") == {ativo["id"], enc["id"]}
        assert ids("2026-03-01") == {ativo["id"]}
