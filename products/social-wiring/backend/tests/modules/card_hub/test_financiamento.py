"""Financiamento / Escritura — the deal's closing paperwork (078).

WHAT THESE PIN
--------------
- one set per ATENDIMENTO, not per person (a certidão de casamento belongs to
  the transaction, not to either spouse);
- `situacao` is three-valued — "pendente" is not "recusado";
- 🔴 every CONTENT read appends to the access log, and listing metadata does
  NOT. An imposto de renda com recibo de entrega is a person's full declared
  income; who opened it has to be answerable;
- a soft-deleted document keeps its access log, including its own delete
  entry — soft delete is not erasure;
- the FGTS documents are a distinct GROUP, so the UI cannot render one set in
  the other's section.

Auth is not re-tested here — `test_auth_boundary.py` enumerates every mounted
card_hub route and asserts a strict 401 on each.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub import financiamento_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

PDF = ("ir.pdf", b"%PDF-1.7 fake", "application/pdf")


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
    scoped.set_table_data("atendimento_financiamento", [])
    scoped.set_table_data("atendimento_documentos", [])
    scoped.set_table_data("atendimento_documento_acessos", [])
    return cid, aid


def _upload(client, cid, *, tipo="certidao_casamento", arquivo=PDF):
    return client.post(
        f"/api/clientes/{cid}/financiamento/documentos",
        files={"file": arquivo},
        data={"tipo_documento": tipo},
        headers=_auth(),
    )


class TestTheEmptyState:
    def test_a_deal_with_no_financing_reads_as_pendente(self, client, scoped):
        """Not a 404 — a deal that has not reached the bank yet is normal."""
        cid, aid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/financiamento", headers=_auth()).json()
        assert body["situacao"] == "pendente"
        assert body["existe"] is False
        assert body["fgts"] is False
        assert body["documentos"] == []

    def test_it_advertises_both_document_groups(self, client, scoped):
        """The UI renders two sections; the groups come from the server so a
        naming convention never has to be re-derived on the client."""
        cid, aid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/financiamento", headers=_auth()).json()
        assert body["tipos_escritura"] == [
            "certidao_casamento",
            "escritura_pacto",
            "registro_pacto",
            "comprovante_residencia",
        ]
        assert body["tipos_fgts"] == [
            "imposto_renda_com_recibo",
            "carteira_trabalho",
            "extratos_fgts",
            "comprovante_residencia_1ano",
        ]


class TestTheDecision:
    def test_pendente_is_not_recusado(self, client, scoped):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/financiamento",
            json={"situacao": "aprovado"},
            headers=_auth(),
        )
        assert r.status_code == 200
        assert r.json()["situacao"] == "aprovado"
        assert r.json()["situacao_em"] is not None

    def test_an_unknown_situacao_is_refused(self, client, scoped):
        cid, aid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/financiamento",
            json={"situacao": "talvez"},
            headers=_auth(),
        )
        assert r.status_code == 422

    def test_the_decision_timestamp_is_not_bumped_by_an_unrelated_edit(
        self, client, scoped
    ):
        """🔴 Otherwise "when was this approved" silently becomes "when was
        this last edited"."""
        cid, aid = _seed(scoped)
        primeiro = client.patch(
            f"/api/clientes/{cid}/financiamento",
            json={"situacao": "aprovado"},
            headers=_auth(),
        ).json()["situacao_em"]

        depois = client.patch(
            f"/api/clientes/{cid}/financiamento",
            json={"observacoes": "conversado com o gerente"},
            headers=_auth(),
        ).json()
        assert depois["situacao_em"] == primeiro
        assert depois["situacao"] == "aprovado"


class TestDocuments:
    def test_an_escritura_document_uploads_into_its_group(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        r = _upload(client, cid, tipo="certidao_casamento")
        assert r.status_code == 200
        assert r.json()["grupo"] == "escritura"

    def test_an_fgts_document_uploads_into_the_other_group(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        r = _upload(client, cid, tipo="imposto_renda_com_recibo")
        assert r.json()["grupo"] == "fgts"

    def test_an_unknown_type_is_refused_by_name(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        r = _upload(client, cid, tipo="passaporte")
        assert r.status_code == 400
        assert "passaporte" in r.text

    def test_the_storage_key_starts_with_the_org_id(
        self, client, scoped, fake_storage
    ):
        """🔴 Migration 057's object-RLS policies match on the FIRST path
        segment. A key shaped any other way is readable across orgs."""
        cid, aid = _seed(scoped)
        _upload(client, cid)
        rows = scoped.table("atendimento_documentos").select("*").execute().data
        assert rows
        assert rows[0]["storage_path"].startswith(f"{ORG_ID}/atendimentos/{aid}/")

    def test_a_soft_deleted_document_is_not_listed(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        did = _upload(client, cid).json()["id"]
        r = client.delete(
            f"/api/clientes/{cid}/financiamento/documentos/{did}?motivo=errado",
            headers=_auth(),
        )
        assert r.status_code == 204
        body = client.get(f"/api/clientes/{cid}/financiamento", headers=_auth()).json()
        assert body["documentos"] == []

    def test_delete_requires_a_motivo(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        did = _upload(client, cid).json()["id"]
        r = client.delete(
            f"/api/clientes/{cid}/financiamento/documentos/{did}", headers=_auth()
        )
        assert r.status_code == 422

    def test_the_size_limit_is_driven_through_the_seam_not_a_patch(self):
        """No monkeypatching of the configured ceiling — see
        `DocumentoStore.validar`."""
        with pytest.raises(ValidationError_) as exc:
            svc.STORE.validar(
                tipo_documento="certidao_casamento",
                content_type="application/pdf",
                tamanho_bytes=50,
                max_bytes=10,
            )
        assert "0MB" not in str(exc.value)


class TestTheAccessLog:
    """🔴 An imposto de renda is a person's full declared income."""

    def test_reading_a_documents_content_is_logged(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        did = _upload(client, cid, tipo="imposto_renda_com_recibo").json()["id"]

        r = client.get(
            f"/api/clientes/{cid}/financiamento/documentos/{did}/url",
            headers=_auth(),
        )
        assert r.status_code == 200

        log = client.get(
            f"/api/clientes/{cid}/financiamento/documentos/{did}/acessos",
            headers=_auth(),
        ).json()
        assert log["total"] == 1
        assert log["items"][0]["acao"] == "view"

    def test_listing_metadata_is_NOT_logged(self, client, scoped, fake_storage):
        """Listing does not touch the file's bytes, so it is not an access.

        A log that recorded every page render would bury the reads that
        matter under noise and stop being usable as evidence.
        """
        cid, aid = _seed(scoped)
        did = _upload(client, cid).json()["id"]
        client.get(f"/api/clientes/{cid}/financiamento", headers=_auth())
        client.get(f"/api/clientes/{cid}/financiamento", headers=_auth())

        log = client.get(
            f"/api/clientes/{cid}/financiamento/documentos/{did}/acessos",
            headers=_auth(),
        ).json()
        assert log["total"] == 0

    def test_a_delete_is_logged_and_its_log_survives_the_delete(
        self, client, scoped, fake_storage
    ):
        """🔴 Soft delete is not erasure. The record of the deletion is
        precisely the thing an audit needs, so it must outlive the row's
        visibility."""
        cid, aid = _seed(scoped)
        did = _upload(client, cid).json()["id"]
        client.delete(
            f"/api/clientes/{cid}/financiamento/documentos/{did}?motivo=duplicado",
            headers=_auth(),
        )
        log = client.get(
            f"/api/clientes/{cid}/financiamento/documentos/{did}/acessos",
            headers=_auth(),
        ).json()
        assert [i["acao"] for i in log["items"]] == ["delete"]

    def test_a_download_is_logged_distinctly_from_a_view(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        did = _upload(client, cid).json()["id"]
        client.get(
            f"/api/clientes/{cid}/financiamento/documentos/{did}/url?intent=download",
            headers=_auth(),
        )
        log = client.get(
            f"/api/clientes/{cid}/financiamento/documentos/{did}/acessos",
            headers=_auth(),
        ).json()
        assert log["items"][0]["acao"] == "download"


class TestTheImovelSurfaceStaysUnlogged:
    def test_the_imovel_store_declares_no_access_log(self):
        """The two surfaces differ ON PURPOSE, and the difference is one
        explicit field rather than two divergent copies of a service."""
        from app.modules.imovel_hub import documentos_service as imovel_docs

        assert imovel_docs.STORE.acessos_table is None
        assert svc.STORE.acessos_table == "atendimento_documento_acessos"
