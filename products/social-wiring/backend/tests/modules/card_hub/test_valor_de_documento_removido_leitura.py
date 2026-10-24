"""Read-time backstop for values whose source document was removed.

The delete hook (F80) only reverts what a delete through it touches; a value
pointing at a soft-deleted / discarded document by any other path must not be
trusted when read: the checklist shows it pending ("documento removido"), the
contract readiness lists a falta, and a CONFIRMED value or one another live
document still states is kept. Every value below is invented.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import documento_checklist_service as checklist
from app.modules.card_hub import identidade_extracao_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row, documento_row

ORG_UUID = UUID(ORG_ID)
REMOVIDO = "2026-10-20T00:00:00+00:00"


def _seed(scoped, *, doc_extra=None, outro_doc=None, **cliente):
    cid, did = str(uuid4()), str(uuid4())
    base = dict(
        estado_civil="casado",
        estado_civil_origem="certidao_casamento",
        estado_civil_documento_id=did,
        estado_civil_em="2026-10-01T00:00:00+00:00",
    )
    base.update(cliente)
    scoped.set_table_data("clientes", [cliente_row(cid, **base)])
    docs = [documento_row(
        did, cid, tipo_documento="certidao_casamento",
        extracao_estado_civil="casado",
        **{"deleted_at": REMOVIDO, "extracao_descartada_em": None, **(doc_extra or {})},
    )]
    if outro_doc:
        docs.append(documento_row(str(uuid4()), cid, extracao_descartada_em=None, **outro_doc))
    scoped.set_table_data("cliente_documentos", docs)
    return cid, did


class TestSanearProveniencia:
    def test_machine_value_of_a_deleted_document_is_withheld(self, client, scoped):
        cid, _ = _seed(scoped)
        row = svc.sanear_proveniencia(scoped, ORG_UUID, UUID(cid), _row(scoped, cid))
        assert row["estado_civil"] is None
        assert row["estado_civil_origem"] is None
        assert row["estado_civil_documento_id"] is None
        assert row[svc.CHAVE_DOCUMENTO_REMOVIDO] == ["estado_civil"]

    def test_a_discarded_extraction_is_withheld_too(self, client, scoped):
        cid, _ = _seed(scoped, doc_extra={"deleted_at": None, "extracao_descartada_em": REMOVIDO})
        row = svc.sanear_proveniencia(scoped, ORG_UUID, UUID(cid), _row(scoped, cid))
        assert row["estado_civil"] is None

    def test_a_confirmed_value_is_kept(self, client, scoped):
        cid, _ = _seed(scoped, estado_civil_confirmado_em="2026-10-02T00:00:00+00:00")
        row = svc.sanear_proveniencia(scoped, ORG_UUID, UUID(cid), _row(scoped, cid))
        assert row["estado_civil"] == "casado"
        assert svc.CHAVE_DOCUMENTO_REMOVIDO not in row

    def test_a_manual_value_is_kept(self, client, scoped):
        cid, _ = _seed(scoped, estado_civil_origem="manual")
        row = svc.sanear_proveniencia(scoped, ORG_UUID, UUID(cid), _row(scoped, cid))
        assert row["estado_civil"] == "casado"

    def test_another_live_document_with_the_same_value_keeps_it_and_provenance_moves(
        self, client, scoped
    ):
        cid, did = _seed(scoped, outro_doc={
            "tipo_documento": "certidao_casamento", "extracao_estado_civil": "casado",
        })
        row = svc.sanear_proveniencia(scoped, ORG_UUID, UUID(cid), _row(scoped, cid))
        assert row["estado_civil"] == "casado"
        assert row["estado_civil_documento_id"] != did
        assert svc.CHAVE_DOCUMENTO_REMOVIDO not in row

    def test_every_group_goes_through_the_one_helper_endereco_included(self, client, scoped):
        cid, did = _seed(scoped)
        scoped.set_table_data("clientes", [cliente_row(
            cid, estado_civil="casado", estado_civil_origem="certidao_casamento",
            estado_civil_documento_id=did, rg="1234567", rg_origem="cnh",
            rg_documento_id=did, endereco_logradouro="Rua Ficticia",
            endereco_cidade="Sao Paulo", endereco_origem="comprovante_endereco",
            endereco_documento_id=did,
        )])
        row = svc.sanear_proveniencia(scoped, ORG_UUID, UUID(cid), _row(scoped, cid))
        assert set(row[svc.CHAVE_DOCUMENTO_REMOVIDO]) == {"estado_civil", "rg", "endereco"}
        assert row["rg"] is None and row["endereco_logradouro"] is None


class TestLeituras:
    def test_checklist_marks_the_item_pending_with_a_note(self, client, scoped):
        cid, _ = _seed(scoped)
        scoped.set_table_data("documento_checklist", [])
        resultado = checklist.listar(scoped, ORG_UUID, UUID(cid))
        assert resultado["documento_removido"] == ["estado_civil"]
        assert (resultado["valores"] or {}).get("estado_civil") in (None, "")

    def test_contract_qualification_emits_a_falta_instead_of_the_value(self, client, scoped):
        cid, _ = _seed(scoped)
        completude = checklist.completude_contratual(scoped, ORG_UUID, UUID(cid))
        assert completude["estado_civil"] is None
        assert "estado_civil" in completude["faltando"]

    def test_confirmed_value_still_counts_for_the_contract(self, client, scoped):
        cid, _ = _seed(scoped, estado_civil_confirmado_em="2026-10-02T00:00:00+00:00")
        completude = checklist.completude_contratual(scoped, ORG_UUID, UUID(cid))
        assert completude["estado_civil"] == "casado"


def _row(scoped, cid):
    return next(
        r for r in scoped.table("clientes").select("*").execute().data if r["id"] == cid
    )
