"""Certidao de casamento, SP 2a via, regime "COMUNHAO DE BENS" sem qualificador
(real, deal 799, 2026-10-22; texto abaixo SINTETICO, nomes/CPFs inventados).

Tres falhas: (1) a data por extenso "um mil e novecentos e setenta e sete"
tem 8 palavras e o regex a cortava em "setenta" -> 1970; (2) "comunhao de bens"
puro (regime legal pre-Lei 6.515/77, em vigor 1977-12-26) nao era lido; (3)
sem regime nem rotulo, estado civil ficava nulo numa certidao de casamento
sem averbacao de divorcio/obito.
"""
from __future__ import annotations

from datetime import date

from noctusai_lib.integrations.documents.civil_status import (
    find_data_casamento,
    find_estado_civil,
    find_estado_civil_certidao_casamento,
    find_regime_bens,
)

BASE = """CERTIDÃO DE CASAMENTO
NOME ATUAL DOS CÔNJUGES:
NÚMERO DO CPF
RICARDO AUGUSTO TAVARES
111.444.777-35
FLAVIA REGINA TAVARES
529.982.247-25
Matrícula
123456 01 55 1977 2 00123 045 0012345 67
1º Cônjuge:
Data de nascimento
Nome no momento da habilitação
RICARDO AUGUSTO TAVARES
Dia
12
Mês
08
Ano
1949
Nacionalidade
brasileira
Estado Civil
solteiro
Nome que passou a utilizar
RICARDO AUGUSTO TAVARES
2º Cônjuge:
Data de nascimento
Nome no momento da habilitação
FLAVIA REGINA SOUZA
Dia
23
Mês
04
Ano
1953
Estado Civil
solteira
Nome que passou a utilizar
FLAVIA REGINA TAVARES
Data da celebração do casamento ou, se for o caso de conversão da união estável, data do registro
trinta de abril de um mil e novecentos e setenta e sete
Dia
30
Mês
04
Ano
1977
Regime de bens
COMUNHÃO DE BENS
Data de registro do casamento
trinta de abril de um mil e novecentos e setenta e sete
Dia
30
Mês
04
Ano
1977
Anotações/Averbações
Registro feito no livro B-0008, às folhas 083, sob o n° 1679. Aos 08/03/2019, de acordo com o Provimento nº 63, de 14/11/2017-CNJ, faço constar no assento, o número do CPF dos contraentes.
"""


def _pos(texto: str) -> str:
    return (
        texto.replace("setenta e sete", "oitenta e oito")
        .replace("1977", "1988")
        .replace("00123 045", "00123 045")
    )


def test_data_por_extenso_longa_concorda_com_as_celulas():
    assert find_data_casamento(BASE)[0] == date(1977, 4, 30)


def test_comunhao_de_bens_pre_lei_6515_e_universal():
    valor, conf, _ = find_regime_bens(BASE)
    assert (valor, conf) == ("comunhao_universal", "alta")


def test_comunhao_de_bens_pos_lei_6515_e_ambigua_nunca_chutada():
    valor, conf, rotulo = find_regime_bens(_pos(BASE))
    assert (valor, conf) == (None, "nenhuma")
    assert "AMBIGUO" in rotulo


def test_comunhao_parcial_qualificada_segue_igual():
    valor, conf, _ = find_regime_bens(BASE.replace("COMUNHÃO DE BENS", "COMUNHÃO PARCIAL DE BENS"))
    assert (valor, conf) == ("comunhao_parcial", "alta")


def test_estado_civil_casado_via_regime_legal():
    assert find_estado_civil(BASE)[:2] == ("casado", "alta")


def test_certidao_casamento_sem_averbacao_e_casada_mesmo_com_regime_ambiguo():
    assert find_estado_civil(_pos(BASE))[0] is None
    assert find_estado_civil_certidao_casamento(_pos(BASE))[:2] == ("casado", "alta")


def test_averbacao_de_divorcio_barra_a_inferencia():
    texto = _pos(BASE) + "\nAverbado o divorcio em 10/01/2000.\n"
    assert find_estado_civil_certidao_casamento(texto)[0] != "casado"
