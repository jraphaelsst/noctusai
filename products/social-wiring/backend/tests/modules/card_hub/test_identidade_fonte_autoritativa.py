"""Source precedence for machine values (owner rule 2026-10-14, prod deal 876).

On 876 the ficha cadastral was read BEFORE the certidão de casamento, so
estado_civil / regime_bens / nacionalidade were stored with origem
`ficha_cadastral`; the certidão then read the SAME values and nothing moved.
The owner's definition of done is "the correct value, extracted from the
correct document" — so the source matters. The table is the seed's
`autoridade.PRECEDENCIA`; the rule lives in `aplicar_campos_ao_cliente`.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import identidade_extracao_service as svc
from tests.modules.card_hub.conftest import cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import ORG_UUID, _cliente, _conflitos

NOME = "MARIA APARECIDA SOUZA"
CASAL = ("estado_civil", "regime_bens", "nacionalidade")


def _lidos(**campos):
    base = svc._lidos_vazios()
    base.update({k: (v, "alta", "ROTULO", True) for k, v in campos.items()})
    return base


def _aplicar(db, cid, origem, documento_id, **campos):
    return svc.aplicar_campos_ao_cliente(
        db, ORG_UUID, UUID(cid), origem, _lidos(nome_oficial=NOME, **campos),
        documento_id=documento_id, ligar_pessoa=True,
    )


def _novo_cliente(scoped, **extra) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome=NOME, nome_oficial=NOME, **extra)])
    scoped.set_table_data("cliente_campo_conflitos", [])
    return cid


def _pendentes(scoped) -> list[dict]:
    return [c for c in _conflitos(scoped) if c.get("status") == "pendente"]


CASAL_876 = dict(estado_civil="casado", regime_bens="comunhão parcial de bens", nacionalidade="brasileira")


class TestDeal876:
    def test_ficha_first_then_certidao_same_values_hands_the_source_over(self, client, scoped):
        cid = _novo_cliente(scoped)
        ficha, certidao = uuid4(), uuid4()
        _aplicar(scoped, cid, "ficha_cadastral", ficha, **CASAL_876)
        row = _cliente(scoped, cid)
        assert all(row[f"{c}_origem"] == "ficha_cadastral" for c in CASAL)

        _, abertos = _aplicar(scoped, cid, "certidao_casamento", certidao, **CASAL_876)

        row = _cliente(scoped, cid)
        assert abertos == []
        assert _pendentes(scoped) == []
        for campo in CASAL:
            assert row[campo] == CASAL_876[campo]
            assert row[f"{campo}_origem"] == "certidao_casamento"
            assert row[f"{campo}_documento_id"] == str(certidao)
            assert row[f"{campo}_em"] is not None
            assert row.get(f"{campo}_confirmado_em") is None
        auditoria = [c for c in _conflitos(scoped) if c.get("status") == "resolvido_automatico"]
        assert {c["campo"] for c in auditoria} == set(CASAL)
        assert all(svc.REGRA_FONTE_AUTORITATIVA in c["motivo_resolucao"] for c in auditoria)

    def test_a_different_value_opens_a_pending_conflict_never_overwrites(self, client, scoped):
        cid = _novo_cliente(scoped)
        _aplicar(scoped, cid, "ficha_cadastral", uuid4(), estado_civil="solteiro")

        _, abertos = _aplicar(scoped, cid, "certidao_casamento", uuid4(), estado_civil="casado")

        row = _cliente(scoped, cid)
        assert row["estado_civil"] == "solteiro"
        assert row["estado_civil_origem"] == "ficha_cadastral"
        pendentes = _pendentes(scoped)
        assert len(pendentes) == 1 and len(abertos) == 1
        assert pendentes[0]["campo"] == "estado_civil"
        assert pendentes[0]["valor_proposto"] == "casado"
        assert pendentes[0]["origem_proposto"] == "certidao_casamento"

    def test_a_manual_value_is_never_touched(self, client, scoped):
        cid = _novo_cliente(scoped, estado_civil="casado", estado_civil_origem="manual")

        _, abertos = _aplicar(scoped, cid, "certidao_casamento", uuid4(), estado_civil="casado")

        row = _cliente(scoped, cid)
        assert row["estado_civil_origem"] == "manual"
        assert abertos == [] and _conflitos(scoped) == []

    def test_a_confirmed_machine_value_is_never_touched(self, client, scoped):
        doc = str(uuid4())
        cid = _novo_cliente(
            scoped, estado_civil="casado", estado_civil_origem="ficha_cadastral",
            estado_civil_documento_id=doc, estado_civil_confirmado_por=str(uuid4()),
            estado_civil_confirmado_em="2026-10-01T00:00:00+00:00",
        )

        _aplicar(scoped, cid, "certidao_casamento", uuid4(), estado_civil="casado")

        row = _cliente(scoped, cid)
        assert row["estado_civil_origem"] == "ficha_cadastral"
        assert row["estado_civil_documento_id"] == doc
        assert _conflitos(scoped) == []

    def test_reverse_order_certidao_first_then_ficha_keeps_the_certidao(self, client, scoped):
        cid = _novo_cliente(scoped)
        certidao = uuid4()
        _aplicar(scoped, cid, "certidao_casamento", certidao, **CASAL_876)

        _, abertos = _aplicar(scoped, cid, "ficha_cadastral", uuid4(), **CASAL_876)

        row = _cliente(scoped, cid)
        assert abertos == [] and _conflitos(scoped) == []
        for campo in CASAL:
            assert row[f"{campo}_origem"] == "certidao_casamento"
            assert row[f"{campo}_documento_id"] == str(certidao)


class TestEnderecoConsistente:
    def test_the_address_declaration_set_is_the_precedence_top_tier(self):
        assert svc.ORIGENS_ENDERECO_DECLARADO == frozenset({"ficha_cadastral"})
        assert svc.ORIGENS_ENDERECO_COMPROVANTE
        assert svc.ORIGENS_ENDERECO_DECLARADO.isdisjoint(svc.ORIGENS_ENDERECO_COMPROVANTE)
