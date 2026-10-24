"""`PUT/DELETE /api/imoveis/{codigo}/certidoes/{tipo}/manual` (migration 306)
— a certidão's fields typed with NO file.

WHAT THESE PIN
--------------
- a typed record answers `GET .../certidoes` (the read the contract loader
  uses) with `documento_id: None`, `sem_arquivo: True`, `confirmado: True`;
- newest wins between a typed record and an upload: an upload AFTER typing
  supersedes it; typing AFTER an upload corrects it;
- a typed matrícula entry is never hidden by a visualização upload (P5);
- a field the tipo does not carry is refused by name; an all-empty record
  is refused; DELETE of nothing is a 404; an unknown imóvel is a 404;
- the write stamps the caller's org and actor.

Auth: `test_imovel_auth_boundary.py` enumerates every mounted route (these
two included) and asserts a strict 401.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.imovel_hub.conftest import CODIGO, ORG_ID, auth, documento_row, seed

_URL = f"/api/imoveis/{CODIGO}/certidoes"


def _por_tipo(body: dict) -> dict:
    return {i["tipo"]: i for i in body["items"]}


class TestCertidaoManual:
    def test_a_typed_cnd_iptu_with_no_file_answers_the_certidoes_read(self, client, scoped):
        seed(scoped)
        r = client.put(
            f"{_URL}/cnd_iptu/manual",
            json={
                "numero": "CND-0001/2026",
                "emitida_em": "2026-10-01",
                "validade_ate": "2026-12-30",
                "resultado": "negativa",
                "inscricao_imobiliaria": "12.345.678-9",
            },
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        item = _por_tipo(r.json())["cnd_iptu"]
        assert item["documento_id"] is None
        assert item["sem_arquivo"] is True
        assert item["confirmado"] is True
        assert (item["numero"], item["emitida_em"], item["resultado"]) == (
            "CND-0001/2026", "2026-10-01", "negativa",
        )
        assert r.json()["manuais"]["cnd_iptu"]["confirmado_por"] is not None

        lido = client.get(_URL, headers=auth()).json()
        assert _por_tipo(lido)["cnd_iptu"]["manual_id"] == item["manual_id"]
        rows = scoped.table("imovel_certidoes_manuais").select("*").execute().data
        assert [(r["org_id"], r["codigo"], r["tipo"]) for r in rows] == [(ORG_ID, CODIGO, "cnd_iptu")]

    def test_a_second_put_replaces_the_record_not_appends(self, client, scoped):
        seed(scoped)
        client.put(f"{_URL}/cnd_condominio/manual", json={"emitida_em": "2026-09-01"}, headers=auth())
        r = client.put(
            f"{_URL}/cnd_condominio/manual",
            json={"emitida_em": "2026-10-02", "resultado": "negativa"},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        assert len(scoped.table("imovel_certidoes_manuais").select("*").execute().data) == 1
        item = _por_tipo(r.json())["cnd_condominio"]
        assert (item["emitida_em"], item["resultado"]) == ("2026-10-02", "negativa")

    def test_typing_after_an_upload_wins_and_a_later_upload_supersedes(self, client, scoped):
        antigo = documento_row(
            str(uuid4()), tipo_documento="matricula", emitida_em="2025-01-01",
            created_at="2025-01-02T00:00:00+00:00",
        )
        seed(scoped, documentos=[antigo])
        r = client.put(f"{_URL}/matricula/manual", json={"emitida_em": "2026-10-10"}, headers=auth())
        item = _por_tipo(r.json())["matricula"]
        assert (item["emitida_em"], item["sem_arquivo"], item["tipo_documento_matricula"]) == (
            "2026-10-10", True, "certidao",
        )

        # An upload NEWER than the typed record supersedes it.
        manuais = scoped.table("imovel_certidoes_manuais").select("*").execute().data
        novo = documento_row(
            str(uuid4()), tipo_documento="matricula", emitida_em="2099-01-01",
            created_at="2099-01-02T00:00:00+00:00",
        )
        scoped.set_table_data("imovel_documentos", [antigo, novo])
        scoped.set_table_data("imovel_certidoes_manuais", manuais)
        item = _por_tipo(client.get(_URL, headers=auth()).json())["matricula"]
        assert (item["emitida_em"], item["sem_arquivo"]) == ("2099-01-01", False)

    def test_a_visualizacao_upload_never_hides_a_typed_certidao(self, client, scoped):
        seed(scoped)
        client.put(f"{_URL}/matricula/manual", json={"emitida_em": "2026-10-10"}, headers=auth())
        manuais = scoped.table("imovel_certidoes_manuais").select("*").execute().data
        scoped.set_table_data(
            "imovel_documentos",
            [
                documento_row(
                    str(uuid4()), tipo_documento="matricula", emitida_em=None,
                    tipo_documento_matricula="visualizacao",
                    created_at="2099-01-01T00:00:00+00:00",
                )
            ],
        )
        scoped.set_table_data("imovel_certidoes_manuais", manuais)
        item = _por_tipo(client.get(_URL, headers=auth()).json())["matricula"]
        assert (item["emitida_em"], item["sem_arquivo"]) == ("2026-10-10", True)

    def test_a_field_the_tipo_does_not_carry_is_refused(self, client, scoped):
        seed(scoped)
        r = client.put(
            f"{_URL}/cnd_condominio/manual",
            json={"emitida_em": "2026-10-01", "numero": "X-1"},
            headers=auth(),
        )
        assert r.status_code == 400
        assert "numero" in r.text

    def test_an_all_empty_record_is_refused(self, client, scoped):
        seed(scoped)
        r = client.put(f"{_URL}/cnd_iptu/manual", json={}, headers=auth())
        assert r.status_code == 400

    def test_an_unknown_tipo_is_a_422(self, client, scoped):
        seed(scoped)
        r = client.put(f"{_URL}/guia_iptu/manual", json={"inscricao_imobiliaria": "1"}, headers=auth())
        assert r.status_code == 422

    def test_delete_drops_the_record_and_the_upload_answers_again(self, client, scoped):
        doc = documento_row(
            str(uuid4()), tipo_documento="cnd_iptu", resultado="positiva",
            created_at="2025-01-01T00:00:00+00:00",
        )
        seed(scoped, documentos=[doc])
        client.put(f"{_URL}/cnd_iptu/manual", json={"resultado": "negativa"}, headers=auth())
        r = client.delete(f"{_URL}/cnd_iptu/manual", headers=auth())
        assert r.status_code == 200, r.text
        item = _por_tipo(r.json())["cnd_iptu"]
        assert (item["resultado"], item["documento_id"]) == ("positiva", doc["id"])
        assert r.json()["manuais"] == {}

    def test_deleting_nothing_is_a_404(self, client, scoped):
        seed(scoped)
        assert client.delete(f"{_URL}/cnd_iptu/manual", headers=auth()).status_code == 404

    def test_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        r = client.put(
            "/api/imoveis/NOPE9/certidoes/cnd_iptu/manual",
            json={"resultado": "negativa"},
            headers=auth(),
        )
        assert r.status_code == 404
