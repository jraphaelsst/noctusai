"""Owner decisions 2026-10-05 on the contract gate: (A) previous owners —
their companies certified like the sellers', a per-deal dispensation that
becomes an `aviso` (never a silent skip), `destino` pointing at the Certidões
tab's antigos subtab; (B) an ANUENTE spouse is never certified, nor are their
companies. Every name / CPF / CNPJ is synthetic."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from app.modules.card_hub.contrato_gerador import derivacao
from tests.modules.card_hub import contrato_gerador_fixtures as fx

CNPJ_A = "11444777000161"
CNPJ_B = "45723174000110"
RECENTE = date(2021, 9, 15)  # < 5 years before fx.ASSINATURA
ANTIGA = date(2021, 9, 14)   # exactly 5 years: not required


def _avaliar(d):
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _codigos(itens):
    return {i["codigo"] for i in itens}


def _campos(av):
    return {f["campo"] for f in av.faltando}


def _card(quando, *antigos, empresas=(), **extra):
    d = fx.variante(1)
    return replace(
        d, imovel=replace(d.imovel, ultima_transferencia_em=quando),
        vendedores=d.vendedores + list(antigos), empresas=list(empresas), **extra,
    )


def _empresa_sem_certidoes(dono, cnpj=CNPJ_A, situacao="ativa", data_situacao=None):
    e = fx.empresa("e1", cnpj, "Empresa Exemplo Ltda", situacao, data_situacao, owners=[dono])
    return replace(e, certidoes=[])


class TestEmpresasDosAntigos:
    def test_company_of_a_previous_owner_is_certified_like_a_sellers(self):
        antigo = fx.antiga_proprietaria()
        av = _avaliar(_card(RECENTE, antigo, empresas=[_empresa_sem_certidoes(antigo)]))
        faltas = [f for f in av.faltando if f["campo"].startswith("certidao.") and f["parte_id"] == antigo.parte_id]
        # the 11 CNPJ certidões of the company + the 12 CPF ones are NOT the
        # same group: the company's are reported against the antigo's parte
        assert any("Empresa Exemplo Ltda" in f["rotulo"] for f in faltas)
        assert all(f["onde"] == "antigos_proprietarios" for f in faltas)
        assert all(f["destino"]["alvo"] == derivacao.ALVO_ANTIGOS_PROPRIETARIOS for f in faltas)

    def test_same_baixada_rule_as_the_sellers(self):
        antigo = fx.antiga_proprietaria()
        recente = _empresa_sem_certidoes(antigo, situacao="baixada", data_situacao=date(2024, 1, 10))
        velha = _empresa_sem_certidoes(antigo, situacao="baixada", data_situacao=date(2015, 1, 10))
        assert any("Empresa Exemplo" in f["rotulo"] for f in _avaliar(_card(RECENTE, antigo, empresas=[recente])).faltando)
        assert not any("Empresa Exemplo" in f["rotulo"] for f in _avaliar(_card(RECENTE, antigo, empresas=[velha])).faltando)

    def test_companies_of_antigos_are_not_asked_when_the_antigos_are_not_required(self):
        antigo = fx.antiga_proprietaria()
        av = _avaliar(_card(ANTIGA, antigo, empresas=[_empresa_sem_certidoes(antigo)]))
        assert not any("Empresa Exemplo" in f["rotulo"] for f in av.faltando)
        assert "ANTIGO_PROPRIETARIO_DISPENSADO" in _codigos(av.avisos)


class TestDispensa:
    def test_missing_group_is_a_falta_pointing_at_the_antigos_subtab(self):
        av = _avaliar(_card(RECENTE))
        falta = next(f for f in av.faltando if f["campo"] == "partes.antigo_proprietario")
        assert falta["onde"] == "antigos_proprietarios"
        assert falta["destino"]["tela"] == "card_certidoes"
        assert falta["destino"]["ancora"] == "certidoes"
        assert falta["destino"]["alvo"] == "certidoes-subtab-antigo_proprietario"

    def test_dispensed_deal_turns_the_falta_into_an_aviso(self):
        av = _avaliar(_card(RECENTE, antigos_dispensados=True))
        assert "partes.antigo_proprietario" not in _campos(av)
        assert "ANTIGO_PROPRIETARIO_DISPENSADO_NO_NEGOCIO" in _codigos(av.avisos)
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_dispensed_antigos_never_enter_the_instrument_or_the_gate(self):
        antigo = replace(fx.antiga_proprietaria(), certidoes=[])
        d = _card(RECENTE, antigo, antigos_dispensados=True)
        av = _avaliar(d)
        assert not any(f["parte_id"] == antigo.parte_id for f in av.faltando)
        assert not derivacao.antigos_no_contrato(d, fx.ASSINATURA, fx.politica_variante(1))

    def test_five_years_or_more_asks_nothing(self):
        av = _avaliar(_card(ANTIGA))
        assert "partes.antigo_proprietario" not in _campos(av)
        assert av.pronto, (av.faltando, av.bloqueios)


class TestAnuenteNaoCertifica:
    def _anuente(self, **extra):
        d = fx.variante(1)
        v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial",
                     conjuge_cliente_id="an1", data_casamento=date(2000, 6, 10))
        a = replace(
            fx.pessoa("an1", "vendedor", "anuente", "Cicrana Anuente", "Feminino", "111222333", "55.555.555-5"),
            estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="v1",
            data_casamento=date(2000, 6, 10), certidoes=[], **extra,
        )
        return replace(d, vendedores=[v1, a])

    def test_anuente_has_no_certidoes_required(self):
        av = _avaliar(self._anuente())
        assert not any(f["parte_id"] == "parte-an1" and f["campo"].startswith("certidao.") for f in av.faltando)
        assert derivacao.pessoas_certificadas(
            self._anuente(), {"tem_permuta": False}, fx.ASSINATURA, fx.politica_variante(1)
        ) == [self._anuente().vendedores[0]]

    def test_anuentes_company_is_not_certified_but_the_sellers_is(self):
        d = self._anuente()
        v1, an1 = d.vendedores
        da_anuente = _empresa_sem_certidoes(an1, cnpj=CNPJ_A)
        da_anuente = replace(da_anuente, id="e-anu")
        do_vendedor = replace(_empresa_sem_certidoes(v1, cnpj=CNPJ_B), id="e-vend", razao_social="Empresa Do Vendedor")
        av = _avaliar(replace(d, empresas=[da_anuente, do_vendedor]))
        rotulos = " ".join(f["rotulo"] for f in av.faltando)
        assert "Empresa Do Vendedor" in rotulos
        assert "Empresa Exemplo Ltda" not in rotulos
