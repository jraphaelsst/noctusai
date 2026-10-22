"""RG+CPF stated in an averbação completes a CNH's RG (synthetic numbers)."""

from noctusai_lib.integrations.documents.rg_averbacao import (
    completar_rg_cnh,
    find_rg_cpf_averbacao,
)

CPF = "529.982.247-25"  # valid synthetic CPF
TEXTO = (
    f"AV.3 - Consta que o número do RG de FULANO DE TAL EXEMPLO é 12.345.678-9 "
    f"e o do CPF é {CPF}, residente em São Paulo."
)


def test_extrai_nome_rg_cpf():
    (p,) = find_rg_cpf_averbacao(TEXTO)
    assert (p.nome, p.rg, p.cpf) == ("FULANO DE TAL EXEMPLO", "123456789", "52998224725")


def test_cpf_invalido_nao_conta():
    assert find_rg_cpf_averbacao(TEXTO.replace(CPF, "111.111.111-11")) == ()


def test_dv_x():
    (p,) = find_rg_cpf_averbacao(TEXTO.replace("12.345.678-9", "12.345.678-X"))
    assert p.rg == "12345678X"


def test_completa_quando_cpf_e_prefixo_batem():
    pares = find_rg_cpf_averbacao(TEXTO)
    assert completar_rg_cnh("12345678", CPF, pares) == "123456789"
    assert completar_rg_cnh("12.345.678", "52998224725", pares) == "123456789"


def test_nao_completa_com_cpf_ou_prefixo_diferente():
    pares = find_rg_cpf_averbacao(TEXTO)
    assert completar_rg_cnh("12345678", "111.444.777-35", pares) is None
    assert completar_rg_cnh("87654321", CPF, pares) is None
    assert completar_rg_cnh(None, CPF, pares) is None
