"""Generator defects found by replaying a real signed deal (799) against the
generator's render — each reproduced here on SYNTHETIC data only.

1. a married seller whose spouse signs as ANUENTE lost "casado";
2. an all-female group printed masculine plural ("Os COMPRADORES … casados");
3. a `forma_pagamento` typed as a clause printed "por meio de pago aos …";
4. readiness avisos: external PJ intermediário without representante, a
   sede without número/CEP, a doação em adiantamento de legítima whose
   doadores are not anuentes;
5. an RG read only off a CNH (no check digit) is missing for the contract
   exactly as it is for the card checklist (one predicate).

V1..V6 (`contrato_gerador_fixtures`) are reused as bases and never edited.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub import documento_checklist_service as checklist
from app.modules.card_hub.contrato_gerador import derivacao, documento, frases, lint
from app.modules.card_hub.contrato_gerador.concordancia import lado, plural_feminino
from app.modules.card_hub.contrato_gerador.dados import (
    Endereco,
    Intermediario,
    TitularMatricula,
)
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _avaliar(d):
    sw = derivacao.derivar_switches(d, fx.POLITICA_PADRAO, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, fx.POLITICA_PADRAO, fx.ASSINATURA, fx.REFERENCIA)


def _texto(d) -> str:
    sw = derivacao.derivar_switches(d, fx.POLITICA_PADRAO, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, fx.POLITICA_PADRAO, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, fx.POLITICA_PADRAO, fx.ASSINATURA)
    achados = lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas)
    assert achados == [], achados
    return "\n".join(r.paragrafos)


def _codigos(itens) -> set[str]:
    return {i["codigo"] for i in itens}


def _mensagens(itens, codigo: str) -> list[str]:
    return [i["mensagem"] for i in itens if i["codigo"] == codigo]


# ─── 1. estado civil of a seller whose spouse is an anuente ───────────────


def _vendedor_com_anuente():
    d = fx.variante(1)
    casamento = date(2000, 6, 10)
    v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial",
                 conjuge_cliente_id="an1", data_casamento=casamento, profissao="Engenheiro")
    a = replace(
        fx.pessoa("an1", "vendedor", "anuente", "Cicrana Anuente", "Feminino", "111222333", "55.555.555-5"),
        estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="v1",
        data_casamento=casamento,
    )
    return replace(d, vendedores=[v1, a])


class TestEstadoCivilDoVendedorComAnuente:
    def test_the_married_seller_states_casado(self):
        texto = _texto(_vendedor_com_anuente())
        assert "FULANO DE TAL, brasileiro, casado, engenheiro, portador" in texto

    def test_the_anuente_paragraph_is_unchanged(self):
        texto = _texto(_vendedor_com_anuente())
        assert (
            "CICRANA ANUENTE, brasileira, analista, portadora da cédula de identidade RG"
        ) in texto
        assert "casada no regime da comunhão parcial de bens, na vigência da Lei 6.515/77 com FULANO DE TAL" in texto

    def test_a_couple_on_the_same_side_still_uses_the_nucleo_wording(self):
        d = fx.variante(1)
        casamento = date(2000, 6, 10)
        v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens="comunhao_parcial",
                     conjuge_cliente_id="v2", data_casamento=casamento)
        v2 = replace(fx.pessoa("v2", "vendedor", "conjuge", "Cicrana Amostra", "Feminino", "111222333",
                               "55.555.555-5"),
                     estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="v1",
                     data_casamento=casamento)
        texto = _texto(replace(d, vendedores=[v1, v2]))
        assert "FULANO DE TAL, brasileiro, analista" in texto  # the núcleo carries "casados"
        assert "casados no regime da comunhão parcial de bens" in texto


# ─── 2. all-female group agreement ────────────────────────────────────────


def _compradoras_casadas():
    d = fx.variante(1)
    casamento = date(2015, 3, 1)
    c1 = replace(d.compradores[0], estado_civil="casado", regime_bens="comunhao_parcial",
                 conjuge_cliente_id="c2", data_casamento=casamento)
    c2 = replace(
        fx.pessoa("c2", "comprador", "conjuge", "Sicrana Compradora", "Feminino", "741852963", "88.888.888-8"),
        estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="c1",
        data_casamento=casamento,
    )
    return replace(d, compradores=[c1, c2])


class TestGrupoFeminino:
    def test_two_married_compradoras_agree_in_the_feminine_plural(self):
        texto = _texto(_compradoras_casadas())
        assert "casadas no regime da comunhão parcial de bens" in texto
        assert "residentes e domiciliadas na" in texto
        assert 'denominadas neste ato simplesmente "COMPRADORAS"' in texto
        assert "As COMPRADORAS" in texto or "as COMPRADORAS" in texto
        assert "COMPRADORES" not in texto
        assert "casados no regime" not in texto

    def test_the_concordancia_of_an_all_female_group(self):
        C = lado(["f", "f"], "comprador")
        assert (C.NOME, C.ART, C.art, C.aos, C.dos, C.pelos, C.estes) == (
            "COMPRADORAS", "As", "as", "às", "das", "pelas", "estas",
        )
        assert C.g("denominado", "denominada", "denominados") == "denominadas"
        assert C.g("legítimo proprietário", "legítima proprietária", "legítimos proprietários") == (
            "legítimas proprietárias"
        )
        assert C.g("ciente", "ciente", "cientes") == "cientes"
        assert C.g("responsável", "responsável", "responsáveis") == "responsáveis"
        assert C.pl("declara", "declaram") == "declaram"

    def test_one_man_makes_the_group_masculine(self):
        C = lado(["f", "m"], "comprador")
        assert (C.NOME, C.ART) == ("COMPRADORES", "Os")
        assert C.g("denominado", "denominada", "denominados") == "denominados"

    def test_a_single_woman_is_still_singular(self):
        C = lado(["f"], "comprador")
        assert (C.NOME, C.ART) == ("COMPRADORA", "A")

    def test_plural_feminino_takes_an_explicit_form_untouched(self):
        assert plural_feminino("deste", "desta", "destes") == "destas"
        assert lado(["f", "f"], "vendedor").g("x", "y", "z", "w") == "w"


# ─── 3. forma de pagamento typed as a clause ──────────────────────────────

FORMA_CLAUSULA = "pago aos intermediadores diretamente pelas COMPRADORAS"


def _parcela_forma(forma: str, *, favorecido: bool):
    d = fx.variante(1)
    p2 = replace(d.parcelas[1], forma_pagamento=forma, favorecido_id="fav-v" if favorecido else None)
    return replace(d, parcelas=[d.parcelas[0], p2, d.parcelas[2]])


class TestFormaDePagamentoClausula:
    def test_a_clause_forma_prints_bare_never_after_por_meio_de(self):
        texto = _texto(_parcela_forma(FORMA_CLAUSULA, favorecido=False))
        assert "por meio de pago" not in texto
        assert f", {FORMA_CLAUSULA}." in texto

    def test_a_clause_forma_without_account_is_an_aviso(self):
        av = _avaliar(_parcela_forma(FORMA_CLAUSULA, favorecido=False))
        assert "FORMA_PAGAMENTO_NAO_E_MEIO" in _codigos(av.avisos)
        assert "FORMA_PAGAMENTO_NAO_E_MEIO" not in _codigos(av.bloqueios)

    def test_a_clause_forma_with_an_account_is_refused(self):
        av = _avaliar(_parcela_forma(FORMA_CLAUSULA, favorecido=True))
        assert "FORMA_PAGAMENTO_NAO_E_MEIO" in _codigos(av.bloqueios)
        assert not av.pronto

    def test_a_means_keeps_por_meio_de(self):
        assert frases.por_meio_de("PIX") == "por meio de PIX"
        assert frases.por_meio_de("Transferência bancária com recursos próprios") == (
            "por meio de transferência bancária com recursos próprios"
        )
        assert not frases.forma_e_clausula("Boleto")

    def test_a_prepositioned_means_is_not_doubled(self):
        assert frases.por_meio_de("mediante boleto") == "mediante boleto"
        assert frases.por_meio_de("via PIX") == "via PIX"

    def test_a_plain_means_raises_no_aviso(self):
        av = _avaliar(fx.variante(1))
        assert "FORMA_PAGAMENTO_NAO_E_MEIO" not in _codigos(av.avisos)


# ─── 4. readiness avisos ──────────────────────────────────────────────────


def _intermediario_pj(**extra) -> Intermediario:
    base = dict(
        id="int-ext", corretor_id=None, nome="Parceira Imóveis Ltda", creci="00002-J",
        tipo="percentual", valor=Decimal("3"), favorecido_id="fav-org", pessoa_tipo="pj",
        documento="11444777000161",
        endereco=Endereco(logradouro="Rua Parceira", numero="5", complemento=None, bairro="Centro",
                          cidade="Cidade Exemplo", uf="SP", cep="01000000"),
    )
    base.update(extra)
    return Intermediario(**base)


def _com_intermediario(it: Intermediario):
    d = fx.variante(1)
    return replace(d, intermediarios=d.intermediarios + [it])


class TestAvisosIntermediarioESede:
    def test_a_pj_intermediario_without_representante_is_warned(self):
        av = _avaliar(_com_intermediario(_intermediario_pj()))
        assert _mensagens(av.avisos, "INTERMEDIARIO_PJ_SEM_REPRESENTANTE")
        assert "Parceira Imóveis Ltda" in _mensagens(av.avisos, "INTERMEDIARIO_PJ_SEM_REPRESENTANTE")[0]

    def test_a_represented_pj_or_a_pf_is_not_warned(self):
        av = _avaliar(_com_intermediario(_intermediario_pj(representante_nome="Rep Exemplo")))
        assert "INTERMEDIARIO_PJ_SEM_REPRESENTANTE" not in _codigos(av.avisos)
        av = _avaliar(_com_intermediario(_intermediario_pj(pessoa_tipo="pf", documento=fx.cpf_sintetico("147258369"))))
        assert "INTERMEDIARIO_PJ_SEM_REPRESENTANTE" not in _codigos(av.avisos)

    def test_the_office_itself_is_never_an_external_pj(self):
        av = _avaliar(fx.variante(1))
        assert "INTERMEDIARIO_PJ_SEM_REPRESENTANTE" not in _codigos(av.avisos)

    def test_an_intermediario_sede_without_cep_is_warned(self):
        it = _intermediario_pj(representante_nome="Rep Exemplo",
                               endereco=replace(_intermediario_pj().endereco, cep=None))
        av = _avaliar(_com_intermediario(it))
        assert any("CEP" in m for m in _mensagens(av.avisos, "INTERMEDIARIO_SEDE_INCOMPLETA"))
        assert "INTERMEDIARIO_SEDE_INCOMPLETA" not in _codigos(av.bloqueios)

    def test_the_office_sede_without_numero_is_warned_never_blocked(self):
        d = fx.variante(1)
        org = replace(d.imobiliaria, endereco=replace(d.imobiliaria.endereco, numero=None))
        av = _avaliar(replace(d, imobiliaria=org))
        assert any("número" in m for m in _mensagens(av.avisos, "IMOBILIARIA_SEDE_INCOMPLETA"))
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_a_complete_sede_raises_nothing(self):
        av = _avaliar(fx.variante(1))
        assert not {"IMOBILIARIA_SEDE_INCOMPLETA", "INTERMEDIARIO_SEDE_INCOMPLETA"} & _codigos(av.avisos)


def _doacao(texto: str, *anuentes):
    d = fx.variante(1)
    im = replace(
        d.imovel,
        titulo_natureza="doacao",
        titulo_aquisitivo_texto=texto,
        transmitentes_titulo=(TitularMatricula(nome="Doadora Exemplo da Silva"),),
    )
    return replace(d, imovel=im, vendedores=d.vendedores + list(anuentes))


LEGITIMA = "por doação em adiantamento de legítima, conforme R.3 da matrícula"


class TestDoacaoAdiantamentoDeLegitima:
    def test_doadores_not_on_the_contract_are_warned_by_name(self):
        av = _avaliar(_doacao(LEGITIMA))
        msgs = _mensagens(av.avisos, "DOACAO_ADIANTAMENTO_LEGITIMA_SEM_ANUENTE")
        assert msgs and "Doadora Exemplo da Silva" in msgs[0]
        assert "confirme se os doadores devem anuir" in msgs[0]
        assert "DOACAO_ADIANTAMENTO_LEGITIMA_SEM_ANUENTE" not in _codigos(av.bloqueios)

    def test_a_doadora_signing_as_anuente_clears_it(self):
        doadora = fx.pessoa("an7", "vendedor", "anuente", "Doadora Exemplo da Silva", "Feminino",
                            "369258147", "99.999.999-9")
        av = _avaliar(_doacao(LEGITIMA, doadora))
        assert "DOACAO_ADIANTAMENTO_LEGITIMA_SEM_ANUENTE" not in _codigos(av.avisos)

    def test_a_doacao_without_adiantamento_de_legitima_is_silent(self):
        av = _avaliar(_doacao("por doação, conforme R.3 da matrícula"))
        assert "DOACAO_ADIANTAMENTO_LEGITIMA_SEM_ANUENTE" not in _codigos(av.avisos)


# ─── 5. RG read only off a CNH ────────────────────────────────────────────

ORG_UUID = UUID(ORG_ID)


def _cliente_cnh(cid: str, **extra) -> dict:
    base = cliente_row(
        cid,
        nome_oficial="Pessoa Exemplo", nacionalidade="brasileira", profissao="Analista",
        estado_civil="solteiro", regime_bens=None, cpf="412.954.238-98",
        rg="41.111.222", rg_orgao_expedidor="SSP/SP", rg_origem="cnh", rg_confirmado_em=None,
        endereco_logradouro="Rua das Flores", endereco_numero="1", endereco_bairro="Centro",
        endereco_cidade="São Paulo", endereco_uf="SP", endereco_cep="01310-100",
        conjuge_cliente_id=None,
    )
    base.update(extra)
    return base


class TestRgSoDaCnh:
    def test_a_cnh_only_rg_is_missing_for_the_contract(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [_cliente_cnh(cid)])
        out = checklist.completude_contratual(scoped, ORG_UUID, cid)
        assert checklist.CHAVE_RG_SO_DA_CNH in out["faltando"]
        assert out["completo"] is False

    def test_agrees_with_the_card_checklist_rule(self, client, scoped):
        cid = str(uuid4())
        row = _cliente_cnh(cid)
        assert "rg" in checklist.campos_faltando(row, "identidade", {})

    def test_a_confirmed_rg_is_complete(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [_cliente_cnh(cid, rg_confirmado_em="2026-09-01T00:00:00Z")])
        out = checklist.completude_contratual(scoped, ORG_UUID, cid)
        assert checklist.CHAVE_RG_SO_DA_CNH not in out["faltando"]

    def test_an_rg_card_reading_the_same_number_corroborates_it(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [_cliente_cnh(cid)])
        scoped.set_table_data(checklist.DOCUMENTOS_TABLE, [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "tipo_documento": "rg",
            "extracao_rg": "41.111.222-3", "deleted_at": None, "created_at": "2026-09-01T00:00:00Z",
        }])
        out = checklist.completude_contratual(scoped, ORG_UUID, cid)
        assert checklist.CHAVE_RG_SO_DA_CNH not in out["faltando"]

    def test_the_contract_gate_names_it_with_the_checklist_label(self):
        d = fx.variante(1)
        v = replace(d.vendedores[0], faltando_qualificacao=[checklist.CHAVE_RG_SO_DA_CNH])
        av = _avaliar(replace(d, vendedores=[v]))
        faltas = [f for f in av.faltando if f["campo"] == f"qualificacao.{checklist.CHAVE_RG_SO_DA_CNH}"]
        assert faltas and faltas[0]["rotulo"].startswith(checklist.ROTULO_RG_SO_DA_CNH)
        assert not av.pronto
