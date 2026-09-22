"""Operator-authored checklist lines — ported from social-wiring's
`tests/modules/card_hub/test_checklist_extras.py`.

A line is a REQUEST; a document is only its current ANSWER:
- `concluido` is derived, never stored;
- uploading twice REPLACES; deleting the file KEEPS the line;
- a crossed write is a 422, never a 200 that silently drops the value.
"""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.domain.card_hub import checklist_extras as svc
from tests.domain.card_hub.conftest import AUTH, ORG_ID


def _seed(hub) -> str:
    return hub.new_entity()


def _seed_upload_catalogue(hub) -> None:
    hub.seed(hub.cfg.tables.documento_tipos, [
        hub.documento_tipo_row(hub.cfg.checklist_extra_tipo_documento, categoria="nao_classificado", retencao_dias=365)
    ])


def _base(hub, eid) -> str:
    return hub.url(eid, "/checklist-extras")


def _listar(hub, eid) -> list[dict]:
    resp = hub.client.get(_base(hub, eid), headers=AUTH)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _criar(hub, eid, *, label="Convenção", tipo="texto") -> dict:
    resp = hub.client.post(_base(hub, eid), json={"label": label, "tipo": tipo}, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload(hub, eid, extra_id, *, nome="scan.pdf", conteudo=b"%PDF-1.4 x"):
    return hub.client.post(
        f"{_base(hub, eid)}/{extra_id}/documento",
        files={"file": (nome, conteudo, "application/pdf")},
        headers=AUTH,
    )


class TestCrud:
    def test_a_new_entity_has_no_extras(self, hub):
        eid = _seed(hub)
        assert hub.client.get(_base(hub, eid), headers=AUTH).json() == {"items": [], "total": 0}

    def test_create_returns_the_full_row_shape(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid, label="Convenção do condomínio")
        assert list(criado) == ["id", "label", "tipo", "valor_texto", "documento", "concluido", "ordem"]
        assert criado["label"] == "Convenção do condomínio"
        assert criado["tipo"] == "texto"
        assert criado["valor_texto"] is None
        assert criado["documento"] is None
        assert criado["concluido"] is False

    def test_create_persists_and_lists(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid)
        assert [i["id"] for i in _listar(hub, eid)] == [criado["id"]]

    def test_label_is_trimmed_on_create(self, hub):
        eid = _seed(hub)
        assert _criar(hub, eid, label="  Escritura  ")["label"] == "Escritura"

    def test_new_lines_land_at_the_bottom(self, hub):
        eid = _seed(hub)
        a, b, c = (_criar(hub, eid, label=x) for x in "ABC")
        assert [a["ordem"], b["ordem"], c["ordem"]] == [0, 1, 2]
        assert [i["label"] for i in _listar(hub, eid)] == ["A", "B", "C"]

    def test_list_is_ordered_by_ordem_then_created_at(self, hub):
        eid = _seed(hub)
        hub.seed(hub.cfg.tables.checklist_extras, [
            hub.checklist_extra_row(str(uuid4()), eid, label="C", ordem=5),
            hub.checklist_extra_row(str(uuid4()), eid, label="B", ordem=0, created_at="2026-02-02T00:00:00+00:00"),
            hub.checklist_extra_row(str(uuid4()), eid, label="A", ordem=0, created_at="2026-01-01T00:00:00+00:00"),
        ])
        assert [i["label"] for i in _listar(hub, eid)] == ["A", "B", "C"]

    def test_patch_sets_valor_texto_and_label_and_ordem(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid)
        resp = hub.client.patch(
            f"{_base(hub, eid)}/{criado['id']}",
            json={"label": "Novo rótulo", "valor_texto": "1234-5", "ordem": 7},
            headers=AUTH,
        )
        assert resp.status_code == 200, resp.text
        assert (resp.json()["label"], resp.json()["valor_texto"], resp.json()["ordem"]) == ("Novo rótulo", "1234-5", 7)

    def test_patch_only_writes_what_it_carried(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid)
        hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"valor_texto": "mantém"}, headers=AUTH)
        body = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"ordem": 3}, headers=AUTH).json()
        assert body["valor_texto"] == "mantém"
        assert body["ordem"] == 3

    def test_explicit_null_valor_texto_clears_it(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid)
        hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"valor_texto": "algo"}, headers=AUTH)
        body = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"valor_texto": None}, headers=AUTH).json()
        assert body["valor_texto"] is None
        assert body["concluido"] is False

    def test_blank_label_is_refused_not_stored(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid)
        resp = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"label": "   "}, headers=AUTH)
        assert resp.status_code == 400, resp.text
        assert _listar(hub, eid)[0]["label"] == "Convenção"

    def test_delete_is_a_soft_delete(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid)
        resp = hub.client.delete(f"{_base(hub, eid)}/{criado['id']}", headers=AUTH)
        assert resp.status_code == 204, resp.text
        assert _listar(hub, eid) == []
        stored = hub.rows(hub.cfg.tables.checklist_extras)
        assert len(stored) == 1 and stored[0]["deleted_at"] is not None

    def test_another_entitys_line_is_a_404_not_an_edit(self, hub):
        eid, outro = _seed(hub), _seed(hub)
        criado = _criar(hub, eid)
        resp = hub.client.patch(f"{_base(hub, outro)}/{criado['id']}", json={"label": "invadido"}, headers=AUTH)
        assert resp.status_code == 404, resp.text

    def test_unknown_extra_is_a_404(self, hub):
        eid = _seed(hub)
        resp = hub.client.delete(f"{_base(hub, eid)}/{uuid4()}", headers=AUTH)
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.tables.checklist_extras


class TestConcluidoIsDerived:
    def test_texto_line_ticks_when_it_has_text(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid, tipo="texto")
        assert criado["concluido"] is False
        body = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"valor_texto": "Bloco B"}, headers=AUTH).json()
        assert body["concluido"] is True

    def test_whitespace_only_text_does_not_tick(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid, tipo="texto")
        body = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"valor_texto": "   "}, headers=AUTH).json()
        assert body["valor_texto"] is None
        assert body["concluido"] is False

    def test_a_soft_deleted_document_unticks_the_line(self, hub):
        eid = _seed(hub)
        did = str(uuid4())
        hub.seed(hub.cfg.tables.documentos, [hub.documento_row(did, eid, deleted_at="2026-03-01T00:00:00+00:00")])
        hub.seed(hub.cfg.tables.checklist_extras, [hub.checklist_extra_row(str(uuid4()), eid, tipo="arquivo", documento_id=did)])
        linha = _listar(hub, eid)[0]
        assert linha["documento"] is None
        assert linha["concluido"] is False

    def test_nothing_stores_a_concluido_column(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid)
        hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"valor_texto": "x"}, headers=AUTH)
        assert "concluido" not in hub.rows(hub.cfg.tables.checklist_extras)[0]

    def test_the_rule_is_a_pure_function(self):
        assert svc.concluido_de({"tipo": "texto", "valor_texto": "ok"}, None) is True
        assert svc.concluido_de({"tipo": "texto", "valor_texto": " "}, None) is False
        assert svc.concluido_de({"tipo": "texto", "valor_texto": None}, None) is False
        assert svc.concluido_de({"tipo": "arquivo"}, None) is False
        assert svc.concluido_de({"tipo": "arquivo"}, {"id": "d"}) is True


class TestDocumento:
    def test_upload_links_the_document_and_ticks(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        resp = _upload(hub, eid, criado["id"], nome="convencao.pdf")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["concluido"] is True
        assert body["documento"]["nome_original"] == "convencao.pdf"
        assert list(body["documento"]) == ["id", "nome_original", "mime_type", "tamanho_bytes", "created_at"]

    def test_upload_goes_through_the_documents_path(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        _upload(hub, eid, criado["id"])
        docs = hub.rows(hub.cfg.tables.documentos)
        assert len(docs) == 1
        assert docs[0]["tipo_documento"] == hub.cfg.checklist_extra_tipo_documento == "outro"
        assert docs[0]["categoria_lgpd"] == "nao_classificado"
        assert docs[0]["retencao_ate"] is not None
        assert docs[0]["storage_path"].startswith(f"{ORG_ID}/{hub.cfg.storage_segment}/{eid}/")

    def test_upload_onto_an_occupied_line_replaces(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        primeiro = _upload(hub, eid, criado["id"], nome="errado.pdf").json()
        segundo = _upload(hub, eid, criado["id"], nome="certo.pdf").json()
        assert segundo["documento"]["nome_original"] == "certo.pdf"
        assert segundo["documento"]["id"] != primeiro["documento"]["id"]
        docs = {d["id"]: d for d in hub.rows(hub.cfg.tables.documentos)}
        assert docs[primeiro["documento"]["id"]]["deleted_at"] is not None
        assert docs[primeiro["documento"]["id"]]["delete_motivo"] == svc.MOTIVO_SUBSTITUICAO
        assert docs[segundo["documento"]["id"]]["deleted_at"] is None
        assert len(_listar(hub, eid)) == 1

    def test_delete_documento_keeps_the_line(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        enviado = _upload(hub, eid, criado["id"]).json()
        resp = hub.client.delete(f"{_base(hub, eid)}/{criado['id']}/documento", headers=AUTH)
        assert resp.status_code == 204, resp.text
        items = _listar(hub, eid)
        assert [(i["id"], i["documento"], i["concluido"]) for i in items] == [(criado["id"], None, False)]
        doc = hub.rows(hub.cfg.tables.documentos)[0]
        assert doc["id"] == enviado["documento"]["id"]
        assert doc["deleted_at"] is not None
        assert doc["delete_motivo"] == svc.MOTIVO_REMOCAO

    def test_the_line_accepts_a_fresh_upload_after_a_delete(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        _upload(hub, eid, criado["id"], nome="errado.pdf")
        hub.client.delete(f"{_base(hub, eid)}/{criado['id']}/documento", headers=AUTH)
        de_novo = _upload(hub, eid, criado["id"], nome="certo.pdf")
        assert de_novo.status_code == 200, de_novo.text
        assert de_novo.json()["documento"]["nome_original"] == "certo.pdf"
        assert de_novo.json()["concluido"] is True

    def test_delete_documento_appends_to_the_lgpd_access_log(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        _upload(hub, eid, criado["id"])
        hub.client.delete(f"{_base(hub, eid)}/{criado['id']}/documento", headers=AUTH)
        assert [a["acao"] for a in hub.rows(hub.cfg.tables.documento_acessos)] == ["delete"]

    def test_delete_documento_on_an_empty_line_is_a_no_op(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        resp = hub.client.delete(f"{_base(hub, eid)}/{criado['id']}/documento", headers=AUTH)
        assert resp.status_code == 204, resp.text
        assert len(_listar(hub, eid)) == 1

    def test_removing_the_line_does_not_delete_the_document(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        _upload(hub, eid, criado["id"])
        hub.client.delete(f"{_base(hub, eid)}/{criado['id']}", headers=AUTH)
        assert hub.rows(hub.cfg.tables.documentos)[0]["deleted_at"] is None

    def test_replace_survives_a_previous_document_already_swept(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        primeiro = _upload(hub, eid, criado["id"], nome="antigo.pdf").json()
        hub.db.table(hub.cfg.tables.documentos).update({"deleted_at": "2026-04-01T00:00:00+00:00"}).eq(
            "id", primeiro["documento"]["id"]
        ).execute()
        resp = _upload(hub, eid, criado["id"], nome="novo.pdf")
        assert resp.status_code == 200, resp.text
        assert resp.json()["documento"]["nome_original"] == "novo.pdf"
        assert resp.json()["concluido"] is True

    def test_delete_survives_a_document_already_swept(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        enviado = _upload(hub, eid, criado["id"]).json()
        hub.db.table(hub.cfg.tables.documentos).update({"deleted_at": "2026-04-01T00:00:00+00:00"}).eq(
            "id", enviado["documento"]["id"]
        ).execute()
        resp = hub.client.delete(f"{_base(hub, eid)}/{criado['id']}/documento", headers=AUTH)
        assert resp.status_code == 204, resp.text
        stored = hub.rows(hub.cfg.tables.checklist_extras)[0]
        assert stored["documento_id"] is None, "the dangling link must be cleared"
        assert stored["deleted_at"] is None, "the LINE survives"


class TestTipoMismatch:
    def test_texto_line_refuses_a_document_upload(self, hub):
        eid = _seed(hub)
        _seed_upload_catalogue(hub)
        criado = _criar(hub, eid, tipo="texto")
        resp = _upload(hub, eid, criado["id"])
        assert resp.status_code == 422, resp.text
        assert hub.rows(hub.cfg.tables.documentos) == []
        assert _listar(hub, eid)[0]["documento"] is None

    def test_arquivo_line_refuses_valor_texto(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        resp = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"valor_texto": "não deveria colar"}, headers=AUTH)
        assert resp.status_code == 422, resp.text
        assert _listar(hub, eid)[0]["valor_texto"] is None

    def test_arquivo_line_still_accepts_label_and_ordem(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid, tipo="arquivo")
        resp = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"label": "Certidão", "ordem": 2}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "Certidão"

    def test_unknown_tipo_is_rejected_at_the_boundary(self, hub):
        eid = _seed(hub)
        resp = hub.client.post(_base(hub, eid), json={"label": "x", "tipo": "video"}, headers=AUTH)
        assert resp.status_code == 422, resp.text

    def test_tipo_cannot_be_changed_by_patch(self, hub):
        eid = _seed(hub)
        criado = _criar(hub, eid, tipo="texto")
        resp = hub.client.patch(f"{_base(hub, eid)}/{criado['id']}", json={"tipo": "arquivo"}, headers=AUTH)
        assert resp.status_code == 422, resp.text
