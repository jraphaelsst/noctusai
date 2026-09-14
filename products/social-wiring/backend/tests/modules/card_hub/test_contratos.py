"""Contratos — the deal's contract, in revision (106).

WHAT THESE PIN
--------------
- an atendimento may carry more than one contract, and each contract is a
  STATUS plus a list of immutable VERSIONS — never a file replaced in place;
- version numbering never reuses a number, even past a soft-deleted version;
- `versao_atual` is the highest-`numero` LIVE version;
- a cancelado contract refuses new versions (409);
- a contract cannot be left with zero live versions (409) — only deleting
  the whole contract can remove its last version;
- 🔴 every CONTENT read of a version appends to the access log, same
  contract `financiamento_service`'s documents carry.

Auth is not re-tested here — `test_auth_boundary.py` enumerates every
mounted card_hub route and asserts a strict 401 on each.
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub import contratos_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

PDF = ("contrato.pdf", b"%PDF-1.7 fake", "application/pdf")
DOCX = (
    "contrato.docx",
    b"PK\x03\x04 fake docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
PNG = ("foto.png", b"\x89PNG\r\n fake", "image/png")


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str) -> dict:
    return {
        "id": aid,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "status": "aberta",
        "substituida_por": None,
        "arquivado": False,
        "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
    }


def _seed(scoped):
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_contratos", [])
    scoped.set_table_data("atendimento_contrato_versoes", [])
    scoped.set_table_data("atendimento_contrato_versao_acessos", [])
    return cid, aid


def _criar(client, cid, *, titulo="Contrato de compra e venda", modelo=None, rotulo=None, arquivo=PDF):
    data = {"titulo": titulo}
    if modelo is not None:
        data["modelo"] = modelo
    if rotulo is not None:
        data["rotulo"] = rotulo
    return client.post(
        f"/api/clientes/{cid}/contratos",
        files={"file": arquivo},
        data=data,
        headers=_auth(),
    )


def _nova_versao(client, cid, contrato_id, *, rotulo=None, arquivo=DOCX):
    data = {}
    if rotulo is not None:
        data["rotulo"] = rotulo
    return client.post(
        f"/api/clientes/{cid}/contratos/{contrato_id}/versoes",
        files={"file": arquivo},
        data=data,
        headers=_auth(),
    )


class TestCreatingAContract:
    def test_creating_uploads_exactly_one_version(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        r = _criar(client, cid, rotulo="REV 25.07")
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "rascunho"
        assert body["origem"] == "upload"
        assert body["modelo"] == "compra_venda"
        assert len(body["versoes"]) == 1
        assert body["versoes"][0]["numero"] == 1
        assert body["versoes"][0]["rotulo"] == "REV 25.07"
        assert body["versao_atual"]["numero"] == 1

    def test_modelo_defaults_to_compra_venda(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        r = _criar(client, cid)
        assert r.json()["modelo"] == "compra_venda"

    def test_an_explicit_modelo_is_honoured(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        r = _criar(client, cid, modelo="compra_venda_a_vista")
        assert r.json()["modelo"] == "compra_venda_a_vista"

    def test_an_empty_titulo_is_refused(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        r = _criar(client, cid, titulo="")
        assert r.status_code == 422

    def test_an_unknown_mime_is_refused(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        r = _criar(client, cid, arquivo=PNG)
        assert r.status_code == 400

    def test_a_rejected_upload_leaves_no_orphan_contract(
        self, client, scoped, fake_storage
    ):
        """No incomplete commits — a refused file must not leave a contrato
        row with zero versions."""
        cid, aid = _seed(scoped)
        _criar(client, cid, arquivo=PNG)
        listagem = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()
        assert listagem["contratos"] == []


class TestTheEmptyState:
    def test_a_card_with_no_contracts_reads_as_an_empty_list(self, client, scoped):
        cid, aid = _seed(scoped)
        r = client.get(f"/api/clientes/{cid}/contratos", headers=_auth())
        assert r.status_code == 200
        assert r.json() == {"contratos": []}

    def test_listing_is_newest_first(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        primeiro = _criar(client, cid, titulo="Primeiro contrato").json()["id"]
        segundo = _criar(client, cid, titulo="Segundo contrato").json()["id"]
        ids = [c["id"] for c in client.get(
            f"/api/clientes/{cid}/contratos", headers=_auth()
        ).json()["contratos"]]
        assert ids == [segundo, primeiro]


class TestVersioning:
    def test_a_new_version_becomes_versao_atual(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        r = _nova_versao(client, cid, contrato_id, rotulo="REV FINAL")
        assert r.status_code == 201
        body = r.json()
        assert body["versao_atual"]["numero"] == 2
        assert body["versao_atual"]["rotulo"] == "REV FINAL"
        assert [v["numero"] for v in body["versoes"]] == [2, 1]

    def test_a_cancelado_contract_refuses_new_versions(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"status": "cancelado"},
            headers=_auth(),
        )
        r = _nova_versao(client, cid, contrato_id)
        assert r.status_code == 409
        assert "cancelado" in r.json()["error"]["message"].lower()

    def test_numbering_never_reuses_a_deleted_versions_number(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        v2 = _nova_versao(client, cid, contrato_id).json()["versao_atual"]["id"]
        client.delete(
            f"/api/clientes/{cid}/contratos/{contrato_id}/versoes/{v2}"
            "?motivo=duplicado",
            headers=_auth(),
        )
        r = _nova_versao(client, cid, contrato_id)
        assert r.json()["versao_atual"]["numero"] == 3


class TestDeletingAVersion:
    def test_deleting_the_only_remaining_version_is_refused(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        body = _criar(client, cid).json()
        versao_id = body["versao_atual"]["id"]
        r = client.delete(
            f"/api/clientes/{cid}/contratos/{body['id']}/versoes/{versao_id}"
            "?motivo=teste",
            headers=_auth(),
        )
        assert r.status_code == 409
        assert "pelo menos uma vers" in r.json()["error"]["message"].lower()

    def test_deleting_one_of_two_versions_succeeds(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        v2 = _nova_versao(client, cid, contrato_id).json()["versao_atual"]["id"]
        r = client.delete(
            f"/api/clientes/{cid}/contratos/{contrato_id}/versoes/{v2}"
            "?motivo=duplicado",
            headers=_auth(),
        )
        assert r.status_code == 204
        body = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()
        assert len(body["contratos"][0]["versoes"]) == 1

    def test_delete_requires_a_motivo(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        body = _criar(client, cid).json()
        r = client.delete(
            f"/api/clientes/{cid}/contratos/{body['id']}/versoes/"
            f"{body['versao_atual']['id']}",
            headers=_auth(),
        )
        assert r.status_code == 422


class TestPatch:
    def test_status_change_stamps_status_em_and_status_por(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        r = client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"status": "em_revisao"},
            headers=_auth(),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "em_revisao"
        assert r.json()["status_em"] is not None

    def test_an_unrelated_edit_does_not_bump_status_em(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        primeiro = client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"status": "em_revisao"},
            headers=_auth(),
        ).json()["status_em"]
        depois = client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"titulo": "Novo título"},
            headers=_auth(),
        ).json()
        assert depois["status_em"] == primeiro
        assert depois["titulo"] == "Novo título"

    def test_any_status_to_any_status_is_allowed(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"status": "assinado"},
            headers=_auth(),
        )
        r = client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"status": "rascunho"},
            headers=_auth(),
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rascunho"

    def test_an_unknown_field_is_refused(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        r = client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"nao_existe": True},
            headers=_auth(),
        )
        assert r.status_code == 422

    def test_an_unknown_status_is_refused(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        r = client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"status": "talvez"},
            headers=_auth(),
        )
        assert r.status_code == 422


class TestDeletingAContract:
    def test_deleting_the_contract_soft_deletes_its_versions_too(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        _nova_versao(client, cid, contrato_id)
        r = client.delete(
            f"/api/clientes/{cid}/contratos/{contrato_id}?motivo=cancelado pelo cliente",
            headers=_auth(),
        )
        assert r.status_code == 204
        assert client.get(
            f"/api/clientes/{cid}/contratos", headers=_auth()
        ).json() == {"contratos": []}

    def test_delete_requires_a_motivo(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        r = client.delete(
            f"/api/clientes/{cid}/contratos/{contrato_id}", headers=_auth()
        )
        assert r.status_code == 422


class TestUrlAndAccessLog:
    def test_reading_a_versions_content_is_logged(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        body = _criar(client, cid).json()
        versao_id = body["versao_atual"]["id"]
        r = client.get(
            f"/api/clientes/{cid}/contratos/{body['id']}/versoes/{versao_id}/url",
            headers=_auth(),
        )
        assert r.status_code == 200
        assert "url" in r.json()

        rows = scoped.table("atendimento_contrato_versao_acessos").select("*").execute().data
        assert len(rows) == 1
        assert rows[0]["acao"] == "view"

    def test_a_download_intent_is_logged_distinctly(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        body = _criar(client, cid).json()
        versao_id = body["versao_atual"]["id"]
        client.get(
            f"/api/clientes/{cid}/contratos/{body['id']}/versoes/{versao_id}"
            "/url?intent=download",
            headers=_auth(),
        )
        rows = scoped.table("atendimento_contrato_versao_acessos").select("*").execute().data
        assert rows[0]["acao"] == "download"


class TestOrgIsolation:
    def test_a_contrato_from_another_org_is_a_404(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]

        # Corrupt the row's org_id directly, as if it belonged to another org.
        rows = scoped.table("atendimento_contratos").select("*").execute().data
        for row in rows:
            row["org_id"] = str(uuid4())
        scoped.set_table_data("atendimento_contratos", rows)

        r = client.patch(
            f"/api/clientes/{cid}/contratos/{contrato_id}",
            json={"titulo": "invasão"},
            headers=_auth(),
        )
        assert r.status_code == 404

    def test_a_foreign_versao_id_on_a_real_contrato_is_a_404(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        r = client.get(
            f"/api/clientes/{cid}/contratos/{contrato_id}/versoes/{uuid4()}/url",
            headers=_auth(),
        )
        assert r.status_code == 404


class TestTheSizeLimitSeam:
    def test_the_size_limit_is_driven_through_the_seam_not_a_patch(self):
        """No monkeypatching of the configured ceiling — see
        `DocumentoStore.validar`."""
        import pytest
        from noctusai_lib.primitives.exceptions import ValidationError_

        with pytest.raises(ValidationError_) as exc:
            svc.VERSOES_STORE.validar(
                tipo_documento="contrato",
                content_type="application/pdf",
                tamanho_bytes=50,
                max_bytes=10,
            )
        assert "0MB" not in str(exc.value)
