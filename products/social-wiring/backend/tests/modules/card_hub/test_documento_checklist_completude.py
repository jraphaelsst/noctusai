"""`documento_checklist_service.completude_contratual` (migration 110).

WHAT THESE TESTS PIN
---------------------
1. **A stricter question than the Documentos checklist.** `nome_oficial`
   specifically — a channel-supplied `nome` that satisfies the checklist's
   "Nome Completo" item does NOT satisfy this.
2. **`regime_bens` is required only for a married party** (CC art. 1.647),
   and only THEN.
3. **A married party needs a linked cônjuge who is ALSO qualified** — a
   spouse link alone is not enough.
4. **Legacy free-text `estado_civil` values are read through the seed's
   closed vocabulary** without ever being rewritten in the database.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import documento_checklist_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

ORG_UUID = UUID(ORG_ID)


def _qualificado(cliente_id, **overrides) -> dict:
    """A fully contract-qualified pessoa física, `estado_civil="solteiro"`
    so no cônjuge is pulled in unless a test asks for one."""
    base = cliente_row(
        cliente_id,
        nome_oficial="Ana Maria da Silva",
        nacionalidade="brasileira",
        profissao="Engenheira",
        estado_civil="solteiro",
        regime_bens=None,
        cpf="412.954.238-98",
        rg="52.179.965-X",
        rg_orgao_expedidor="SSP/SP",
        endereco_logradouro="Rua das Flores",
        endereco_numero="123",
        endereco_bairro="Centro",
        endereco_cidade="São Paulo",
        endereco_uf="SP",
        endereco_cep="01310-100",
        conjuge_cliente_id=None,
    )
    base.update(overrides)
    return base


class TestCamposObrigatoriosDaPessoa:
    def test_a_fully_qualified_solteiro_is_complete(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [_qualificado(cid)])
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["completo"] is True
        assert out["faltando"] == []
        assert out["conjuge"] is None

    def test_a_blank_client_is_missing_everything_asked(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["completo"] is False
        for campo in (
            "nome_oficial", "nacionalidade", "profissao", "estado_civil",
            "rg", "rg_orgao_expedidor", "cpf", "endereco",
        ):
            assert campo in out["faltando"], campo

    def test_a_channel_supplied_nome_does_not_satisfy_nome_oficial(
        self, client, scoped
    ):
        """The Documentos checklist's 2026-08-24 ruling ("nome" counts for
        "Nome Completo") is deliberately NOT inherited here — a contract
        prints the document name."""
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(cid, nome="Ana", nome_completo=None, nome_oficial=None)],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "nome_oficial" in out["faltando"]

    def test_endereco_is_missing_when_any_required_part_is_absent(
        self, client, scoped
    ):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes", [_qualificado(cid, endereco_cep=None)]
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "endereco" in out["faltando"]

    def test_endereco_complemento_is_not_required(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes", [_qualificado(cid, endereco_complemento=None)]
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "endereco" not in out["faltando"]


class TestRegimeDeBensSoQuandoCasado:
    def test_solteiro_does_not_need_regime_bens(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes", [_qualificado(cid, estado_civil="solteiro")]
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "regime_bens" not in out["faltando"]

    def test_casado_without_regime_bens_is_incomplete(self, client, scoped):
        esposa = str(uuid4())
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [
                _qualificado(
                    cid, estado_civil="casado", regime_bens=None,
                    conjuge_cliente_id=esposa,
                ),
                _qualificado(esposa, estado_civil="casado", regime_bens="comunhao_parcial",
                             conjuge_cliente_id=cid),
            ],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "regime_bens" in out["faltando"]

    def test_uniao_estavel_also_requires_regime_bens(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(cid, estado_civil="uniao_estavel", regime_bens=None)],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "regime_bens" in out["faltando"]


class TestConjugeExigidoQuandoCasado:
    def test_casado_with_no_conjuge_linked_is_incomplete(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(
                cid, estado_civil="casado", regime_bens="comunhao_parcial",
                conjuge_cliente_id=None,
            )],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "conjuge" in out["faltando"]
        assert out["conjuge"] is None

    def test_casado_with_an_unqualified_conjuge_is_incomplete(self, client, scoped):
        cid, esposa = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes",
            [
                _qualificado(
                    cid, estado_civil="casado", regime_bens="comunhao_parcial",
                    conjuge_cliente_id=esposa,
                ),
                # The spouse exists and is linked, but has nothing filled in.
                cliente_row(esposa, estado_civil="casado", conjuge_cliente_id=cid),
            ],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["completo"] is False
        assert "conjuge_qualificacao" in out["faltando"]
        assert out["conjuge"]["completo"] is False
        assert "nome_oficial" in out["conjuge"]["faltando"]

    def test_casado_with_a_fully_qualified_conjuge_is_complete(self, client, scoped):
        cid, esposa = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes",
            [
                _qualificado(
                    cid, estado_civil="casado", regime_bens="comunhao_parcial",
                    conjuge_cliente_id=esposa, data_casamento="2010-03-12",
                ),
                _qualificado(
                    esposa, estado_civil="casado", regime_bens="comunhao_parcial",
                    conjuge_cliente_id=cid, nome_oficial="Maria da Silva",
                    cpf="123.456.789-09", data_casamento="2010-03-12",
                ),
            ],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["completo"] is True
        assert out["faltando"] == []
        assert out["conjuge"]["completo"] is True
        assert out["conjuge"]["cliente_id"] == esposa

    def test_does_not_recurse_into_the_conjuges_own_conjuge(self, client, scoped):
        """Depth-one only — the pair is symmetric by construction, so a
        second level would just re-examine the ORIGINAL party."""
        cid, esposa = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "clientes",
            [
                _qualificado(
                    cid, estado_civil="casado", regime_bens="comunhao_parcial",
                    conjuge_cliente_id=esposa, data_casamento="2010-03-12",
                ),
                _qualificado(
                    esposa, estado_civil="casado", regime_bens="comunhao_parcial",
                    conjuge_cliente_id=cid, nome_oficial="Maria da Silva",
                    cpf="123.456.789-09", data_casamento="2010-03-12",
                ),
            ],
        )
        # No infinite recursion / no exception — this call completing at all
        # is the assertion.
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["conjuge"]["faltando"] == []


class TestEstadoCivilLegado:
    """`clientes.estado_civil` is unconstrained TEXT and `ClientePatchBody`
    accepts any string — an older UI may have written Title-case Portuguese
    rather than the extractor's closed snake_case vocabulary."""

    def test_legacy_title_case_is_recognised_as_married(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(cid, estado_civil="Casado(a)", regime_bens=None)],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["estado_civil"] == "casado"
        assert "regime_bens" in out["faltando"]
        assert "conjuge" in out["faltando"]

    def test_an_unrecognised_value_is_treated_as_not_stated(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes", [_qualificado(cid, estado_civil="???")]
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["estado_civil"] is None
        # Never a guess: an unrecognised value must not itself become the
        # reason the party looks incomplete beyond its own listed field.
        assert "conjuge" not in out["faltando"]

    def test_stored_value_is_never_rewritten(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(cid, estado_civil="Casado(a)", regime_bens=None)],
        )
        svc.completude_contratual(scoped, ORG_UUID, cid)
        row = scoped.table("clientes").select("*").execute().data[0]
        assert row["estado_civil"] == "Casado(a)"


class TestDataCasamentoExigidoQuandoCasado:
    """Migration 117 (contract F6). The office's Lei 6.515/77 citation needs
    the marriage date off a `casado` party — narrower than
    `_ESTADOS_QUE_EXIGEM_CONJUGE`: `uniao_estavel` has no "casamento" to
    date, so it is NOT required there."""

    def test_a_casado_party_with_no_data_casamento_is_missing_it(
        self, client, scoped
    ):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(
                cid, estado_civil="casado", regime_bens="comunhao_parcial",
                conjuge_cliente_id=None, data_casamento=None,
            )],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "data_casamento" in out["faltando"]

    def test_a_casado_party_with_data_casamento_does_not_list_it(
        self, client, scoped
    ):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(
                cid, estado_civil="casado", regime_bens="comunhao_parcial",
                conjuge_cliente_id=None, data_casamento="2010-03-12",
            )],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "data_casamento" not in out["faltando"]

    def test_uniao_estavel_does_not_require_data_casamento(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data(
            "clientes",
            [_qualificado(
                cid, estado_civil="uniao_estavel",
                regime_bens="comunhao_parcial", conjuge_cliente_id=None,
                data_casamento=None,
            )],
        )
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "data_casamento" not in out["faltando"]

    def test_a_solteiro_party_does_not_require_data_casamento(
        self, client, scoped
    ):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [_qualificado(cid)])
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert "data_casamento" not in out["faltando"]


class TestCertidaoEstadoCivilInResponse:
    """Migration 117. `completude_contratual` surfaces the office's
    90-day-freshness rule as data, never as a `faltando` gate — see
    `identidade_extracao_service.certidao_estado_civil_mais_recente`."""

    def test_none_when_no_certidao_has_a_recorded_emissao(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [_qualificado(cid)])
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["certidao_estado_civil"] is None

    def test_surfaces_the_documento_id_and_emitida_em_when_present(
        self, client, scoped
    ):
        cid = str(uuid4())
        did = str(uuid4())
        scoped.set_table_data("clientes", [_qualificado(cid)])
        scoped.set_table_data("cliente_documentos", [{
            "id": did, "org_id": ORG_ID, "cliente_id": cid,
            "tipo_documento": "certidao_casamento", "deleted_at": None,
            "extracao_descartada_em": None,
            "extracao_data_emissao": "2024-03-15",
        }])
        out = svc.completude_contratual(scoped, ORG_UUID, cid)
        assert out["certidao_estado_civil"]["documento_id"] == did
        assert out["certidao_estado_civil"]["emitida_em"] == "2024-03-15"
        assert isinstance(out["certidao_estado_civil"]["dias"], int)
