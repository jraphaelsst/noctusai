"""Guard tests for the TWO-LAYER verdict of `comparador.pontuar` (owner
directive 2026-10-06: contracts need not be alike byte for byte, they must be
similar enough to be acceptable on that deal's terms).

Both directions are pinned, so neither layer can drift into a lying verdict:

- a MATERIAL term that diverges (price, CPF, installment amounts, matrícula
  number, cartório, party, estado civil, street, a party's certidões, a missing
  material clause) FAILS even when everything else is word-for-word identical;
- wording/structure that differs (reordered or renamed clause, merged clause, an
  extra standard clause, a missing optional clause, reworded prose) PASSES as
  `aprovado_com_observacoes`.

Every string is invented."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import comparador  # noqa: E402

_CERT_A = "1.1 – Certidão Negativa Federal – nº AAA-0001 - emitida em 01/09/2026;"
_CERT_B = "2.1 – Certidão Negativa Federal – nº BBB-0002 - emitida em 01/09/2026;"

_BASE = [
    "INSTRUMENTO PARTICULAR DE PROMESSA DE VENDA E COMPRA",
    "De um lado, FULANO DE TAL, brasileiro, casado, inscrito no CPF sob nº 111.444.777-35, residente na Rua Fictícia, nº 10, "
    "e de outro lado, BELTRANA EXEMPLO, brasileira, solteira, inscrita no CPF sob nº 529.982.247-25, residente na Avenida Modelo, nº 20.",
    "CLÁUSULA PRIMEIRA – DO OBJETO",
    "IMÓVEL: apartamento nº 11 do Edifício Exemplo, com área privativa de 80,50m2, caracterizado na Matrícula Nº 12.345 "
    "do 1º Cartório de Registro de Imóveis de Cidade Exemplo. Conforme AV.3, em 10 de janeiro de 2020, foi averbada a construção.",
    "CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO",
    "O preço certo e ajustado é de R$ 500.000,00 (quinhentos mil reais), pago da seguinte forma:",
    "Parcela 01: R$ 100.000,00 (cem mil reais) no ato da assinatura;",
    "Parcela 02: R$ 400.000,00 (quatrocentos mil reais) em até 30 (trinta) dias.",
    "CLÁUSULA TERCEIRA – DA POSSE",
    "A posse será transmitida aos compradores em 15 de outubro de 2026, livre de pessoas e coisas.",
    "CLÁUSULA QUARTA – DO ÔNUS SOBRE O IMÓVEL",
    "Os vendedores declaram que o imóvel está livre e desembaraçado de quaisquer ônus, dívidas ou ações reais.",
    "CLÁUSULA QUINTA – DAS CERTIDÕES",
    "1 - Em nome de FULANO DE TAL",
    _CERT_A,
    "2 - Em nome de BELTRANA EXEMPLO",
    _CERT_B,
    "CLÁUSULA SEXTA – DA ELEIÇÃO DO FORO",
    "As partes elegem o foro da Comarca de Cidade Exemplo para dirimir as questões deste instrumento.",
    "Cidade Exemplo, 14 de setembro de 2026.",
    "VENDEDOR",
    "COMPRADOR",
]


def _troca(paragrafos, velho, novo):
    out = [p.replace(velho, novo) for p in paragrafos]
    assert out != paragrafos, f"fixture: {velho!r} not found"
    return out


def _clausula(paragrafos, titulo_parte):
    """(inicio, fim) of the clause whose heading contains `titulo_parte`."""
    i = next(k for k, p in enumerate(paragrafos) if p.startswith("CLÁUSULA") and titulo_parte in p)
    j = next((k for k in range(i + 1, len(paragrafos)) if paragrafos[k].startswith("CLÁUSULA") or paragrafos[k].startswith("Cidade Exemplo,")), len(paragrafos))
    return i, j


def test_base_e_aprovada():
    card = comparador.pontuar(_BASE, list(_BASE))
    assert card.veredito == "aprovado", (card.motivos(), card.observacoes())


# ─── MATERIAL terms: each wrong fact FAILS (wording identical otherwise) ──


@pytest.mark.parametrize(
    "velho,novo,codigo",
    [
        ("O preço certo e ajustado é de R$ 500.000,00", "O preço certo e ajustado é de R$ 450.000,00", "numeros_divergentes"),
        ("111.444.777-35", "111.444.777-36", "numeros_divergentes"),
        ("529.982.247-25", "529.982.247-26", "numeros_divergentes"),
        ("Matrícula Nº 12.345", "Matrícula Nº 12.346", "mat_matricula_numero"),
        ("80,50m2", "81,50m2", "numeros_divergentes"),
        ("em até 30 (trinta) dias", "em até 45 (quarenta e cinco) dias", "numeros_divergentes"),
        ("em 15 de outubro de 2026", "em 20 de outubro de 2026", "datas_divergentes"),
        ("brasileiro, casado", "brasileiro, solteiro", "mat_estado_civil"),
        ("Rua Fictícia, nº 10", "Rua Inventada, nº 10", "mat_logradouro"),
        ("1º Cartório de Registro de Imóveis de Cidade Exemplo", "1º Cartório de Registro de Imóveis de Outra Cidade", "mat_cartorio"),
        ("FULANO DE TAL, brasileiro", "SICRANO DE TAL, brasileiro", "mat_parte_nome"),
    ],
)
def test_fato_material_errado_reprova(velho, novo, codigo):
    gerado = _troca(_BASE, velho, novo)
    card = comparador.pontuar(_BASE, gerado)
    assert card.veredito == "reprovado", card.observacoes()
    assert any(m.startswith(codigo) for m in card.motivos()), card.motivos()


def test_parcelas_com_valores_trocados_reprovam():
    """The SAME two amounts, swapped between installments: a bare set-of-values
    comparison would pass this; the installment order is a material fact."""
    gerado = _troca(_troca(_BASE, "Parcela 01: R$ 100.000,00", "Parcela 01: R$ 400.000,00"), "Parcela 02: R$ 400.000,00", "Parcela 02: R$ 100.000,00")
    card = comparador.pontuar(_BASE, gerado)
    assert card.veredito == "reprovado"
    assert card.resumo()["numeros_materiais_por_tipo"].get("parcela", 0) >= 2


def test_certidoes_de_uma_parte_obrigatoria_faltando_reprova():
    """Every certidão of one required party is missing from the render."""
    gerado = [p for p in _BASE if p not in ("2 - Em nome de BELTRANA EXEMPLO", _CERT_B)]
    card = comparador.pontuar(_BASE, gerado)
    assert card.veredito == "reprovado"
    assert card.motivos() == ["mat_certidoes_parte_ausente:1"]
    # the card DECLARED its certidão data missing → a gap, never a pass and never a failure
    declarado = comparador.pontuar(_BASE, gerado, certidoes_ausentes_sao_lacuna=True)
    assert declarado.motivos() == [] and declarado.veredito == "incompleto"


@pytest.mark.parametrize("titulo", ["DO OBJETO", "DO PREÇO", "DA POSSE", "DO ÔNUS"])
def test_clausula_material_faltando_reprova(titulo):
    i, j = _clausula(_BASE, titulo)
    gerado = _BASE[:i] + _BASE[j:]
    card = comparador.pontuar(_BASE, gerado)
    assert card.veredito == "reprovado"
    assert any(m.startswith("clausula_material_faltando") for m in card.motivos()), card.motivos()


def test_valor_extra_na_clausula_padrao_reprova():
    """A money amount the render invents in boilerplate is not standard wording."""
    gerado = _troca(_BASE, "para dirimir as questões deste instrumento", "para dirimir as questões deste instrumento, sob multa de R$ 9.999,00")
    assert comparador.pontuar(_BASE, gerado).veredito == "reprovado"


def test_lacuna_continua_incompleto_e_nao_aprovado():
    gerado = _troca(_BASE, "111.444.777-35", comparador.MARCADOR_LACUNA)
    card = comparador.pontuar(_BASE, gerado)
    assert card.veredito == "incompleto", card.motivos()


def test_lacuna_nao_esconde_preco_errado():
    gerado = _troca(_troca(_BASE, "111.444.777-35", comparador.MARCADOR_LACUNA), "R$ 500.000,00", "R$ 450.000,00")
    assert comparador.pontuar(_BASE, gerado).veredito == "reprovado"


# ─── WORDING / STRUCTURE: each difference PASSES with observations ────────


def _aceito(gerado, esperado_obs=None):
    card = comparador.pontuar(_BASE, gerado)
    assert card.motivos() == [], (card.motivos(), card.detalhe()["secoes"])
    assert card.veredito == "aprovado_com_observacoes", (card.veredito, card.observacoes())
    if esperado_obs:
        assert any(o.startswith(esperado_obs) for o in card.observacoes()), card.observacoes()
    return card


def test_clausulas_reordenadas_passam():
    i, j = _clausula(_BASE, "DA POSSE")
    k, m = _clausula(_BASE, "DO ÔNUS")
    gerado = _BASE[:i] + _BASE[k:m] + _BASE[i:j] + _BASE[m:]
    card = comparador.pontuar(_BASE, gerado)
    assert card.motivos() == [], card.motivos()
    assert card.clausulas_faltando == [] and card.clausulas_extras == []


def test_titulo_de_clausula_renomeado_passa():
    gerado = _troca(_BASE, "CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO", "CLÁUSULA SEGUNDA – DO VALOR DA NEGOCIAÇÃO")
    card = comparador.pontuar(_BASE, gerado)
    assert card.motivos() == [], card.motivos()
    assert card.clausulas_faltando == []


def test_renomeado_nao_protege_preco_errado():
    gerado = _troca(
        _troca(_BASE, "CLÁUSULA SEGUNDA – DO PREÇO E CONDIÇÕES DE PAGAMENTO", "CLÁUSULA SEGUNDA – DO VALOR DA NEGOCIAÇÃO"),
        "R$ 500.000,00", "R$ 450.000,00",
    )
    assert comparador.pontuar(_BASE, gerado).veredito == "reprovado"


def test_clausula_padrao_extra_com_mp_passa():
    extra = [
        "CLÁUSULA SÉTIMA – DA ASSINATURA DIGITAL",
        "As partes reconhecem a validade da assinatura eletrônica nos termos da Medida Provisória nº 2.200-2, de 24 de agosto de 2001, e do art. 10, § 2º, e do art. 107 do Código Civil.",
    ]
    i, _ = _clausula(_BASE, "DA ELEIÇÃO DO FORO")
    _aceito(_BASE[:i] + extra + _BASE[i:], "clausulas_extras")


def test_declaracoes_da_vendedora_extra_passa():
    extra = [
        "CLÁUSULA SÉTIMA – DAS DECLARAÇÕES GERAIS DA VENDEDORA",
        "A vendedora declara que o imóvel não é objeto de ação judicial, que foi construído há 20 anos e que as 3 vagas de garagem acompanham a unidade.",
    ]
    i, _ = _clausula(_BASE, "DA ELEIÇÃO DO FORO")
    _aceito(_BASE[:i] + extra + _BASE[i:], "clausulas_extras")


def test_clausula_opcional_faltando_passa():
    i, j = _clausula(_BASE, "DA ELEIÇÃO DO FORO")
    gerado = _BASE[:i] + _BASE[j:]
    _aceito(gerado, "clausulas_opcionais_faltando")


def test_redacao_diferente_sem_alterar_fatos_passa():
    gerado = _troca(
        _BASE,
        "Os vendedores declaram que o imóvel está livre e desembaraçado de quaisquer ônus, dívidas ou ações reais.",
        "Declaram os vendedores, sob as penas da lei, que o bem se encontra desembaraçado, sem gravames, débitos ou demandas pendentes.",
    )
    card = comparador.pontuar(_BASE, gerado)
    assert card.motivos() == [], card.motivos()
    assert card.veredito in ("aprovado", "aprovado_com_observacoes")
    assert card.categorias["redacao"] < 1.0  # the wording DID change, and that is not a failure


def test_clausulas_fundidas_passam():
    """Two reference clauses (posse + ônus) folded into one generated clause."""
    i, j = _clausula(_BASE, "DA POSSE")
    k, m = _clausula(_BASE, "DO ÔNUS")
    fundida = ["CLÁUSULA TERCEIRA – DA POSSE E DO ÔNUS"] + _BASE[i + 1 : j] + _BASE[k + 1 : m]
    card = comparador.pontuar(_BASE, _BASE[:i] + fundida + _BASE[m:])
    assert card.motivos() == [], (card.motivos(), card.clausulas_faltando)


def test_fundida_nao_protege_prazo_errado():
    i, j = _clausula(_BASE, "DA POSSE")
    k, m = _clausula(_BASE, "DO ÔNUS")
    fundida = ["CLÁUSULA TERCEIRA – DA POSSE E DO ÔNUS"] + _BASE[i + 1 : j] + _BASE[k + 1 : m]
    gerado = _BASE[:i] + fundida + _BASE[m:]
    gerado = _troca(gerado, "em 15 de outubro de 2026", "em 16 de outubro de 2026")
    assert comparador.pontuar(_BASE, gerado).veredito == "reprovado"


def test_citacao_legal_e_ato_do_registro_sao_observacoes():
    """Statutory numerals and registry-act numbers the render adds/changes are
    not facts of the deal."""
    gerado = _troca(_BASE, "Conforme AV.3, em 10 de janeiro de 2020, foi averbada a construção.", "Conforme AV.7, em 11 de fevereiro de 2021, foi averbada a construção (protocolo nº 55.123).")
    card = _aceito(gerado)
    assert card.obs_numeros + card.obs_datas >= 1


def test_certidao_novamente_emitida_passa():
    gerado = _troca(_BASE, "BBB-0002 - emitida em 01/09/2026", "BBB-0009 - emitida em 20/09/2026")
    card = comparador.pontuar(_BASE, gerado)
    assert card.motivos() == [] and card.resumo()["certidoes_reemitidas"] == 1
    # same kind, only the identifier changed: a non-material difference, reported
    so_numero = _troca(_BASE, "BBB-0002", "BBB-0009")
    _aceito(so_numero, "numeros_nao_materiais")


# ─── the verdict surface ──────────────────────────────────────────────────


def test_resumo_expoe_camadas_sem_valores():
    gerado = _troca(_BASE, "R$ 500.000,00", "R$ 450.000,00")
    resumo = comparador.pontuar(_BASE, gerado).resumo()
    assert resumo["veredito"] == "reprovado" and "observacoes" in resumo
    assert resumo["numeros_materiais_por_tipo"] == {"valor": 2}
    texto = str(resumo)
    for valor in ("500", "450", "111.444", "FULANO", "12.345"):
        assert valor not in texto


def test_cli_exit_code_aprovado_com_observacoes(tmp_path):
    ref = tmp_path / "ref.txt"
    gen = tmp_path / "gen.txt"
    ref.write_text("\n".join(_BASE), encoding="utf-8")
    i, j = _clausula(_BASE, "DA ELEIÇÃO DO FORO")
    gen.write_text("\n".join(_BASE[:i] + _BASE[j:]), encoding="utf-8")
    assert comparador.main(["--ref", str(ref), "--gerado", str(gen)]) == 0


def test_limiares_json_versionado_carrega_e_e_leniente():
    lim = comparador.Limiares.de_arquivo()
    assert lim.max_numeros_divergentes == 0 and lim.max_datas_divergentes == 0  # material stays strict
    assert lim.falhar_em_clausula_extra is False
    assert lim.secao_min <= 0.5 and lim.redacao_min <= 0.75  # wording is an observation floor
