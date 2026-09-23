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
