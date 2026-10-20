"""An RNE read from a CNH / RNE card is corroborated by the RNE already on file.

Prod deal 876 (2026-10-20): a foreigner's CNH printed her RNE; the read was
"uncorroborated, so not stored from the CNH" and the lower-authority ficha
kept the provenance. There is no public check digit for RNE/CRNM, so the
corroboration is the strict mask (`identificador.validar_rne`) PLUS agreement
with an RNE-shaped value another source already holds — fed to the seed trust
gate (`confianca.avaliar`) by `_confirmados_de_outro_documento`. Synthetic
numbers only.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import identidade_extracao_service as svc
from app.services import clientes_service
from noctusai_lib.integrations.documents import confianca
from noctusai_lib.integrations.documents.types import ExtractionConfidence, IdentityFields
from tests.modules.card_hub.conftest import cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import ORG_ID, ORG_UUID, _cliente, _conflitos

RNE = "V123456-7"
OUTRO_RNE = "V765432-1"


def _cliente_com(scoped, **extra) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Fulana Teste", **extra)])
    scoped.set_table_data("cliente_campo_conflitos", [])
    return cid


def _confirmados(scoped, cid, tipo="CNH"):
    return svc._confirmados_de_outro_documento(scoped, ORG_UUID, UUID(cid), tipo)


def _lidos(rne):
    base = svc._lidos_vazios()
    base["rg"] = (rne, "media", "RNE", True)
    return base


def _aplicar(scoped, cid, origem="cnh", rne=RNE, documento_id=None):
    return svc.aplicar_campos_ao_cliente(
        scoped, ORG_UUID, UUID(cid), origem, _lidos(rne),
        documento_id=documento_id or uuid4(),
    )


class TestConfirmadosFeedsTheGate:
    def test_an_rne_on_file_from_another_source_corroborates(self, client, scoped):
        cid = _cliente_com(scoped, rg=RNE, rg_origem="ficha_cadastral")
        assert _confirmados(scoped, cid)["rne"] == RNE

    def test_the_gate_marks_a_matching_cnh_rne_corroborated(self, client, scoped):
        cid = _cliente_com(scoped, rg=RNE, rg_origem="ficha_cadastral")
        fields = IdentityFields(rne="V123456-7", rne_confianca=ExtractionConfidence.BAIXA)
        v = confianca.avaliar(fields, "CNH", confirmados=_confirmados(scoped, cid))
        assert "corroborado_outro_documento" in v["rne"].motivos
        assert v["rne"].estado == confianca.CONFIAVEL
        assert confianca.calibrar(fields, v).rne_confianca is ExtractionConfidence.MEDIA

    def test_a_cnh_rne_alone_stays_uncorroborated(self, client, scoped):
        cid = _cliente_com(scoped)
        assert "rne" not in _confirmados(scoped, cid)
        fields = IdentityFields(rne=RNE, rne_confianca=ExtractionConfidence.BAIXA)
        v = confianca.avaliar(fields, "CNH", confirmados=_confirmados(scoped, cid))
        assert "corroborado_outro_documento" not in v["rne"].motivos

    def test_a_disagreeing_rne_is_flagged_not_corroborated(self, client, scoped):
        cid = _cliente_com(scoped, rg=OUTRO_RNE, rg_origem="ficha_cadastral")
        fields = IdentityFields(rne=RNE, rne_confianca=ExtractionConfidence.BAIXA)
        v = confianca.avaliar(fields, "CNH", confirmados=_confirmados(scoped, cid))
        assert "diverge_de_valor_confirmado" in v["rne"].motivos
        assert v["rne"].duvidoso

    def test_a_malformed_value_on_file_never_corroborates(self, client, scoped):
        cid = _cliente_com(scoped, rg="1234", rg_origem="ficha_cadastral")
        assert "rne" not in _confirmados(scoped, cid)

    def test_a_plain_rg_on_file_says_nothing_about_an_rne(self, client, scoped):
        cid = _cliente_com(scoped, rg="52.179.965-X", rg_origem="ficha_cadastral")
        assert "rne" not in _confirmados(scoped, cid)
        assert _confirmados(scoped, cid)["rg"] == "52.179.965-X"

    def test_a_malformed_rne_read_is_rejected_by_the_gate(self, client, scoped):
        cid = _cliente_com(scoped, rg=RNE, rg_origem="ficha_cadastral")
        fields = IdentityFields(rne="V12-3", rne_confianca=ExtractionConfidence.BAIXA)
        v = confianca.avaliar(fields, "CNH", confirmados=_confirmados(scoped, cid))
        assert "mascara_invalida" in v["rne"].motivos
        assert v["rne"].duvidoso

    def test_the_documents_own_origin_is_not_independent_evidence(self, client, scoped):
        cid = _cliente_com(scoped, rg=RNE, rg_origem="cnh")
        assert "rne" not in _confirmados(scoped, cid, tipo="cnh")

    def test_cpf_corroboration_is_unchanged(self, client, scoped):
        cid = _cliente_com(scoped, cpf="529.982.247-25", cpf_origem="ficha_cadastral")
        assert _confirmados(scoped, cid)["cpf"] == "529.982.247-25"


class TestApplyAfterCorroboration:
    def test_an_agreeing_cnh_rne_takes_the_provenance_without_a_conflict(self, client, scoped):
        cid = _cliente_com(scoped, rg=RNE, rg_origem="ficha_cadastral")
        doc = uuid4()
        _aplicar(scoped, cid, origem="cnh", documento_id=doc)
        row = _cliente(scoped, cid)
        assert (row["rg"], row["rg_origem"]) == (RNE, "cnh")
        assert row["rg_documento_id"] == str(doc)
        assert [c for c in _conflitos(scoped) if c["status"] == "pendente"] == []

    def test_a_disagreeing_cnh_rne_opens_a_conflict_and_overwrites_nothing(self, client, scoped):
        cid = _cliente_com(scoped, rg=OUTRO_RNE, rg_origem="ficha_cadastral")
        _, abertos = _aplicar(scoped, cid, origem="cnh")
        row = _cliente(scoped, cid)
        assert (row["rg"], row["rg_origem"]) == (OUTRO_RNE, "ficha_cadastral")
        [conflito] = [c for c in _conflitos(scoped) if c["status"] == "pendente"]
        assert abertos == [conflito]
        assert conflito["valor_proposto"] == RNE and conflito["origem_proposto"] == "cnh"

    def test_an_owner_corrected_rne_is_protected(self, client, scoped):
        cid = _cliente_com(scoped, rg=OUTRO_RNE, rg_origem="ficha_cadastral")
        clientes_service.update_cliente(
            scoped, ORG_UUID, UUID(cid), acting_user_id=uuid4(), is_admin=True, rg=RNE,
        )
        _, abertos = _aplicar(scoped, cid, origem="cnh", rne=OUTRO_RNE)
        row = _cliente(scoped, cid)
        assert (row["rg"], row["rg_origem"]) == (RNE, "manual")
        [conflito] = [c for c in _conflitos(scoped) if c["status"] == "pendente"]
        assert conflito["protege_correcao"] is True
