"""Confirming or discarding a low-confidence birthdate read (migration 069).

WHAT THESE TESTS PIN
--------------------
068 established that only a high-confidence read is written unattended, which
left low-confidence reads correct but invisible. These tests pin the decision
surface that makes them actionable WITHOUT letting them become facts by
default:

- a suggestion is offered only while the field is still unanswered;
- confirming records WHO vouched, separately from WHERE the value came from;
- discarding stops the prompt but keeps the evidence;
- a filled field cannot be overwritten by either path.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.card_hub import documento_checklist_service as checklist
from app.modules.card_hub import identidade_extracao_service as svc
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

ORG_UUID = UUID(ORG_ID)


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped, *, cliente=None, docs=()) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **(cliente or {}))])
    scoped.set_table_data("cliente_documento_checklist", [])
    scoped.set_table_data("cliente_documentos", [{**d, "cliente_id": cid} for d in docs])
    return cid


def _doc(**over) -> dict:
    base = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "nome_original": "rg.pdf",
        "tipo_documento": "rg",
        "deleted_at": None,
        "extracao_status": "ok",
        "extracao_data_nascimento": "1980-05-12",
        "extracao_confianca": "baixa",
        "extracao_fonte": "ocr",
        "extracao_rotulo": None,
        "extracao_em": "2026-08-22T10:00:00+00:00",
        "extracao_descartada_em": None,
        "extracao_descartada_por": None,
    }
    return {**base, **over}


def _cliente(scoped, cid) -> dict:
    return [r for r in scoped.table("clientes").select("*").execute().data
            if r["id"] == cid][0]


def _item(client, cid, key="data_nascimento") -> dict:
    body = client.get(f"/api/clientes/{cid}/documento-checklist", headers=_auth()).json()
    return {i["key"]: i for i in body["items"]}[key]


class TestWhenASuggestionIsOffered:
    def test_a_low_confidence_read_rides_on_its_checklist_item(self, client, scoped):
        """The checklist is already the "what is still missing" surface, so an
        answer to a missing item belongs next to the item."""
        d = _doc()
        cid = _seed(scoped, docs=[d])
        item = _item(client, cid)
        assert item["concluido"] is False
        assert item["sugestao"]["valor"] == "1980-05-12"
        assert item["sugestao"]["confianca"] == "baixa"
        assert item["sugestao"]["fonte"] == "ocr"
        assert item["sugestao"]["documento_nome"] == "rg.pdf"

    def test_no_suggestion_once_the_field_is_answered(self, client, scoped):
        """🔴 Continuing to ask would be asking a question already answered."""
        cid = _seed(
            scoped,
            cliente={"data_nascimento": "1975-11-03"},
            docs=[_doc()],
        )
        item = _item(client, cid)
        assert item["concluido"] is True
        assert item["sugestao"] is None

    def test_a_discarded_suggestion_is_not_offered_again(self, client, scoped):
        cid = _seed(
            scoped,
            docs=[_doc(extracao_descartada_em="2026-08-22T12:00:00+00:00")],
        )
        assert _item(client, cid)["sugestao"] is None

    def test_a_deleted_document_offers_nothing(self, client, scoped):
        cid = _seed(scoped, docs=[_doc(deleted_at="2026-08-22T12:00:00+00:00")])
        assert _item(client, cid)["sugestao"] is None

    def test_a_document_with_no_extracted_value_offers_nothing(self, client, scoped):
        cid = _seed(scoped, docs=[_doc(extracao_data_nascimento=None,
                                       extracao_status="sem_dados")])
        assert _item(client, cid)["sugestao"] is None

    def test_the_newest_read_is_offered_first(self, client, scoped):
        """🔴 Two documents disagreeing is exactly where showing both at once
        invites picking one quickly and wrongly. One at a time."""
        old = _doc(extracao_em="2026-08-01T10:00:00+00:00",
                   extracao_data_nascimento="1970-01-01", nome_original="antigo.pdf")
        new = _doc(extracao_em="2026-08-22T10:00:00+00:00",
                   extracao_data_nascimento="1980-05-12", nome_original="novo.pdf")
        cid = _seed(scoped, docs=[old, new])
        sug = _item(client, cid)["sugestao"]
        assert sug["documento_nome"] == "novo.pdf"
        assert sug["valor"] == "1980-05-12"

    def test_items_with_no_extractable_field_never_carry_one(self, client, scoped):
        cid = _seed(scoped, docs=[_doc()])
        body = client.get(
            f"/api/clientes/{cid}/documento-checklist", headers=_auth()
        ).json()
        for i in body["items"]:
            if i["key"] != "data_nascimento":
                assert i["sugestao"] is None


class TestConfirming:
    def test_confirming_applies_the_value_and_records_who_vouched(self, client, scoped):
        """🔴 Origin says WHERE it came from; confirmado_por says WHO took
        responsibility. One column answering both would answer neither."""
        d = _doc()
        cid = _seed(scoped, docs=[d])
        r = client.post(
            f"/api/clientes/{cid}/documentos/{d['id']}/extracao/confirmar",
            headers=_auth(),
        )
        assert r.status_code == 200, r.text

        c = _cliente(scoped, cid)
        assert c["data_nascimento"] == "1980-05-12"
        assert c["data_nascimento_origem"] == "rg", (
            "recorded as 'manual' — that erases the fact a scan produced it"
        )
        assert c["data_nascimento_documento_id"] == d["id"]
        assert c["data_nascimento_confirmado_por"] is not None
        assert c["data_nascimento_confirmado_em"] is not None

    def test_confirming_ticks_the_item_and_clears_the_prompt(self, client, scoped):
        d = _doc()
        cid = _seed(scoped, docs=[d])
        client.post(
            f"/api/clientes/{cid}/documentos/{d['id']}/extracao/confirmar",
            headers=_auth(),
        )
        item = _item(client, cid)
        assert item["concluido"] is True
        assert item["origem"] == "derivado", "no override was written — the DATA is there"
        assert item["sugestao"] is None

    def test_confirming_over_an_existing_value_is_refused(self, client, scoped):
        """Two operators on the same card otherwise race, and the loser
        silently overwrites the winner."""
        d = _doc()
        cid = _seed(scoped, cliente={"data_nascimento": "1975-11-03"}, docs=[d])
        with pytest.raises(ValidationError_):
            svc.confirmar_sugestao(scoped, ORG_UUID, UUID(cid), UUID(d["id"]))
        assert _cliente(scoped, cid)["data_nascimento"] == "1975-11-03"

    def test_confirming_a_document_with_nothing_extracted_is_refused(
        self, client, scoped
    ):
        d = _doc(extracao_data_nascimento=None)
        cid = _seed(scoped, docs=[d])
        with pytest.raises(ValidationError_):
            svc.confirmar_sugestao(scoped, ORG_UUID, UUID(cid), UUID(d["id"]))

    def test_confirming_an_already_discarded_suggestion_is_refused(self, client, scoped):
        d = _doc(extracao_descartada_em="2026-08-22T12:00:00+00:00")
        cid = _seed(scoped, docs=[d])
        with pytest.raises(ValidationError_):
            svc.confirmar_sugestao(scoped, ORG_UUID, UUID(cid), UUID(d["id"]))

    def test_another_clients_document_cannot_be_confirmed(self, client, scoped):
        """The document id alone must never be enough to write someone
        else's record."""
        d = _doc()
        cid = _seed(scoped, docs=[d])
        with pytest.raises(NotFoundError):
            svc.confirmar_sugestao(scoped, ORG_UUID, uuid4(), UUID(d["id"]))


class TestDiscarding:
    def test_discarding_stops_the_prompt(self, client, scoped):
        d = _doc()
        cid = _seed(scoped, docs=[d])
        r = client.post(
            f"/api/clientes/{cid}/documentos/{d['id']}/extracao/descartar",
            headers=_auth(),
        )
        assert r.status_code == 200, r.text
        assert _item(client, cid)["sugestao"] is None

    def test_discarding_keeps_the_extracted_value(self, client, scoped):
        """🔴 Erasing it would destroy the only evidence that distinguishes a
        bad OCR pass from a bad decision about a good one."""
        d = _doc()
        cid = _seed(scoped, docs=[d])
        client.post(
            f"/api/clientes/{cid}/documentos/{d['id']}/extracao/descartar",
            headers=_auth(),
        )
        row = [r for r in scoped.table("cliente_documentos").select("*").execute().data
               if r["id"] == d["id"]][0]
        assert row["extracao_data_nascimento"] == "1980-05-12"
        assert row["extracao_descartada_em"] is not None
        assert row["extracao_descartada_por"] is not None

    def test_discarding_never_touches_the_client(self, client, scoped):
        d = _doc()
        cid = _seed(scoped, docs=[d])
        client.post(
            f"/api/clientes/{cid}/documentos/{d['id']}/extracao/descartar",
            headers=_auth(),
        )
        assert _cliente(scoped, cid).get("data_nascimento") is None

    def test_discarding_the_newest_reveals_the_next(self, client, scoped):
        """One decision at a time, by design."""
        old = _doc(extracao_em="2026-08-01T10:00:00+00:00",
                   extracao_data_nascimento="1970-01-01", nome_original="antigo.pdf")
        new = _doc(extracao_em="2026-08-22T10:00:00+00:00", nome_original="novo.pdf")
        cid = _seed(scoped, docs=[old, new])
        client.post(
            f"/api/clientes/{cid}/documentos/{new['id']}/extracao/descartar",
            headers=_auth(),
        )
        sug = _item(client, cid)["sugestao"]
        assert sug is not None
        assert sug["documento_nome"] == "antigo.pdf"

    def test_another_clients_document_cannot_be_discarded(self, client, scoped):
        d = _doc()
        _seed(scoped, docs=[d])
        with pytest.raises(NotFoundError):
            svc.descartar_sugestao(scoped, ORG_UUID, uuid4(), UUID(d["id"]))


class TestHighConfidenceNeverBecomesAPrompt:
    def test_an_applied_high_confidence_read_asks_nothing(self, client, scoped):
        """It is already a fact on the record; there is nothing to decide."""
        d = _doc(extracao_confianca="alta", extracao_fonte="texto",
                 extracao_rotulo="DATA DE NASCIMENTO")
        cid = _seed(
            scoped,
            cliente={"data_nascimento": "1980-05-12", "data_nascimento_origem": "rg"},
            docs=[d],
        )
        item = _item(client, cid)
        assert item["concluido"] is True
        assert item["sugestao"] is None
