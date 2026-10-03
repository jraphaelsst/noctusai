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
    gerado = _troca(_REF, "14 de setembro de 2026", "15 de setembro de 2026")
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


def test_scorecard_certidao_faltando_reprova():
    gerado = [p for p in _REF if not p.startswith("1.2 ")]
    card = comparador.pontuar(_REF, gerado)
    assert card.categorias["certidoes"] == pytest.approx(0.5)
    assert "certidoes_abaixo_do_limiar" in card.motivos()


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
