"""Migration 193 — party qualification + non-payment clauses from the signed
corpus (redacted catalog §3-§7, §9): anuente, PJ party, pacto antenupcial,
RNE/RNM, registry naming, ônus já quitado / usufruto, verbatim operator
obligations, the imóvel certidão's real resultado.

NEW fixture variants only — V1..V6 (`contrato_gerador_fixtures`) are reused
as bases and never edited, so the pinned renders stay stable. Every name,
CPF and number here is synthetic.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, frases, lint
from app.modules.card_hub.contrato_gerador.dados import (
    AtoCitado,
    Certidao,
    CertidaoImovel,
    Endereco,
    PactoAntenupcial,
    ParteJuridica,
)
from app.modules.card_hub.contrato_gerador.frases import CERTIDOES
from tests.modules.card_hub import contrato_gerador_fixtures as fx

CNPJ_PJ = "11444777000161"


def _avaliar(n: int, d):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _render(n: int, d):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA)
    achados = lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas)
    assert achados == [], achados
    return r


def _texto(n: int, d) -> str:
    return "\n".join(_render(n, d).paragrafos)


def _codigos(itens) -> set[str]:
    return {i["codigo"] for i in itens}


def _campos(av) -> set[str]:
    return {f["campo"] for f in av.faltando}


# ─── fixture variants ─────────────────────────────────────────────────────


def _anuente(estado_civil: str = "casado", regime: str | None = "comunhao_parcial", **extra):
    """V1's seller married to a non-owning spouse who signs as ANUENTE."""
    d = fx.variante(1)
    casamento = date(2000, 6, 10) if estado_civil == "casado" else None
    v1 = replace(d.vendedores[0], estado_civil=estado_civil, regime_bens=regime,
                 conjuge_cliente_id="an1", data_casamento=casamento)
    a = replace(
        fx.pessoa("an1", "vendedor", "anuente", "Cicrana Anuente", "Feminino", "111222333", "55.555.555-5"),
        estado_civil=estado_civil, regime_bens=regime, conjuge_cliente_id="v1", data_casamento=casamento,
        **extra,
    )
    return replace(d, vendedores=[v1, a])


def _certidoes_pj() -> list[Certidao]:
    return [
        Certidao(tipo=t, resultado="negativa", numero=f"PJ-{i:04d}", emitida_em=date(2026, 9, 1),
                 validade_ate=date(2026, 12, 1), consulta_tipo_documento="cnpj")
        for i, (t, _r, _n, _pf, pj, _s) in enumerate(CERTIDOES, start=1) if pj
    ]


def _pj_vendedora(**pj_extra):
    """V1 sold by a COMPANY (corpus deal 866), signed by its sócio-administrador."""
    d = fx.variante(1)
    rep = replace(d.vendedores[0], papel="representante", representa_parte_id="pj1",
                  certidoes=[], certidao_estado_civil_emitida_em=None)
    base = dict(
        parte_id="pj1", empresa_id="emp1", lado="vendedor", papel="proprietario",
        razao_social="Acme Empreendimentos Ltda", cnpj=CNPJ_PJ, nire="35200000001",
        sede=Endereco(logradouro="Rua da Sede", numero="7", complemento=None, bairro="Centro",
                      cidade="Cidade Exemplo", uf="SP", cep="01000000"),
        situacao_cadastral="ativa", certidoes=_certidoes_pj(),
    )
    base.update(pj_extra)
    return replace(d, vendedores=[rep], partes_pj=[ParteJuridica(**base)])


def _casal_vendedor(regime: str, casamento: date, *, pacto_v1=None, pacto_v2=None):
    d = fx.variante(1)
    v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens=regime,
                 conjuge_cliente_id="v2", data_casamento=casamento, pacto=pacto_v1)
    v2 = replace(fx.pessoa("v2", "vendedor", "conjuge", "Cicrana Amostra", "Feminino", "111222333",
                           "55.555.555-5"),
                 estado_civil="casado", regime_bens=regime, conjuge_cliente_id="v1",
                 data_casamento=casamento, pacto=pacto_v2)
    return replace(d, vendedores=[v1, v2])


PACTO = PactoAntenupcial(data=date(2001, 3, 10), tabelionato="2º Tabelião de Notas de Cidade Exemplo",
                         livro="123", folha="45")


# ─── 1. anuente ───────────────────────────────────────────────────────────


class TestAnuente:
    def test_spouse_anuente_is_qualified_signs_and_presents_certidoes(self):
        d = _anuente()
        texto = _texto(1, d)
        assert (
            "casada no regime da comunhão parcial de bens, na vigência da Lei 6.515/77 com FULANO DE TAL, "
            'já qualificado anteriormente, denominada neste ato simplesmente "ANUENTE";'
        ) in texto
        assert "CICRANA ANUENTE, brasileira, analista" in texto
        assert "Em nome de CICRANA ANUENTE" in texto
        assert "em seu nome, em nome da Anuente, abaixo relacionadas" in texto
        paragrafos = _render(1, d).paragrafos
        assert "ANUENTE" in paragrafos  # its own signature heading
        # the seller side stays singular: the anuente is not a VENDEDOR
        assert '"VENDEDOR"' in texto and "VENDEDORES" not in texto

    def test_spouse_anuente_owes_the_vendedor_certidoes(self):
        d = _anuente(certidoes=[])
        av = _avaliar(1, d)
        assert any(f["campo"].startswith("certidao.") and f["parte_id"] == "parte-an1" for f in av.faltando)

    def test_companion_anuente_uses_the_uniao_estavel_wording(self):
        texto = _texto(1, _anuente("uniao_estavel", None))
        assert "que convive em união estável com" in texto
        assert "já qualificado anteriormente" in texto

    def test_a_non_spouse_anuente_has_no_wording_and_no_certidoes(self):
        d = fx.variante(1)
        estranho = fx.pessoa("an9", "vendedor", "anuente", "Pessoa Estranha", "Masculino", "333444555",
                             "77.777.777-7", certidoes=[])
        d = replace(d, vendedores=d.vendedores + [estranho])
        av = _avaliar(1, d)
        assert "ANUENTE_SEM_REDACAO" in _codigos(av.bloqueios)
        assert not any(f["parte_id"] == "parte-an9" and f["campo"].startswith("certidao.") for f in av.faltando)
        assert "PARTE_NAO_SIGNATARIA" not in _codigos(av.avisos)

    def test_two_sellers_each_with_an_anuente_number_the_list(self):
        d = _anuente()
        v2 = replace(fx.pessoa("v2", "vendedor", "proprietario", "Beltrano Dono", "Masculino", "444555666",
                               "88.888.888-8"),
                     estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="an2",
                     data_casamento=date(2005, 1, 1))
        a2 = replace(fx.pessoa("an2", "vendedor", "anuente", "Fulana Segunda", "Feminino", "555666777",
                               "99.999.999-9"),
                     estado_civil="casado", regime_bens="comunhao_parcial", conjuge_cliente_id="v2",
                     data_casamento=date(2005, 1, 1))
        d = replace(d, vendedores=d.vendedores + [v2, a2])
        paragrafos = _render(1, d).paragrafos
        assert any(p.startswith("1-) ") for p in paragrafos)
        ultimo = next(p for p in paragrafos if p.startswith("2-) "))
        assert ultimo.endswith('denominadas neste ato simplesmente "ANUENTES";')
        assert "ANUENTES" in paragrafos


# ─── 2. PJ party ──────────────────────────────────────────────────────────


class TestParteJuridica:
    def test_pj_seller_is_qualified_with_the_corpus_wording(self):
        d = _pj_vendedora()
        texto = _texto(1, d)
        assert (
            "ACME EMPREENDIMENTOS LTDA, pessoa jurídica de direito privado, devidamente inscrita sob CNPJ nº "
            "11.444.777/0001-61 e NIRE 35200000001, com sede na Rua da Sede, nº 7 - Centro - Cidade Exemplo/SP"
        ) in texto
        assert "representada neste ato por seu sócio e administrador FULANO DE TAL, brasileiro, solteiro" in texto
        assert '"VENDEDORA"' in texto
        assert "Em nome de ACME EMPREENDIMENTOS LTDA" in texto
        # the representante is not a certificando
        assert "Em nome de FULANO DE TAL" not in texto
        paragrafos = _render(1, d).paragrafos
        assert any(p.startswith("Por: FULANO DE TAL") for p in paragrafos)
        assert "Sócio-Administrador" in paragrafos

    def test_pj_raises_the_review_aviso_and_item(self):
        av = _avaliar(1, _pj_vendedora())
        assert av.pronto
        mensagem = next(a["mensagem"] for a in av.avisos if a["codigo"] == "PJ_REDACAO_A_CONFIRMAR")
        assert "redação de PJ derivada de um único contrato assinado — confirme na revisão jurídica" in mensagem
        assert "PJ_REDACAO_A_CONFIRMAR" in _codigos(av.itens_revisao)

    @pytest.mark.parametrize("campo, extra", [
        ("partes.pj.nire", {"nire": None}),
        ("partes.pj.razao_social", {"razao_social": None}),
        ("partes.pj.sede_cidade", {"sede": Endereco(logradouro="Rua", numero="1", bairro="B", uf="SP",
                                                    cep="01000000")}),
    ])
    def test_each_missing_pj_field_is_named(self, campo, extra):
        av = _avaliar(1, _pj_vendedora(**extra))
        assert campo in _campos(av)
        assert "partes.pj_sem_qualificacao" not in _campos(av)

    def test_a_pj_without_representante_is_missing_one(self):
        d = _pj_vendedora()
        d = replace(d, vendedores=[replace(d.vendedores[0], representa_parte_id="outra")])
        av = _avaliar(1, d)
        assert "partes.pj.representante" in _campos(av)
        assert "REPRESENTANTE_SEM_EMPRESA" in _codigos(av.bloqueios)

    def test_the_pj_needs_its_own_cnpj_certidoes(self):
        av = _avaliar(1, _pj_vendedora(certidoes=[]))
        assert any(f["campo"].startswith("certidao.") and f["parte_id"] == "pj1" for f in av.faltando)

    def test_a_married_representante_needs_no_spouse(self):
        d = _pj_vendedora()
        d = replace(d, vendedores=[replace(d.vendedores[0], estado_civil="casado", regime_bens=None,
                                           conjuge_cliente_id="alguem",
                                           faltando_qualificacao=["regime_bens", "conjuge"])])
        av = _avaliar(1, d)
        assert av.pronto, (av.faltando, av.bloqueios)
        assert "representada neste ato por seu sócio e administrador FULANO DE TAL, brasileiro, casado" in _texto(1, d)


# ─── 3. pacto antenupcial ─────────────────────────────────────────────────


class TestPactoAntenupcial:
    def test_the_pacto_is_cited_in_the_couples_qualification(self):
        texto = _texto(1, _casal_vendedor("separacao_total", date(2001, 3, 20), pacto_v1=PACTO, pacto_v2=PACTO))
        assert (
            "casados no regime da separação total de bens, na vigência da Lei 6.515/77, conforme escritura "
            "de pacto antenupcial, lavrada aos 10 de março de 2001, pelo 2º Tabelião de Notas de Cidade "
            "Exemplo, no Livro nº 123, Página nº 45, residentes e domiciliados"
        ) in texto

    @pytest.mark.parametrize("regime, casamento, exige", [
        ("separacao_total", date(2001, 3, 20), True),
        ("participacao_final_aquestos", date(2001, 3, 20), True),
        ("comunhao_universal", date(1990, 1, 1), True),
        ("comunhao_universal", date(1970, 1, 1), False),
        ("comunhao_parcial", date(2001, 3, 20), False),
        ("separacao_obrigatoria", date(2001, 3, 20), False),
    ])
    def test_a_regime_that_needs_a_pacto_without_one_is_missing_it(self, regime, casamento, exige):
        av = _avaliar(1, _casal_vendedor(regime, casamento))
        assert ("qualificacao.pacto_antenupcial" in _campos(av)) is exige

    def test_a_half_entered_pacto_names_the_missing_field(self):
        meio = replace(PACTO, livro=None)
        av = _avaliar(1, _casal_vendedor("separacao_total", date(2001, 3, 20), pacto_v1=meio))
        assert "qualificacao.pacto_antenupcial_livro" in _campos(av)

    def test_spouses_with_different_pactos_block(self):
        av = _avaliar(1, _casal_vendedor("separacao_total", date(2001, 3, 20), pacto_v1=PACTO,
                                         pacto_v2=replace(PACTO, folha="46")))
        assert "PACTO_ANTENUPCIAL_DIVERGENTE" in _codigos(av.bloqueios)


# ─── 4. foreign party (RNE/RNM) ───────────────────────────────────────────


class TestIdentidadeEstrangeiro:
    def _estrangeira(self, **extra):
        d = fx.variante(1)
        campos = {"nacionalidade": "italiana", "identidade_tipo": "rne",
                  "rg": "V123456-7", "rg_orgao": "CGPI/DIREX/DPF", **extra}
        c = replace(d.compradores[0], **campos)
        return replace(d, compradores=[c])

    def test_rne_replaces_the_rg_wording(self):
        texto = _texto(1, self._estrangeira())
        assert "italiana" in texto
        assert "portadora da cédula de identidade RNE V123456-7 CGPI/DIREX/DPF e inscrita no CPF/MF" in texto
        assert "RG V123456-7" not in texto

    def test_a_brazilian_identified_by_rne_blocks(self):
        av = _avaliar(1, self._estrangeira(nacionalidade="brasileira"))
        assert "IDENTIDADE_ESTRANGEIRO_BRASILEIRO" in _codigos(av.bloqueios)

    def test_a_foreigner_identified_by_rg_is_warned(self):
        av = _avaliar(1, self._estrangeira(identidade_tipo=None))
        assert "ESTRANGEIRO_COM_RG" in _codigos(av.avisos)


# ─── 5. registry naming ───────────────────────────────────────────────────


class TestCartorio:
    @pytest.mark.parametrize("bruto, impresso", [
        ("SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia - CNS: 11991-7", "Cartório de Registro de Imóveis de Cotia"),
        ("1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA", "1º Cartório de Registro de Imóveis de Cotia"),
        ("OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE SÃO PAULO/SP",
         "Cartório de Registro de Imóveis de São Paulo"),
        ("11991-7", None),
        ("18º OFICIAL DE REGISTRO DE IMÓVEIS DA CAPITAL", None),
    ])
    def test_the_corpus_form_is_derived_from_the_heading(self, bruto, impresso):
        assert frases.cartorio_texto(bruto) == impresso

    def test_the_objeto_prints_the_cartorio_form(self):
        d = fx.variante(1)
        d = replace(d, imovel=replace(d.imovel, numero_registro_imoveis="SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia"))
        texto = _texto(1, d)
        assert "do Cartório de Registro de Imóveis de Cotia." in texto
        assert "SERVENTIA" not in texto

    def test_a_reading_with_no_city_is_named(self):
        d = fx.variante(1)
        d = replace(d, imovel=replace(d.imovel, numero_registro_imoveis="11991-7"))
        assert "imovel.numero_registro_imoveis" in _campos(_avaliar(1, d))


# ─── 6. ônus: já quitado / usufruto ───────────────────────────────────────


def _ja_quitado(**termos):
    d = fx.variante(1)
    im = replace(d.imovel, situacao_onus="alienacao_fiduciaria", onus_fonte_atos=[AtoCitado("R", 3)],
                 onus_credor=None)
    base = {"onus_quitacao": "ja_quitado", "onus_baixa_protocolo_em": date(2026, 9, 2)}
    base.update(termos)
    return replace(d, imovel=im, termos=replace(d.termos, **base))


class TestOnus:
    def test_ja_quitado_prints_deal_867s_paragraph(self):
        texto = _texto(1, _ja_quitado())
        assert (
            "declara ter conhecimento de que o VENDEDOR protocolou, em 02/09/2026, junto ao Registro de "
            "Imóveis de Cidade Exemplo, o requerimento de baixa da Alienação Fiduciária registrada sob o R-03 "
            "da matrícula do imóvel, estando ciente de que a efetivação da referida baixa depende da conclusão "
            "do procedimento registral pelo Oficial competente."
        ) in texto.replace("**", "")
        assert "existir saldo de financiamento" not in texto
        assert "Matrícula Atualizada do Imóvel com a baixa da alienação fiduciária" in texto

    def test_ja_quitado_without_the_protocol_date_is_missing_it(self):
        av = _avaliar(1, _ja_quitado(onus_baixa_protocolo_em=None))
        assert "negociacao.onus_baixa_protocolo_em" in _campos(av)
        assert "ONUS_QUITACAO_SEM_REDACAO" not in _codigos(av.bloqueios)

    def test_usufruto_prints_deal_839s_paragraph_when_financed(self):
        d = fx.variante(1)
        d = replace(d, imovel=replace(d.imovel, situacao_onus="usufruto"))
        texto = _texto(1, d).replace("**", "")
        assert (
            "Parágrafo Segundo: O VENDEDOR declara estar ciente da necessidade de lavratura de escritura pública "
            "de baixa do usufruto, como condição prévia ao início do processo junto à instituição financeira a "
            "ser escolhida pela COMPRADORA para fins de financiamento imobiliário."
        ) in texto

    def test_usufruto_without_financing_has_no_wording(self):
        d = fx.variante(4)
        d = replace(d, imovel=replace(d.imovel, situacao_onus="usufruto"), parcelas=d.parcelas[:1])
        assert "ONUS_USUFRUTO_SEM_FINANCIAMENTO" in _codigos(_avaliar(4, d).bloqueios)

    @pytest.mark.parametrize("onus", ["penhora", "indisponibilidade"])
    def test_penhora_and_indisponibilidade_stay_blocked(self, onus):
        d = fx.variante(1)
        d = replace(d, imovel=replace(d.imovel, situacao_onus=onus))
        assert "ONUS_NAO_SUPORTADO" in _codigos(_avaliar(1, d).bloqueios)


# ─── 7. verbatim operator obligations ─────────────────────────────────────


class TestObrigacoesLivres:
    def test_seller_obligations_print_verbatim_in_the_onus_clause(self):
        d = fx.variante(1)
        d = replace(d, termos=replace(d.termos, obrigacoes_vendedor=(
            "O VENDEDOR se compromete a averbar a área construída em até 6 meses.\n"
            "Os custos da averbação serão do VENDEDOR."
        )))
        paragrafos = _render(1, d).paragrafos
        i = paragrafos.index("Parágrafo Único: O VENDEDOR se compromete a averbar a área construída em até 6 meses.")
        assert paragrafos[i + 1] == "Os custos da averbação serão do VENDEDOR."
        assert "DO ÔNUS" in next(p for p in reversed(paragrafos[:i]) if p.startswith("CLÁUSULA"))
        av = _avaliar(1, d)
        assert "OBRIGACOES_VENDEDOR_TEXTO_LIVRE" in _codigos(av.itens_revisao)

    def test_permuta_delivery_prints_inside_the_permuta_posse_clause(self):
        d = fx.variante(5)
        d = replace(d, termos=replace(d.termos, permuta_obrigacoes_entrega=(
            "Fica acordado entre as partes que a COMPRADORA se compromete a entregar a casa pintada."
        )))
        paragrafos = _render(5, d).paragrafos
        i = next(k for k, p in enumerate(paragrafos) if p.startswith("Durante o referido período"))
        assert paragrafos[i + 1].startswith("Fica acordado entre as partes que a COMPRADORA")

    def test_permuta_obligations_without_a_permuta_block(self):
        d = fx.variante(1)
        d = replace(d, termos=replace(d.termos, permuta_obrigacoes_entrega="Entregar pintado."))
        assert "PERMUTA_OBRIGACOES_SEM_PERMUTA" in _codigos(_avaliar(1, d).bloqueios)


# ─── 8. imóvel certidão: the real resultado ───────────────────────────────


class TestCertidaoImovelResultado:
    def _com(self, resultado):
        d = fx.variante(1)
        certs = tuple(
            replace(c, resultado=resultado) if c.tipo == "cnd_iptu" else c for c in fx.certidoes_do_imovel()
        )
        return replace(d, imovel=replace(d.imovel, certidoes=certs))

    def test_a_positive_iptu_certidao_prints_positiva(self):
        texto = _texto(1, self._com("positiva"))
        assert "Certidão Positiva de Débitos Municipais (IPTU) nº IPTU-0001" in texto
        assert "Certidão Negativa de Débitos Municipais (IPTU) nº" not in texto

    def test_positiva_com_efeito_de_negativa(self):
        assert "Certidão Positiva com Efeito de Negativa de Débitos Municipais (IPTU)" in _texto(
            1, self._com("positiva_com_efeito_de_negativa")
        )

    def test_a_missing_resultado_is_named(self):
        assert "imovel.certidao.cnd_iptu.resultado" in _campos(_avaliar(1, self._com(None)))

    def test_negativa_still_prints_negativa(self):
        assert "Certidão Negativa de Débitos Municipais (IPTU) nº IPTU-0001" in _texto(1, self._com("negativa"))
        assert CertidaoImovel  # imported for the variant builders' type


# ─── 9. the aditivo never silently drops a party it cannot word ───────────


class TestAditivoRecusaPartesSemRedacao:
    """`contrato_aditivo` reuses `derivacao._partes`, which now ACCEPTS a PJ
    party and an anuente; the aditivo's qualification prints neither, so it
    refuses them by name."""

    @pytest.mark.parametrize("variante, codigo", [
        (_pj_vendedora, "ADITIVO_PARTE_PJ_SEM_REDACAO"),
        (_anuente, "ADITIVO_ANUENTE_SEM_REDACAO"),
    ])
    def test_refused_by_name(self, variante, codigo):
        from app.modules.card_hub.contrato_aditivo.avaliacao import avaliar as avaliar_aditivo
        from tests.modules.card_hub.test_contrato_aditivo import DATA, PAGAMENTO, _aditivo, _novas_parcelas

        av = avaliar_aditivo(variante(), _aditivo(PAGAMENTO, parcelas=_novas_parcelas()),
                             fx.POLITICA_PADRAO, DATA, DATA)
        assert codigo in _codigos(av.bloqueios)
