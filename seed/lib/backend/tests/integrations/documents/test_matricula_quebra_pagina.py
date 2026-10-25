"""Page-continuation furniture inside an act (F104) + "vendeu a parte ideal" (F97)."""
from __future__ import annotations

from noctusai_lib.integrations.documents import extrair_detalhes_ato, extrair_qualificacoes
from noctusai_lib.integrations.documents.matricula_ruido import neutralizar_quebra_pagina
from tests.integrations.documents.test_matricula_qualificacao import _cpf_sintetico, _fmt_cpf

CPF = _fmt_cpf(_cpf_sintetico("123456789"))

ATO_QUEBRADO = (
    "R.06, em 10 de maio de 2021.\n\nVENDA E COMPRA\n\n"
    "Pelo instrumento particular com força de escritura pública, firmado aos 30 de "
    "abril de 2021, em São Paulo-SP, a proprietária EMPRESA EXEMPLO LTDA, já qualificada, "
    "transmitiu o\n\ncontinua no verso\n\nMOD. 10\n\n"
    f"imóvel desta matrícula a CARLOS EXEMPLO SILVA, brasileiro, divorciado, piloto, "
    f"RG nº 11.222.333-4-SSP/SP, CPF nº {CPF}, residente e domiciliado na Rua Um, 10, "
    "pelo valor de R$ 100.000,00."
)


def test_neutralizar_preserva_tamanho_e_remove_mobiliario():
    out = neutralizar_quebra_pagina(ATO_QUEBRADO)
    assert len(out) == len(ATO_QUEBRADO)
    assert "continua" not in out and "MOD." not in out
    assert "transmitiu o" in out


def test_qualificacao_do_adquirente_apos_quebra():
    (q,) = [x for x in extrair_qualificacoes(ATO_QUEBRADO, 0, len(ATO_QUEBRADO)) if x.cpf_cnpj == CPF]
    assert q.nome == "CARLOS EXEMPLO SILVA"
    assert q.estado_civil == "divorciado"
    assert q.profissao == "piloto"
    assert q.rg


def test_adquirente_parseado_e_referencia_posterior_resolve_cpf():
    d = extrair_detalhes_ato(ATO_QUEBRADO)
    assert [p.nome for p in d.adquirentes] == ["CARLOS EXEMPLO SILVA"]
    assert d.adquirentes[0].cpf_cnpj == CPF
    posterior = (
        "R.09, em 10 de maio de 2023.\n\nVENDA E COMPRA\n\n"
        "O proprietário CARLOS EXEMPLO SILVA, já qualificado, vendeu o imóvel desta "
        "matrícula a MARIA EXEMPLO COSTA, brasileira, solteira, advogada, "
        f"CPF nº {_fmt_cpf(_cpf_sintetico('987654321'))}, pelo valor de R$ 200.000,00."
    )
    d2 = extrair_detalhes_ato(posterior, anterior=ATO_QUEBRADO)
    assert d2.transmitentes[0].cpf_cnpj == CPF


def test_vendeu_parte_ideal_nao_engole_o_nome():
    ato = (
        "R.03, em 1 de março de 2020.\n\nVENDA E COMPRA\n\n"
        "A proprietária ANA EXEMPLO LIMA, já qualificada, vendeu a parte ideal de 50% "
        "do imóvel desta matrícula a PEDRO EXEMPLO ROCHA, brasileiro, casado, engenheiro, "
        f"RG nº 22.333.444-5-SSP/SP, CPF nº {CPF}, residente na Rua Dois, 20."
    )
    (q,) = [x for x in extrair_qualificacoes(ato, 0, len(ato)) if x.cpf_cnpj == CPF]
    assert q.nome == "PEDRO EXEMPLO ROCHA"
    assert q.estado_civil == "casado"
