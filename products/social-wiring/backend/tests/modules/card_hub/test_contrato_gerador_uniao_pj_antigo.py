"""P5 follow-ups — (1) "divorciado + união estável" (migration 198,
`clientes.convive_uniao_estavel`, signed deal 867) and (2) a COMPANY as
antigo proprietário (deals 858/869: the seller in the last transfer was a
construtora). Every name, CPF and CNPJ here is synthetic.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, lint
from app.modules.card_hub.contrato_gerador.dados import Certidao, ParteJuridica
from app.modules.card_hub.contrato_gerador.frases import CERTIDOES
from tests.modules.card_hub import contrato_gerador_fixtures as fx

CNPJ_ANTIGA = "11444777000161"


def _avaliar(d):
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _texto(d) -> str:
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)
    assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []
    return "\n".join(r.paragrafos)


def _codigos(itens) -> set[str]:
    return {i["codigo"] for i in itens}


# ─── 1. divorciado + união estável ────────────────────────────────────────


def _divorciado_com_companheira(**companheira_extra):
    """V1's seller, DIVORCIADO, living in união estável with a companion who
    owns nothing and signs as anuente — deal 867's shape."""
    d = fx.variante(1)
    v1 = replace(d.vendedores[0], estado_civil="divorciado", convive_uniao_estavel=True,
                 conjuge_cliente_id="an1")
    a = replace(
        fx.pessoa("an1", "vendedor", "anuente", "Cicrana Companheira", "Feminino", "111222333", "55.555.555-5"),
        estado_civil="solteiro", convive_uniao_estavel=True, conjuge_cliente_id="v1",
        certidoes=[], certidao_estado_civil_emitida_em=None, **companheira_extra,
    )
    return replace(d, vendedores=[v1, a])


class TestConviveUniaoEstavel:
    def test_each_partner_keeps_their_own_estado_civil_in_the_wording(self):
        texto = _texto(_divorciado_com_companheira())
        assert "FULANO DE TAL, brasileiro, divorciado," in texto
        assert "CICRANA COMPANHEIRA, brasileira, solteira," in texto
        assert "que convive em união estável com FULANO DE TAL" in texto

    def test_the_companion_presents_no_certidoes_by_default(self):
        """Same policy as an `estado_civil='uniao_estavel'` companion
        (`Politica.companheiro_apresenta_certidoes`)."""
        av = _avaliar(_divorciado_com_companheira())
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "Em nome de CICRANA COMPANHEIRA" not in _texto(_divorciado_com_companheira())
        pol = replace(fx.politica_variante(1), companheiro_apresenta_certidoes=True)
        d = _divorciado_com_companheira()
        sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
        exige = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
        assert any(f["campo"].startswith("certidao.") and f["parte_id"] == "parte-an1" for f in exige.faltando)

    def test_a_couple_both_flagged_pairs_in_one_nucleo_as_co_sellers(self):
        d = fx.variante(1)
        v1 = replace(d.vendedores[0], estado_civil="divorciado", convive_uniao_estavel=True,
                     conjuge_cliente_id="v2")
        v2 = replace(fx.pessoa("v2", "vendedor", "proprietario", "Beltrana Coproprietaria", "Feminino",
                               "444555666", "55.555.555-5"),
                     estado_civil="viuvo", convive_uniao_estavel=True, conjuge_cliente_id="v1")
        texto = _texto(replace(d, vendedores=[v1, v2]))
        assert "FULANO DE TAL, brasileiro, divorciado," in texto
        assert "que convive em união estável com BELTRANA COPROPRIETARIA, brasileira, viúva," in texto

    def test_flag_beside_casado_is_refused(self):
        d = fx.variante(1)
        v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial",
                     convive_uniao_estavel=True)
        assert "CONVIVE_UNIAO_ESTAVEL_CASADO" in _codigos(_avaliar(replace(d, vendedores=[v1])).bloqueios)

    def test_flag_without_a_linked_companion_is_missing(self):
        d = fx.variante(1)
        v1 = replace(d.vendedores[0], estado_civil="divorciado", convive_uniao_estavel=True)
        av = _avaliar(replace(d, vendedores=[v1]))
        assert ("qualificacao.conjuge", v1.parte_id) in {(f["campo"], f["parte_id"]) for f in av.faltando}

    def test_nucleo_checks_apply_to_a_flagged_couple(self):
        """A flagged companion who is not linked back fails like any núcleo."""
        d = _divorciado_com_companheira()
        a = replace(d.vendedores[1], conjuge_cliente_id=None)
        av = _avaliar(replace(d, vendedores=[d.vendedores[0], a]))
        assert "CONJUGE_NAO_RECIPROCO" in _codigos(av.bloqueios)


# ─── 2. a company as antigo proprietário ──────────────────────────────────


def _certidoes_pj(sem: str | None = None) -> list[Certidao]:
    return [
        Certidao(tipo=t, resultado="negativa", numero=f"PJ-{i:04d}", emitida_em=date(2026, 9, 1),
                 validade_ate=date(2026, 12, 1), consulta_tipo_documento="cnpj")
        for i, (t, _r, _n, _pf, pj, _s) in enumerate(CERTIDOES, start=1) if pj and t != sem
    ]


def _construtora(**extra) -> ParteJuridica:
    base = dict(parte_id="pja", empresa_id="empa", lado="vendedor", papel="antigo_proprietario",
                razao_social="Construtora Exemplo Ltda", cnpj=CNPJ_ANTIGA, situacao_cadastral="ativa",
                certidoes=_certidoes_pj())
    base.update(extra)
    return ParteJuridica(**base)


def _transferido_em(quando, pj: ParteJuridica | None = None):
    d = fx.variante(1)
    return replace(d, imovel=replace(d.imovel, ultima_transferencia_em=quando),
                   partes_pj=[pj] if pj is not None else [])


class TestAntigoProprietarioPJ:
    def test_a_company_answers_the_previous_owner_requirement(self):
        av = _avaliar(_transferido_em(date(2021, 9, 15), _construtora()))
        assert "partes.antigo_proprietario" not in {f["campo"] for f in av.faltando}
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "PJ_ANTIGO_PROPRIETARIO_A_CONFIRMAR" in _codigos(av.avisos)
        assert "PJ_PAPEL_SEM_REDACAO" not in _codigos(av.bloqueios)

    def test_it_is_not_qualified_but_presents_its_cnpj_certidoes(self):
        texto = _texto(_transferido_em(date(2021, 9, 15), _construtora()))
        assert "O VENDEDOR e a antiga proprietária apresentam" in texto
        assert "Em nome de CONSTRUTORA EXEMPLO LTDA" in texto
        # Not in the qualificação: its CNPJ prints nowhere but its certidões.
        assert "11.444.777/0001-61" not in texto and "NIRE" not in texto

    def test_a_missing_cnpj_certidao_is_named(self):
        av = _avaliar(_transferido_em(date(2021, 9, 15), _construtora(certidoes=_certidoes_pj(sem="cnd_federal"))))
        assert ("certidao.cnd_federal", "pja") in {(f["campo"], f["parte_id"]) for f in av.faltando}

    def test_an_old_transfer_dispenses_it_and_prints_nothing(self):
        d = _transferido_em(date(2021, 9, 14), _construtora())
        av = _avaliar(d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "ANTIGO_PROPRIETARIO_DISPENSADO" in _codigos(av.avisos)
        assert "CONSTRUTORA EXEMPLO" not in _texto(d)

    def test_it_never_counts_as_a_seller(self):
        d = _transferido_em(date(2021, 9, 15), _construtora())
        assert "partes.vendedores" in {f["campo"] for f in _avaliar(replace(d, vendedores=[])).faltando}
