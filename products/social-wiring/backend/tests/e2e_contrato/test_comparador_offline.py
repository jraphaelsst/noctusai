"""Offline tests for `comparador.py` — no database, no fixtures with real
data (every string here is invented). This is the only module in
`e2e_contrato/` collected by the normal `pytest` run; `harness.py` itself
is a CLI script that touches a live database and is never imported by a
`test_*.py` module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comparador  # noqa: E402  (path insert must precede this)


def test_identico_sem_diferencas():
    ref = ["Cláusula Primeira. O valor é de R$ 100.000,00.", "Cláusula Segunda. Nada mais."]
    resultado = comparador.comparar(ref, list(ref))
    assert resultado.identico
    assert resultado.similaridade == 1.0


def test_clausula_faltando():
    ref = ["Cláusula Primeira. Texto A.", "Cláusula Segunda. Texto B."]
    gerado = ["Cláusula Primeira. Texto A."]
    resultado = comparador.comparar(ref, gerado)
    assert not resultado.identico
    assert resultado.diferencas[0].tipo == "clausula_faltando"
    assert resultado.diferencas[0].ref == ["Cláusula Segunda. Texto B."]


def test_clausula_extra():
    ref = ["Cláusula Primeira. Texto A."]
    gerado = ["Cláusula Primeira. Texto A.", "Cláusula Extra. Não deveria estar aqui."]
    resultado = comparador.comparar(ref, gerado)
    assert resultado.diferencas[0].tipo == "clausula_extra"
    assert resultado.diferencas[0].gerado == ["Cláusula Extra. Não deveria estar aqui."]


def test_valor_errado_numero_diferente():
    ref = ["O valor total é de R$ 250.000,00 pago em 10 parcelas."]
    gerado = ["O valor total é de R$ 999.000,00 pago em 10 parcelas."]
    resultado = comparador.comparar(ref, gerado)
    assert len(resultado.diferencas) == 1
    assert resultado.diferencas[0].tipo == "valor_errado"


def test_formatacao_mesma_quebra_diferente():
    ref = ["Parágrafo único sobre entrega das chaves e vistoria final do imóvel adquirido."]
    gerado = [
        "Parágrafo único sobre entrega das chaves e",
        "vistoria final do imóvel adquirido.",
    ]
    resultado = comparador.comparar(ref, gerado)
    assert len(resultado.diferencas) == 1
    assert resultado.diferencas[0].tipo == "formatacao"


def test_clausula_diferente_nao_relacionada():
    ref = ["Cláusula sobre multa por atraso na entrega das chaves do imóvel."]
    gerado = ["Cláusula sobre foro de eleição da comarca de São Paulo."]
    resultado = comparador.comparar(ref, gerado)
    assert resultado.diferencas[0].tipo == "clausula_faltando_e_extra"


def test_paragrafos_de_lista_normaliza_espacos_e_descarta_vazios():
    entrada = ["  Texto   com   espaços  ", "", "   ", "Outro."]
    assert comparador.paragrafos_de_lista(entrada) == ["Texto com espaços", "Outro."]


def test_contagem_por_tipo():
    ref = ["A.", "B.", "C."]
    gerado = ["A.", "X.", "C.", "Extra."]
    resultado = comparador.comparar(ref, gerado)
    contagem = resultado.contagem_por_tipo()
    assert sum(contagem.values()) == len(resultado.diferencas)


# ─── scorecard (comparador.pontuar) — the enforced verdict ──────────────
#
# Every string below is invented. A synthetic contract shaped like the real
# instrument: preamble · numbered clauses · closing block.

import json  # noqa: E402

import pytest  # noqa: E402

_REF = [
    "INSTRUMENTO PARTICULAR DE PROMESSA DE VENDA E COMPRA",
    "De um lado, FULANO DE TAL, brasileiro, solteiro, inscrito no CPF sob nº 111.444.777-35, residente na Rua Fictícia, nº 10.",
    "CLÁUSULA PRIMEIRA – DO OBJETO",
    "IMÓVEL: MATRÍCULA Nº 12.345 - O apartamento nº 11 do Edifício Exemplo, com área privativa de 80,00 m2.",
    "CLÁUSULA SEGUNDA – DO PREÇO",
    "O preço certo e ajustado é de R$ 500.000,00 (quinhentos mil reais), pago no ato.",
    "CLÁUSULA TERCEIRA – DAS CERTIDÕES",
    "1 - Em nome de FULANO DE TAL",
    "1.1 – Certidão Negativa de Débitos Trabalhistas – nº SIM-0006 - emitida em 01/09/2026;",
    "1.2 – Certidão Negativa da Justiça Federal – nº SIM-0002 - emitida em 01/09/2026;",
    "CLÁUSULA QUARTA – DA ELEIÇÃO DO FORO",
    "As partes elegem o foro da Comarca de Cidade Exemplo para dirimir as questões deste instrumento.",
    "Cidade Exemplo, 14 de setembro de 2026.",
    "VENDEDOR",
]


def _troca(paragrafos, velho, novo):
    out = [p.replace(velho, novo) for p in paragrafos]
    assert out != paragrafos, f"fixture: {velho!r} not found"
    return out


def test_scorecard_identico_aprovado():
    card = comparador.pontuar(_REF, list(_REF))
    assert card.veredito == "aprovado", card.motivos()
    resumo = card.resumo()
    assert resumo["numeros_divergentes"] == 0
    assert resumo["clausulas_faltando"] == 0
    assert resumo["categorias"]["redacao"] == 1.0
    assert resumo["categorias"]["matricula"] == 1.0
    assert resumo["categorias"]["certidoes"] == 1.0


def test_scorecard_numero_inexplicado_reprova():
    """ONE digit of the price changes, wording identical → fail. Exact
    numbers are zero-tolerance; high wording similarity cannot hide it."""
    gerado = _troca(_REF, "R$ 500.000,00", "R$ 500.001,00")
    card = comparador.pontuar(_REF, gerado)
    assert card.veredito == "reprovado"
    assert card.numeros_divergentes == 2  # one missing, one extra
    assert any(m.startswith("numeros_divergentes") for m in card.motivos())
    assert card.categorias["redacao"] > 0.99  # wording is NOT what failed


def test_scorecard_cpf_inexplicado_reprova():
    gerado = _troca(_REF, "111.444.777-35", "111.444.777-36")
    card = comparador.pontuar(_REF, gerado)
    assert card.veredito == "reprovado"
    detalhe = card.detalhe()
    preambulo = next(s for s in detalhe["secoes"] if s["chave"] == "preambulo")
    assert preambulo["numeros_faltando_por_tipo"] == {"cpf": 1}


def test_scorecard_data_inexplicada_reprova():
    """A certidão's emission date is a fact: one day off → fail (one missing,
    one extra). (The signing-date line is NOT such a fact — see
    `test_data_de_assinatura_nao_e_divergencia`.)"""
    gerado = _troca(_REF, "SIM-0006 - emitida em 01/09/2026", "SIM-0006 - emitida em 02/09/2026")
    card = comparador.pontuar(_REF, gerado)
    assert card.veredito == "reprovado"
    assert card.datas_divergentes == 2


def test_scorecard_clausula_faltando_reprova():
    gerado = [p for p in _REF if "DO PREÇO" not in p and "preço certo" not in p]
    card = comparador.pontuar(_REF, gerado)
    assert card.veredito == "reprovado"
    assert card.clausulas_faltando == ["clausula:do preco"]
    assert card.categorias["estrutura"] == pytest.approx(3 / 4)
    # the missing clause's numbers are part of the missing-clause failure,
    # never double-counted as number diffs
    assert card.numeros_divergentes == 0


def test_scorecard_renumeracao_nao_e_clausula_faltando():
    gerado = _troca(_REF, "CLÁUSULA QUARTA", "CLÁUSULA QUINTA")
    assert comparador.pontuar(_REF, gerado).veredito == "aprovado"


def test_scorecard_clausula_extra_reprova_por_padrao():
    gerado = _REF[:10] + ["CLÁUSULA QUINTA – DA PROTEÇÃO DE DADOS", "As partes tratarão dados pessoais conforme a lei."] + _REF[10:]
    card = comparador.pontuar(_REF, gerado)
    assert card.clausulas_extras == ["clausula:da protecao de dados"]
    assert card.veredito == "reprovado"
    tolerante = comparador.Limiares(falhar_em_clausula_extra=False)
    assert comparador.pontuar(_REF, gerado, limiares=tolerante).veredito == "aprovado"


def test_scorecard_redacao_allowlistada_aprovada():
    """A deliberate template wording change in the foro clause: fails
    without the allowlist entry, passes with an owner-approved one, still
    fails with the same entry NOT approved."""
    gerado = _troca(_REF, "para dirimir as questões deste instrumento", "com renúncia a qualquer outro, por mais privilegiado que seja, para dirimir as questões oriundas deste instrumento")
    estrito = comparador.Limiares(secao_min=0.95)
    sem = comparador.pontuar(_REF, gerado, limiares=estrito)
    assert sem.veredito == "reprovado"
    assert sem.motivos() == ["secoes_abaixo_do_limiar:1"]

    entrada = {
        "id": "foro-renuncia",
        "categoria": "redacao",
        "secao": "^clausula:.*foro",
        "padrao_ref": r"para dirimir as questoes deste instrumento",
        "padrao_gerado": r"com renuncia a qualquer outro, por mais privilegiado que seja, para dirimir as questoes oriundas deste instrumento",
        "motivo": "template adds the standard foro renúncia wording",
        "aprovado_pelo_dono": True,
    }
    com = comparador.pontuar(_REF, gerado, allowlist=comparador.validar_allowlist([entrada]), limiares=estrito)
    assert com.veredito == "aprovado", com.motivos()
    assert com.allowlist_aplicadas == {"foro-renuncia": 2}

    pendente = comparador.pontuar(
        _REF, gerado, allowlist=comparador.validar_allowlist([{**entrada, "aprovado_pelo_dono": False}]), limiares=estrito
    )
    assert pendente.veredito == "reprovado"
    assert pendente.resumo()["allowlist_pendentes"] == 1


def test_scorecard_allowlist_nao_explica_numero_fora_do_padrao():
    """An allowlisted wording span does not launder a number diff elsewhere."""
    gerado = _troca(_REF, "R$ 500.000,00", "R$ 499.000,00")
    entrada = {
        "id": "qualquer", "categoria": "redacao", "secao": "^clausula:.*foro",
        "padrao_ref": "comarca", "padrao_gerado": "comarca",
        "motivo": "x", "aprovado_pelo_dono": True,
    }
    card = comparador.pontuar(_REF, gerado, allowlist=comparador.validar_allowlist([entrada]))
    assert card.veredito == "reprovado"


def test_scorecard_clausula_faltando_allowlistada():
    gerado = [p for p in _REF if "DO PREÇO" not in p and "preço certo" not in p]
    entrada = {
        "id": "sem-preco", "categoria": "clausula_faltando", "padrao_ref": "^clausula:do preco$",
        "motivo": "synthetic", "aprovado_pelo_dono": True,
    }
    card = comparador.pontuar(_REF, gerado, allowlist=comparador.validar_allowlist([entrada]))
    assert card.clausulas_faltando == []
    assert card.veredito == "aprovado", card.motivos()


def test_scorecard_lacuna_e_gap_nao_diferenca():
    """A not-pronto render carries the gap marker where the CPF would be:
    reported as a gap (`incompleto`), never as a number/wording failure."""
    gerado = _troca(_REF, "111.444.777-35", comparador.MARCADOR_LACUNA)
    card = comparador.pontuar(_REF, gerado)
    assert card.veredito == "incompleto", card.motivos()
    resumo = card.resumo()
    assert resumo["lacunas"] == 1
    assert resumo["numeros_em_lacuna"] == 1
    assert resumo["numeros_divergentes"] == 0


def test_scorecard_lacuna_nao_mascara_outro_erro():
    gerado = _troca(_troca(_REF, "111.444.777-35", comparador.MARCADOR_LACUNA), "R$ 500.000,00", "R$ 1,00")
    assert comparador.pontuar(_REF, gerado).veredito == "reprovado"


def test_scorecard_certidao_que_o_cartao_nao_tem_e_lacuna():
    """The generator prints the certidões the CARD carries. A signed-text
    certidão with no counterpart is a data gap (`incompleto`) — counted apart,
    never a divergence and never a drag on the certidões ratio or on wording."""
    gerado = [p for p in _REF if not p.startswith("1.2 ")]
    card = comparador.pontuar(_REF, gerado)
    assert card.certidoes_lacuna == 1
    assert card.categorias["certidoes"] == 1.0
    assert card.numeros_divergentes == 0 and card.datas_divergentes == 0
    assert card.veredito == "incompleto", card.motivos()
    assert card.resumo()["certidoes_lacuna"] == 1


def test_scorecard_certidao_inventada_reprova():
    """A certidão KIND the signed text does not list is a fact the generated
    contract states on its own: the ratio of printed-and-listed kinds drops."""
    gerado = list(_REF)
    gerado.insert(10, "1.3 – Certidão Negativa de Débitos Municipais – nº SIM-0009 - emitida em 01/09/2026;")
    card = comparador.pontuar(_REF, gerado)
    assert card.categorias["certidoes"] == pytest.approx(2 / 3)
    assert "certidoes_abaixo_do_limiar" in card.motivos()
    assert card.certidoes_extras == 1


def test_scorecard_identificador_de_certidao_diferente_reprova():
    gerado = _troca(_REF, "SIM-0002", "SIM-0003")
    card = comparador.pontuar(_REF, gerado)
    assert card.veredito == "reprovado"
    assert card.numeros_divergentes == 2


def test_scorecard_itens_de_certidao_colados_pelo_pdf():
    """A PDF text layer glues two list items into one paragraph: still two items."""
    ref = list(_REF)
    ref[8:10] = [ref[8] + " " + ref[9]]
    card = comparador.pontuar(ref, list(_REF))
    assert card.numeros_divergentes == 0 and card.datas_divergentes == 0, card.detalhe()["secoes"]
    assert card.veredito == "aprovado", card.motivos()


def test_scorecard_resumo_sem_valores():
    """The verdict-level summary never carries a value from either text."""
    gerado = _troca(_REF, "R$ 500.000,00", "R$ 777.000,00")
    texto = json.dumps(comparador.pontuar(_REF, gerado).resumo(), ensure_ascii=False)
    for valor in ("500", "777", "111.444", "FULANO", "12.345", "Fictícia"):
        assert valor not in texto
    detalhe = json.dumps(comparador.pontuar(_REF, gerado).detalhe(), ensure_ascii=False)
    for valor in ("500", "777", "111.444", "FULANO", "12.345"):
        assert valor not in detalhe


def test_extrair_numeros_normaliza():
    datas, numeros = comparador.extrair_numeros("Em 1º de março de 2026 e 02/03/2026, R$ 1.000,00 e CPF 111.444.777-35")
    assert datas == {"data:2026-03-01": 1, "data:2026-03-02": 1}
    assert numeros["valor:1000.00"] == 1
    assert numeros["cpf:11144477735"] == 1


@pytest.mark.parametrize(
    "entrada,erro",
    [
        ({"id": "a", "categoria": "redacao", "padrao_ref": "cpf 11144477735", "motivo": "m", "aprovado_pelo_dono": True}, "valor real"),
        ({"id": "a", "categoria": "redacao", "padrao_ref": "fulano@x.test", "motivo": "m", "aprovado_pelo_dono": True}, "valor real"),
        ({"id": "a", "categoria": "nada", "padrao_ref": "x", "motivo": "m", "aprovado_pelo_dono": True}, "categoria"),
        ({"id": "a", "categoria": "redacao", "motivo": "m", "aprovado_pelo_dono": True}, "padrao"),
        ({"id": "a", "categoria": "redacao", "padrao_ref": "x", "motivo": " ", "aprovado_pelo_dono": True}, "motivo"),
        ({"id": "a", "categoria": "redacao", "padrao_ref": "x", "motivo": "m"}, "aprovado_pelo_dono"),
    ],
)
def test_validar_allowlist_recusa(entrada, erro):
    with pytest.raises(ValueError, match=erro):
        comparador.validar_allowlist([entrada])


def test_allowlist_versionada_e_valida():
    """The committed allowlist + thresholds parse (and therefore carry no
    digit-run/e-mail pattern)."""
    comparador.carregar_allowlist()
    lim = comparador.Limiares.de_arquivo()
    assert lim.max_numeros_divergentes == 0
    assert lim.max_datas_divergentes == 0


def test_limiares_recusa_chave_desconhecida():
    with pytest.raises(ValueError, match="desconhecidas"):
        comparador.Limiares.de_dict({"redacao_minimo": 0.5})


def test_cli_exit_code(tmp_path):
    ref = tmp_path / "ref.txt"
    gen = tmp_path / "gen.txt"
    ref.write_text("\n".join(_REF), encoding="utf-8")
    gen.write_text("\n".join(_REF), encoding="utf-8")
    assert comparador.main(["--ref", str(ref), "--gerado", str(gen)]) == 0
    gen.write_text("\n".join(_troca(_REF, "R$ 500.000,00", "R$ 5,00")), encoding="utf-8")
    assert comparador.main(["--ref", str(ref), "--gerado", str(gen)]) == 1


def test_sentinelas_estruturais_sao_lacunas():
    """R$ 0,01 / 01/01/1900 / 999 are the harness's required-value stand-ins:
    gaps, never number/date diffs."""
    gerado = _troca(_REF, "R$ 500.000,00 (quinhentos mil reais)", "R$ 0,01 (um centavo)")
    gerado = _troca(gerado, "1.1 – Certidão Negativa de Débitos Trabalhistas – nº SIM-0006 - emitida em 01/09/2026;",
                    "1.1 – Certidão Negativa de Débitos Trabalhistas – nº SIM-0006 - emitida em 01/01/1900;")
    card = comparador.pontuar(_REF, gerado)
    assert card.numeros_divergentes == 0 and card.datas_divergentes == 0, card.detalhe()["secoes"]
    assert card.lacunas == 2
    assert card.veredito == "incompleto", card.motivos()


def test_clausula_desligada_e_gap_de_dado_nao_faltando():
    """The reference has a clause the generator switched OFF for this card
    (e.g. intermediação with no corretagem data): a DATA gap (`incompleto`),
    not a missing-clause failure. Without the switch information the same
    absence is a missing clause."""
    gerado = [p for p in _REF if "DO PREÇO" not in p and "preço certo" not in p]
    sem = comparador.pontuar(_REF, gerado)
    assert sem.clausulas_faltando == ["clausula:do preco"]
    com = comparador.pontuar(_REF, gerado, clausulas_desligadas=["DO PREÇO"])
    assert com.clausulas_faltando == []
    assert com.clausulas_desligadas == ["clausula:do preco"]
    assert com.veredito == "incompleto", com.motivos()
    assert com.resumo()["clausulas_desligadas"] == 1
    assert com.categorias["estrutura"] == 1.0


def test_clausula_desligada_nao_cobre_outra_clausula():
    gerado = [p for p in _REF if "DO PREÇO" not in p and "preço certo" not in p]
    card = comparador.pontuar(_REF, gerado, clausulas_desligadas=["DA INTERMEDIAÇÃO"])
    assert card.clausulas_faltando == ["clausula:do preco"]
    assert card.veredito == "reprovado"


# ─── honest comparison (2026-10-05 audit) ───────────────────────────────
#
# The divergence-email lesson (~56 % of "divergences" were formatting /
# alignment / low-confidence noise) applied to the scorer. Each test pairs a
# FALSE class (must no longer count) with the TRUE twin (must still count).
# Every value is invented.


def _doc(*corpo: str) -> list[str]:
    """A minimal instrument: preamble + one clause (+ the caller's lines)."""
    return ["INSTRUMENTO DE TESTE", "De um lado, FULANO DE TAL, brasileiro.", "CLÁUSULA PRIMEIRA – DO OBJETO", *corpo]


def _sem_divergencia(ref: list[str], gerado: list[str]) -> comparador.Scorecard:
    card = comparador.pontuar(ref, gerado)
    assert card.numeros_divergentes == 0 and card.datas_divergentes == 0, card.detalhe()["secoes"]
    return card


@pytest.mark.parametrize(
    "ref,gerado",
    [
        # identifiers: punctuation is format
        ("CPF 111.444.777-35.", "CPF 11144477735."),
        ("CEP: 01310-100.", "CEP: 01310- 100."),
        ("CNPJ 11.222.333/0001-81.", "CNPJ 11222333000181."),
        # money / areas / decimals
        ("área de 170,00m2 e 7,07 m.", "área de 170,000 m² e 7,07m."),
        ("fração ideal 0,745556%.", "fração ideal 0,7455560%."),
        ("pagará R$ 470.000,00 (470.000,00 mil reais).", "pagará R$ 470.000,00 (quatrocentos e setenta mil reais)."),
        # dates: numeric vs extenso
        ("emitida em 01/09/2026.", "emitida em 1º de setembro de 2026."),
        # leading zeros, ordinals, thousand dots, spaced groups
        ("Parcela 01 e contrato nº 0430.", "Parcela 1 e contrato nº 430."),
        ("matrícula 86.743 e 2º ofício.", "matrícula 86743 e 2 ofício."),
        ("raiz 59.884.041.", "raiz 59 884 041."),
        ("inscrição 23253.41.85.0055.0000.", "inscrição 23253-41-85-0055-0000."),
        ("protocolo 449220 / 2026.", "protocolo 449220/2026."),
        # fill-in blanks of the template
        ("lote número 31, quadra 26.", "lote número __31____, quadra __26__."),
    ],
)
def test_formato_nao_e_divergencia(ref, gerado):
    _sem_divergencia(_doc(ref), _doc(gerado))


@pytest.mark.parametrize(
    "ref,gerado",
    [
        ("CPF 111.444.777-35.", "CPF 111.444.777-36."),
        ("área de 170,00m2.", "área de 17,00m2."),
        ("área de 11,500m2.", "área de 11.500m2."),  # pt-BR reads the dot as thousands: another figure
        ("fração ideal 0,745556%.", "fração ideal 0,7455506%."),
        ("lote número 31.", "lote número 32."),
        ("emitida em 01/09/2026.", "emitida em 02/09/2026."),
        ("CEP: 01310-100.", "CEP: 08310-100."),
    ],
)
def test_valor_diferente_continua_divergindo(ref, gerado):
    card = comparador.pontuar(_doc(ref), _doc(gerado))
    assert card.numeros_divergentes + card.datas_divergentes >= 2, ref


def test_rg_sem_digito_verificador_e_o_mesmo_rg():
    """The signed text omits the RG check digit; the SP check digit is
    deterministic (seed identifier registry), so it is the SAME identifier. A
    different number is still a divergence."""
    ref = _doc("portador do RG 12.345.678-SSP-SP.")
    _sem_divergencia(ref, _doc("portador do RG 12.345.678-2-SSP-SP."))
    errado = comparador.pontuar(ref, _doc("portador do RG 12.345.679-SSP-SP."))
    assert errado.numeros_divergentes == 2


def test_email_enumerador_e_referencia_de_item_nao_sao_numeros():
    ref = _doc("e-mail fulano.2@exemplo.test.", "1.10 – Item de lista.", "Esclarecimentos sobre os itens 1.7, 1.9 e 2.10.")
    gerado = _doc("e-mail teste-p3-876@exemplo.test.", "1.9 – Item de lista.")
    _sem_divergencia(ref, gerado)


def test_mencao_em_outra_clausula_e_alinhamento():
    """The same (specific) value, stated in another clause, is alignment — counted,
    not a wrong fact. A bare small number moved around is NOT given that benefit."""
    ref = ["INSTRUMENTO DE TESTE", "CLÁUSULA PRIMEIRA – DO OBJETO", "Imóvel de matrícula 86.743.", "CLÁUSULA SEGUNDA – DO PREÇO", "Preço de R$ 500.000,00."]
    gerado = ["INSTRUMENTO DE TESTE", "CLÁUSULA PRIMEIRA – DO OBJETO", "Imóvel.", "CLÁUSULA SEGUNDA – DO PREÇO", "Preço de R$ 500.000,00 (matrícula 86.743)."]
    card = comparador.pontuar(ref, gerado)
    assert card.numeros_divergentes == 0
    assert card.numeros_alinhados == 2

    pequeno_ref = ["INSTRUMENTO DE TESTE", "CLÁUSULA PRIMEIRA – DO OBJETO", "Apartamento 81.", "CLÁUSULA SEGUNDA – DO PREÇO", "Preço certo, vaga 81."]
    pequeno_gen = ["INSTRUMENTO DE TESTE", "CLÁUSULA PRIMEIRA – DO OBJETO", "Apartamento.", "CLÁUSULA SEGUNDA – DO PREÇO", "Preço certo, vaga 81."]
    assert comparador.pontuar(pequeno_ref, pequeno_gen).numeros_divergentes == 1


def test_valor_repetido_so_na_referencia_nao_e_divergencia_mas_o_valor_trocado_e():
    """A value the signed text repeats in extra paragraphs is one fact (distinct
    values per section, not occurrence counts)."""
    ref = _doc("Pagará R$ 760.000,00.", "Parágrafo Primeiro: no mínimo R$ 760.000,00.", "Parágrafo Segundo: R$ 760.000,00 em 60 dias.")
    gerado = _doc("Pagará R$ 760.000,00.", "Parágrafo Primeiro: no mínimo R$ 760.000,00.", "Parágrafo Segundo: em 60 dias.")
    _sem_divergencia(ref, gerado)
    assert comparador.pontuar(ref, _troca(gerado, "R$ 760.000,00.", "R$ 761.000,00.")).numeros_divergentes > 0


def test_parcela_com_outro_valor_diverge_mesmo_com_os_mesmos_valores():
    """Two amounts swapped between installments pass a bare set-of-values
    comparison — the installment→amount pair is a fact of its own."""
    ref = _doc("Parcela 01: R$ 50.000,00 no ato.", "Parcela 02: R$ 400.000,00 na assinatura.")
    gerado = _doc("Parcela 01: R$ 400.000,00 na assinatura.", "Parcela 02: R$ 50.000,00 no ato.")
    card = comparador.pontuar(ref, gerado)
    assert card.numeros_divergentes == 4  # two pairs missing, two extra
    _sem_divergencia(ref, list(ref))


def test_lacuna_tipada_nao_esconde_rg_errado():
    """A `[[LACUNA]]` after `CPF` stands for a CPF — it must not absorb the
    divergence of an RG the render printed WRONG."""
    ref = _doc("RG 12.345.678-2 e CPF 111.444.777-35.")
    gerado = _doc(f"RG 87.654.321-0 e CPF {comparador.MARCADOR_LACUNA}.")
    card = comparador.pontuar(ref, gerado)
    assert card.resumo()["numeros_em_lacuna"] == 1  # the CPF
    assert card.numeros_divergentes == 2  # the wrong RG: one missing + one extra
    assert card.veredito == "reprovado"


def test_dados_bancarios_do_favorecido_sao_lacuna_esperada():
    """The owner cannot supply the favorecido's bank account: the signed
    sentence's CPF/banco/agência/conta are an expected gap (`incompleto`) — not
    a divergence and not a wording failure. Bank details the render DOES print
    but wrong still diverge."""
    banco = "em favor do VENDEDOR: Fulano de Tal, CPF: 111.444.777-35, Banco 341, Agência 3767, Conta Corrente 24564-4, operando-se a quitação."
    ref = _doc("Parcela 01: R$ 100.000,00 por TED " + banco)
    gerado = _doc("Parcela 01: R$ 100.000,00 por TED operando-se a quitação.")
    card = comparador.pontuar(ref, gerado)
    assert card.numeros_divergentes == 0, card.detalhe()["secoes"]
    assert card.dados_indisponiveis >= 4
    assert card.veredito == "incompleto", card.motivos()
    assert card.categorias["redacao"] > 0.95
    errado = _troca(ref, "Agência 3767", "Agência 9999")
    com_banco_errado = comparador.pontuar(errado, _doc("Parcela 01: R$ 100.000,00 por TED " + banco))
    assert com_banco_errado.numeros_divergentes == 2 and com_banco_errado.dados_indisponiveis == 0


def test_bloco_de_assinatura_data_de_render_e_tipos_de_identificador():
    """The signing-date line carries the RENDER date, and the signed block
    lists witness RGs where the render lists CPFs: neither is a wrong fact."""
    ref = _doc("Corpo.", "Cidade Exemplo, 14 de setembro de 2026.", "TESTEMUNHAS", "BELTRANA DE TAL RG 12.345.678-2")
    gerado = _doc("Corpo.", "Cidade Exemplo, 05 de outubro de 2026.", "TESTEMUNHAS:", "BELTRANA DE TAL CPF 111.444.777-35")
    card = _sem_divergencia(ref, gerado)
    assert card.assinatura_excluidos >= 3
    # …but an identifier kind BOTH blocks print is compared strictly
    ref2 = _doc("Corpo.", "Cidade Exemplo, 14 de setembro de 2026.", "BELTRANA DE TAL CPF 111.444.777-35")
    gen2 = _doc("Corpo.", "Cidade Exemplo, 05 de outubro de 2026.", "BELTRANA DE TAL CPF 111.444.777-36")
    assert comparador.pontuar(ref2, gen2).numeros_divergentes == 2


def test_data_de_assinatura_nao_e_divergencia():
    gerado = _troca(_REF, "14 de setembro de 2026", "15 de setembro de 2026")
    card = comparador.pontuar(_REF, gerado)
    assert card.datas_divergentes == 0
    assert card.assinatura_excluidos == 2
    assert card.veredito == "aprovado", card.motivos()


def _cert(pessoa: str, *itens: str) -> list[str]:
    return [f"CLÁUSULA TERCEIRA – DAS CERTIDÕES", f"1 - Em nome de {pessoa}", *itens]


def test_certidao_reemitida_e_esperada_nao_falha():
    """Same kind, same person, another identifier AND another emission date:
    the card holds a NEWER certidão than the signed text listed."""
    ref = _doc("Texto.") + _cert("BELTRANA DE TAL", "1.1 – Certidão Negativa Federal – nº AAA-0001 - emitida em 01/09/2026;")
    gerado = _doc("Texto.") + _cert("BELTRANA DE TAL", "1.1 – Certidão Negativa Federal – nº AAA-0002 - emitida em 20/09/2026;")
    card = _sem_divergencia(ref, gerado)
    assert card.resumo()["certidoes_reemitidas"] == 1
    # the same emission date with another identifier is a wrong fact
    mesmo_dia = _doc("Texto.") + _cert("BELTRANA DE TAL", "1.1 – Certidão Negativa Federal – nº AAA-0002 - emitida em 01/09/2026;")
    assert comparador.pontuar(ref, mesmo_dia).numeros_divergentes == 2


def test_certidoes_pareadas_por_pessoa_e_nao_por_posicao():
    """Persons listed in another order still pair person-to-person; a person
    the card has no certidão for is a GAP, a person only the render lists is an
    extra (lowers the ratio) — neither inflates number divergences."""
    a = "1.1 – Certidão Negativa Federal – nº AAA-0001 - emitida em 01/09/2026;"
    b = "2.1 – Certidão Negativa Federal – nº BBB-0002 - emitida em 01/09/2026;"
    ref = _doc("Texto.") + ["CLÁUSULA TERCEIRA – DAS CERTIDÕES", "1 - Em nome de BELTRANA DE TAL", a, "2 - Em nome de CICRANO DE TAL", b]
    gerado = _doc("Texto.") + ["CLÁUSULA TERCEIRA – DAS CERTIDÕES", "1 - Em nome de CICRANO DE TAL", b.replace("2.1", "1.1"), "2 - Em nome de BELTRANA DE TAL", a.replace("1.1", "2.1")]
    card = _sem_divergencia(ref, gerado)
    assert card.categorias["certidoes"] == 1.0 and card.certidoes_lacuna == 0
    so_um = _doc("Texto.") + ["CLÁUSULA TERCEIRA – DAS CERTIDÕES", "1 - Em nome de BELTRANA DE TAL", a]
    card_gap = comparador.pontuar(ref, so_um)
    assert card_gap.certidoes_lacuna == 1 and card_gap.numeros_divergentes == 0 and card_gap.veredito == "incompleto"
    extra = _doc("Texto.") + ["CLÁUSULA TERCEIRA – DAS CERTIDÕES", "1 - Em nome de BELTRANA DE TAL", a, "2 - Em nome de FULANO ESTRANHO", b]
    card_extra = comparador.pontuar(_doc("Texto.") + ["CLÁUSULA TERCEIRA – DAS CERTIDÕES", "1 - Em nome de BELTRANA DE TAL", a], extra)
    assert card_extra.certidoes_extras == 1 and card_extra.numeros_divergentes == 0
    assert card_extra.categorias["certidoes"] == pytest.approx(0.5)


def test_redacao_nao_e_arrastada_por_certidao_sem_contraparte():
    """Reference certidões the card does not carry are out of the wording score
    (they used to read as 'missing words' and sink the clause)."""
    muitas = [f"1.{i} – Certidão Negativa Tipo{chr(96 + i)} – nº ZZ-{i:04d} - emitida em 01/09/2026;" for i in range(1, 9)]
    ref = _doc("Texto.") + ["CLÁUSULA TERCEIRA – DAS CERTIDÕES", "1 - Em nome de BELTRANA DE TAL", *muitas]
    gerado = _doc("Texto.") + ["CLÁUSULA TERCEIRA – DAS CERTIDÕES", "1 - Em nome de BELTRANA DE TAL", muitas[0]]
    card = comparador.pontuar(ref, gerado)
    secao = next(s for s in card.detalhe()["secoes"] if "certid" in s["chave"])
    assert secao["redacao"] > 0.95 and card.certidoes_lacuna == 7
    assert card.categorias["certidoes"] == 1.0


def test_email_nao_conta_como_palavra():
    """A test card carries stand-in e-mail addresses: wording must not read them."""
    ref = _doc("com endereço eletrônico: fulano.real@exemplo.test, residente em Cidade.")
    gerado = _doc("com endereço eletrônico: teste-p3-1@exemplo.test, residente em Cidade.")
    assert comparador.pontuar(ref, gerado).categorias["redacao"] == 1.0
