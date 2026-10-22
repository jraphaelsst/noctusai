"""SP certidão de casamento, two spouses, the "nome que cada um passou a
utilizar" block repeating each spouse's own name (deal 799, prod, 2026-10-22).

`passará a usar o nome de X` made the NOME label capture "DE X" as a second,
distinct holder, so the couple read as FOUR names and no cônjuge was created.
Invented names, synthetic CPFs.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.conjuges import find_conjuges
from noctusai_lib.integrations.documents.name import find_name_conflitos

CERTIDAO = (
    "CERTIDÃO DE CASAMENTO\n\n"
    "LUCIANA ARAUJO TEIXEIRA DE MELO\n\nCPF\n529.982.247-25\n\n"
    "RENATA BORGES CAVALCANTE\n\nCPF\n111.444.777-35\n\n"
    "MATRÍCULA\n000000 01 55 2019 2 00001 001 0000001-00\n\n"
    "NOMES COMPLETOS DE SOLTEIRO, DATAS DE NASCIMENTO, NATURALIDADE, "
    "NACIONALIDADE E FILIAÇÕES DOS CÔNJUGES\n\n"
    "LUCIANA ARAUJO TEIXEIRA DE MELO, nascida no dia cinco de junho de mil "
    "novecentos e noventa e um (05/06/1991), em São Paulo, SP, nacionalidade "
    "brasileira, solteira, filha de PAULO TEIXEIRA DE MELO e de ANA ARAUJO.\n\n"
    "RENATA BORGES CAVALCANTE, nascida no dia vinte e sete de março de mil "
    "novecentos e oitenta e três (27/03/1983), em São Paulo, SP, nacionalidade "
    "brasileira, solteira, filha de JOSE CAVALCANTE e de MARIA BORGES.\n\n"
    "DATA DE REGISTRO DO CASAMENTO POR EXTENSO\n\nQUATRO DE OUTUBRO DE DOIS MIL E DEZENOVE\n\n"
    "REGIME DE BENS DO CASAMENTO\n\nCOMUNHÃO PARCIAL DE BENS\n\n"
    "NOME QUE CADA UM DOS CÔNJUGES PASSOU A UTILIZAR (QUANDO HOUVER ALTERAÇÃO)\n\n"
    "LUCIANA ARAUJO TEIXEIRA DE MELO, passará a usar o nome de LUCIANA ARAUJO TEIXEIRA DE MELO.\n"
    "RENATA BORGES CAVALCANTE, passará a usar o nome de RENATA BORGES CAVALCANTE.\n\n"
    "ANOTAÇÕES DE CADASTRO\n\n"
    "LUCIANA ARAUJO TEIXEIRA DE MELO: SEM INFORMAÇÃO.\n"
    "RENATA BORGES CAVALCANTE: SEM INFORMAÇÃO.\n"
)


def test_adopted_name_particle_is_not_a_third_and_fourth_holder():
    assert find_name_conflitos(CERTIDAO) == [
        "LUCIANA ARAUJO TEIXEIRA DE MELO",
        "RENATA BORGES CAVALCANTE",
    ]


def test_both_spouses_are_found_with_their_own_facts():
    luciana, renata = sorted(find_conjuges(CERTIDAO), key=lambda c: c.nome)
    assert luciana.nome == "LUCIANA ARAUJO TEIXEIRA DE MELO"
    assert luciana.cpf == "529.982.247-25"
    assert str(luciana.data_nascimento) == "1991-06-05"
    assert renata.nome == "RENATA BORGES CAVALCANTE"
    assert renata.cpf == "111.444.777-35"
    assert str(renata.data_nascimento) == "1983-03-27"
