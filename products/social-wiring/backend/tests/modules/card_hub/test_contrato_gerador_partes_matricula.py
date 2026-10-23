"""F36/F38 — the matrícula decides who may SELL and who must CONSENT.

A 'proprietário' the matrícula does not name blocks the contract (a non-owner
selling is a legal defect) and the readiness names the papel they likely hold;
a DOADOR of a doação into the sellers (adiantamento de legítima) is worded as
an anuente. Synthetic names/CPFs only.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from app.modules.card_hub.contrato_gerador import derivacao
from app.modules.card_hub.contrato_gerador.dados import TitularMatricula
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.test_contrato_gerador_partes_clausulas import (
    _avaliar,
    _codigos,
    _texto,
)


def _com_matricula(d, donos, *, natureza="compra_e_venda", transmitentes=()):
    imovel = replace(
        d.imovel,
        proprietarios_matricula=tuple(donos),
        titulo_natureza=natureza,
        transmitentes_titulo=tuple(transmitentes),
    )
    return replace(d, imovel=imovel)


def _titular(p):
    return TitularMatricula(nome=p.nome, documento=p.cpf)


class TestVendedorNaoProprietario:
    def test_owner_known_and_seller_among_them_passes(self):
        d = fx.variante(1)
        d = _com_matricula(d, [_titular(d.vendedores[0])])
        assert "VENDEDOR_NAO_PROPRIETARIO" not in _codigos(_avaliar(1, d).bloqueios)

    def test_owners_unknown_checks_nothing(self):
        d = fx.variante(1)
        assert d.imovel.proprietarios_matricula == ()
        assert "VENDEDOR_NAO_PROPRIETARIO" not in _codigos(_avaliar(1, d).bloqueios)

    def test_name_match_ignores_accents_case_and_particles(self):
        d = fx.variante(1)
        dono = TitularMatricula(nome="FÚLANO  tal", documento=None)  # no 'de', accent, case
        d = _com_matricula(d, [dono])
        assert "VENDEDOR_NAO_PROPRIETARIO" not in _codigos(_avaliar(1, d).bloqueios)

    def test_different_cpf_is_a_different_person_whatever_the_name(self):
        d = fx.variante(1)
        outro_cpf = fx.cpf_sintetico("555666777")
        d = _com_matricula(d, [TitularMatricula(nome=d.vendedores[0].nome, documento=outro_cpf)])
        assert "VENDEDOR_NAO_PROPRIETARIO" in _codigos(_avaliar(1, d).bloqueios)

    def test_non_owner_typed_proprietario_blocks_and_suggests_conjuge_anuente(self):
        d = fx.variante(1)
        v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial",
                     conjuge_cliente_id="v2", data_casamento=date(2000, 6, 10))
        v2 = replace(
            fx.pessoa("v2", "vendedor", "proprietario", "Nora Exemplo", "Feminino", "111222333",
                      "55.555.555-5"),
            estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="v1",
            data_casamento=date(2000, 6, 10),
        )
        d = replace(d, vendedores=[v1, v2])
        d = _com_matricula(d, [_titular(v1)])
        bloqueios = _avaliar(1, d).bloqueios
        msg = next(b["mensagem"] for b in bloqueios if b["codigo"] == "VENDEDOR_NAO_PROPRIETARIO")
        assert "Nora Exemplo" in msg and "anuente (cônjuge" in msg

    def test_non_owner_who_is_a_donor_in_the_chain_suggests_anuente_doador(self):
        d = fx.variante(1)
        mae = fx.pessoa("m1", "vendedor", "proprietario", "Matriarca Exemplo", "Feminino", "222333444",
                        "66.666.666-6")
        d = replace(d, vendedores=[d.vendedores[0], mae])
        d = _com_matricula(
            d, [_titular(d.vendedores[0])], natureza="doacao", transmitentes=[_titular(mae)]
        )
        msg = next(
            b["mensagem"] for b in _avaliar(1, d).bloqueios if b["codigo"] == "VENDEDOR_NAO_PROPRIETARIO"
        )
        assert "doador(a)" in msg and "anuente (doador" in msg


class TestAnuenteDoador:
    def _deal(self, *, natureza="doacao"):
        d = fx.variante(1)
        pai = fx.pessoa("d1", "vendedor", "anuente", "Patriarca Exemplo", "Masculino", "333444555",
                        "77.777.777-7", certidoes=[])
        mae = fx.pessoa("d2", "vendedor", "anuente", "Matriarca Exemplo", "Feminino", "444555666",
                        "88.888.888-8", certidoes=[])
        d = replace(d, vendedores=[d.vendedores[0], pai, mae])
        return _com_matricula(
            d, [_titular(d.vendedores[0])], natureza=natureza,
            transmitentes=[_titular(pai), _titular(mae)],
        )

    def test_doadores_are_anuentes_with_their_own_wording_and_no_block(self):
        d = self._deal()
        av = _avaliar(1, d)
        assert "ANUENTE_SEM_REDACAO" not in _codigos(av.bloqueios)
        assert "VENDEDOR_NAO_PROPRIETARIO" not in _codigos(av.bloqueios)
        texto = _texto(1, d)
        assert "PATRIARCA EXEMPLO, brasileiro" in texto
        assert "doador do imóvel objeto deste contrato, que comparece neste ato para anuir" in texto
        assert "doadora do imóvel objeto deste contrato" in texto
        assert 'denominados neste ato simplesmente "ANUENTES"' in texto
        # an anuente is never a certificando
        assert "Em nome de PATRIARCA EXEMPLO" not in texto

    def test_same_people_without_a_doacao_in_the_chain_still_block(self):
        d = self._deal(natureza="compra_e_venda")
        assert "ANUENTE_SEM_REDACAO" in _codigos(_avaliar(1, d).bloqueios)

    def test_a_stranger_anuente_is_not_a_doador(self):
        d = self._deal()
        estranho = fx.pessoa("x9", "vendedor", "anuente", "Pessoa Estranha", "Masculino", "999888777",
                             "99.999.999-9", certidoes=[])
        d = replace(d, vendedores=d.vendedores + [estranho])
        av = _avaliar(1, d)
        assert "ANUENTE_SEM_REDACAO" in _codigos(av.bloqueios)
        assert derivacao.doador_anuente(d, estranho) is False

    def test_spouse_anuente_of_a_seller_keeps_its_existing_wording_beside_doadores(self):
        d = self._deal()
        v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial",
                     conjuge_cliente_id="an1", data_casamento=date(2000, 6, 10))
        nora = replace(
            fx.pessoa("an1", "vendedor", "anuente", "Nora Anuente", "Feminino", "111222333",
                      "55.555.555-5", certidoes=[]),
            estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="v1",
            data_casamento=date(2000, 6, 10),
        )
        d = replace(d, vendedores=[v1, *d.vendedores[1:], nora])
        texto = _texto(1, d)
        assert "com FULANO DE TAL, já qualificado anteriormente" in texto
        assert "doador do imóvel objeto deste contrato" in texto
