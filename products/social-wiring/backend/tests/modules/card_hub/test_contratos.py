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

import asyncio
from uuid import uuid4

from noctusai_lib.testing import TEST_USER_ID

from app.modules.card_hub import contratos_service as svc
from app.modules.card_hub.deps import BUCKET
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


def _seed_gerado(scoped, fake_storage, aid: str) -> dict:
    """A contract with ONE `origem='gerado'` version — the F5 generator's
    shape (migration 106/112/120) — seeded directly, since generation itself
    (F6 wiring) needs a fully-populated card this module's tests don't build.
    Puts real PDF + docx bytes in `fake_storage` so a `formato=` url actually
    resolves to something."""
    contrato_id, versao_id = str(uuid4()), str(uuid4())
    pdf_path = f"{ORG_ID}/contratos/{contrato_id}/{versao_id}"
    docx_path = f"{pdf_path}.docx"
    asyncio.run(
        fake_storage.put(bucket=BUCKET, key=pdf_path, data=b"%PDF-1.7 fake", content_type="application/pdf")
    )
    asyncio.run(
        fake_storage.put(bucket=BUCKET, key=docx_path, data=b"PK\x03\x04 fake docx", content_type=svc.MIME_DOCX)
    )
    scoped.set_table_data("atendimento_contratos", [{
        "id": contrato_id, "org_id": ORG_ID, "atendimento_id": aid,
        "titulo": "Contrato gerado", "modelo": "compra_venda", "status": "rascunho",
        "status_em": None, "status_por": None, "origem": "gerado", "criado_por": None,
        "deleted_at": None, "delete_motivo": None, "delete_solicitado_por": None,
        "created_at": "2026-09-16T00:00:00+00:00", "updated_at": None,
        "assinatura_data": None, "prazo_pendencias_dias": None,
    }])
    scoped.set_table_data("atendimento_contrato_versoes", [{
        "id": versao_id, "org_id": ORG_ID, "contrato_id": contrato_id,
        "storage_path": pdf_path, "nome_original": "contrato-gerado-v1.pdf",
        "mime_type": "application/pdf", "tamanho_bytes": 13,
        "tipo_documento": svc.TIPO_VERSAO, "numero": 1, "rotulo": None,
        "origem": "gerado", "enviado_por": None, "deleted_at": None,
        "delete_motivo": None, "delete_solicitado_por": None,
        "created_at": "2026-09-16T00:00:00+00:00",
        "contexto_sha256": "a" * 64,
        "docx_storage_path": docx_path, "docx_tamanho_bytes": 18,
    }])
    scoped.set_table_data("atendimento_contrato_versao_acessos", [])
    return {"contrato_id": contrato_id, "versao_id": versao_id}


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


class TestDocxFormat:
    """`?formato=docx` (migration 120) — the editable sibling of a gerado
    version's PDF, downloadable through the SAME url endpoint, same
    access-log rules."""

    def test_formato_docx_signs_the_docx_sibling_and_logs_the_access(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        ids = _seed_gerado(scoped, fake_storage, aid)
        r = client.get(
            f"/api/clientes/{cid}/contratos/{ids['contrato_id']}"
            f"/versoes/{ids['versao_id']}/url?formato=docx",
            headers=_auth(),
        )
        assert r.status_code == 200, r.text
        assert "url" in r.json()

        rows = scoped.table("atendimento_contrato_versao_acessos").select("*").execute().data
        assert len(rows) == 1
        assert rows[0]["acao"] == "view"
        assert rows[0]["documento_id"] == ids["versao_id"]

    def test_formato_docx_download_intent_is_logged_distinctly(
        self, client, scoped, fake_storage
    ):
        cid, aid = _seed(scoped)
        ids = _seed_gerado(scoped, fake_storage, aid)
        client.get(
            f"/api/clientes/{cid}/contratos/{ids['contrato_id']}"
            f"/versoes/{ids['versao_id']}/url?formato=docx&intent=download",
            headers=_auth(),
        )
        rows = scoped.table("atendimento_contrato_versao_acessos").select("*").execute().data
        assert rows[0]["acao"] == "download"

    def test_formato_docx_on_an_upload_version_is_a_404(self, client, scoped, fake_storage):
        """An upload's `docx_storage_path` is always NULL (migration 120's
        CHECK) — asking for its docx is asking for something that never
        existed, not a server error."""
        cid, aid = _seed(scoped)
        body = _criar(client, cid).json()
        versao_id = body["versao_atual"]["id"]
        r = client.get(
            f"/api/clientes/{cid}/contratos/{body['id']}/versoes/{versao_id}"
            "/url?formato=docx",
            headers=_auth(),
        )
        assert r.status_code == 404, r.text

    def test_an_unknown_formato_is_refused(self, client, scoped, fake_storage):
        cid, aid = _seed(scoped)
        ids = _seed_gerado(scoped, fake_storage, aid)
        r = client.get(
            f"/api/clientes/{cid}/contratos/{ids['contrato_id']}"
            f"/versoes/{ids['versao_id']}/url?formato=txt",
            headers=_auth(),
        )
        assert r.status_code == 400, r.text


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


class TestProcessoLegado:
    """Migration 151 — the admin-only "processo anterior à plataforma"
    switch (`PUT .../contratos/{id}/processo-legado`). Owner directive,
    2026-09-22: EXPLICIT, admin-only, logged — never an automatic date
    heuristic. Same trusted-`noctus_users`-row gate as
    `decidir_conflito_route` (migration 138); see `test_conflitos.py`'s
    `TestOnlyAdminsCanDecide` for the sibling spoof-closing tests."""

    def _make_admin(self, client) -> None:
        client.mock_supabase.set_table_data(
            "noctus_users",
            [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}],
        )

    def _url(self, cid, contrato_id) -> str:
        return f"/api/clientes/{cid}/contratos/{contrato_id}/processo-legado"

    def test_a_member_cannot_set_it(self, client, scoped, fake_storage):
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]

        r = client.put(
            self._url(cid, contrato_id),
            json={"ativo": True, "motivo": "Deal iniciado antes da plataforma."},
            headers=_auth(),
        )

        assert r.status_code == 403, r.text
        rows = scoped.table("atendimento_contratos").select("*").execute().data
        assert not rows[0].get("processo_legado")

    def test_unauthenticated_is_a_strict_401(self, anon_client, scoped, fake_storage):
        cid, _aid = _seed(scoped)
        r = anon_client.put(
            self._url(cid, uuid4()), json={"ativo": True, "motivo": "x" * 5}
        )
        assert r.status_code == 401, r.text

    def test_ativo_true_without_motivo_is_a_422(self, client, scoped, fake_storage):
        self._make_admin(client)
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]

        r = client.put(self._url(cid, contrato_id), json={"ativo": True}, headers=_auth())
        assert r.status_code == 422, r.text

    def test_ativo_true_with_a_too_short_motivo_is_a_422(self, client, scoped, fake_storage):
        self._make_admin(client)
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]

        r = client.put(
            self._url(cid, contrato_id), json={"ativo": True, "motivo": "ok"}, headers=_auth()
        )
        assert r.status_code == 422, r.text

    def test_an_admin_sets_it_and_it_is_logged(self, client, scoped, fake_storage):
        self._make_admin(client)
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]

        r = client.put(
            self._url(cid, contrato_id),
            json={
                "ativo": True,
                "motivo": "Deal iniciado antes da plataforma — certidões emitidas fora do fluxo.",
            },
            headers=_auth(),
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["processo_legado"] is True
        assert body["processo_legado_por"]["id"] == TEST_USER_ID
        assert body["processo_legado_em"] is not None

        row = scoped.table("atendimento_contratos").select("*").execute().data[0]
        assert row["processo_legado"] is True
        assert row["processo_legado_por"] == TEST_USER_ID
        assert row["processo_legado_em"] is not None
        assert row["processo_legado_motivo"].startswith("Deal iniciado antes da plataforma")

    def test_an_admin_clears_it(self, client, scoped, fake_storage):
        self._make_admin(client)
        cid, _aid = _seed(scoped)
        contrato_id = _criar(client, cid).json()["id"]
        client.put(
            self._url(cid, contrato_id),
            json={"ativo": True, "motivo": "Deal iniciado antes da plataforma."},
            headers=_auth(),
        )

        r = client.put(self._url(cid, contrato_id), json={"ativo": False}, headers=_auth())

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["processo_legado"] is False

        row = scoped.table("atendimento_contratos").select("*").execute().data[0]
        assert row["processo_legado"] is False
        # The dispensation's own reason is stale once lifted — never left
        # behind to look like it still applies.
        assert row["processo_legado_motivo"] is None

    def test_a_foreign_contrato_is_a_404(self, client, scoped, fake_storage):
        self._make_admin(client)
        cid, _aid = _seed(scoped)
        r = client.put(
            self._url(cid, uuid4()),
            json={"ativo": True, "motivo": "Deal iniciado antes da plataforma."},
            headers=_auth(),
        )
        assert r.status_code == 404, r.text


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
