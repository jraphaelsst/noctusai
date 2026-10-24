""""já qualificado" — a party an act names without its document takes the
qualification the MOST RECENT earlier act of the same matrícula gave that
name (`matricula_qualificacao.qualificar_por_referencia`, wired into
`extrair_detalhes_ato` through its `anterior` context).

F97 (prod): "o proprietário <NOME>, já qualificado, transmitiu … a
<ADQUIRENTE>, …, CPF …" — the seller came back with `cpf_cnpj=None`, the
previous owner was synced without a CPF and his certidões were refused.

Every name, CPF, CNPJ, RG and address below is invented; the documents are
check-digit-valid synthetic values.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents import (
    Parte,
    extrair_detalhes_ato,
    parse_detalhes_json,
    qualificacao_por_nome,
    qualificacoes_anteriores,
    qualificar_por_referencia,
    segment_matricula_atos,
)
from noctusai_lib.integrations.documents.matricula_qualificacao import extrair_qualificacoes

CPF_JOAO = "529.982.247-25"
CPF_MARCOS = "123.456.789-09"
CPF_PEDRO = "111.444.777-35"
CPF_MARIA = "935.411.347-80"
CNPJ_ALFA = "11.222.333/0001-81"

ABERTURA = "MATRÍCULA Nº 12.345 - IMÓVEL: Um apartamento nº 12. PROPRIETÁRIA: CONSTRUTORA EXEMPLO LTDA.\n"
R2_PJ = (
    "R-2/12.345 - Em 05 de maio de 2005. Por escritura de 01/05/2005, a proprietária "
    "CONSTRUTORA EXEMPLO LTDA transmitiu o imóvel a ALFA EMPREENDIMENTOS LTDA, pessoa "
    f"jurídica de direito privado, inscrita no CNPJ nº {CNPJ_ALFA}, com sede nesta Capital, "
    "pelo valor de R$ 50.000,00.\n"
)
R3 = (
    "R-3/12.345 - Em 10 de março de 2009. Por escritura de 02/03/2009, a proprietária ALFA "
    "EMPREENDIMENTOS LTDA, já qualificada, vendeu o imóvel desta matrícula a JOÃO CARLOS "
    f"PEREIRA, brasileiro, solteiro, maior, comerciante, RG nº 11.111.111-1-SSP/SP, CPF nº "
    f"{CPF_JOAO}, residente e domiciliado na Rua A, 1, nesta Capital, pelo valor de R$ 100.000,00.\n"
)
R4 = (
    "R-4/12.345 - Em 02 de junho de 2014. Por escritura de 20/05/2014, a proprietária ALFA "
    "EMPREENDIMENTOS LTDA, já qualificada, vendeu o imóvel desta matrícula a JOÃO CARLOS "
    f"PEREIRA, brasileiro, divorciado, piloto, RG nº 11.111.111-1-SSP/SP, CPF nº {CPF_JOAO}, "
    "residente na Rua A, 1.\n"
)
R7 = (
    "R-7/12.345 - Em 15 de abril de 2024. Por escritura de 01/04/2024, o proprietário JOÃO "
    "CARLOS PEREIRA, já qualificado, transmitiu por venda e compra o imóvel desta matrícula a "
    "MARCOS ANTÔNIO SOUZA, brasileiro, solteiro, maior, psicólogo, RG nº 12.345.678-9-SSP/SP, "
    f"CPF nº {CPF_MARCOS}, residente e domiciliado na Rua B, 2, nesta Capital, pelo valor de "
    "R$ 500.000,00.\n"
)


def _detalhes_do_ultimo(texto: str):
    ultimo = segment_matricula_atos(texto)[-1]
    return extrair_detalhes_ato(texto[ultimo.start : ultimo.end], anterior=texto[: ultimo.start])


def test_f97_seller_named_only_as_ja_qualificado_takes_his_earlier_qualification():
    texto = ABERTURA + R2_PJ + R3 + R7
    d = _detalhes_do_ultimo(texto)
    (joao,) = d.transmitentes
    assert joao.nome == "JOÃO CARLOS PEREIRA"
    assert joao.cpf_cnpj == CPF_JOAO
    assert (joao.rg, joao.rg_orgao_expedidor) == ("11.111.111-1", "SSP/SP")
    assert (joao.estado_civil, joao.profissao, joao.nacionalidade) == (
        "solteiro", "comerciante", "brasileiro",
    )
    assert joao.qualificado_em == "R-3"
    # the adquirente is qualified in THIS act — untouched, no provenance key
    (marcos,) = d.adquirentes
    assert marcos.to_json() == {"nome": "MARCOS ANTÔNIO SOUZA", "cpf_cnpj": CPF_MARCOS}


def test_the_most_recent_qualifying_act_wins():
    texto = ABERTURA + R2_PJ + R3 + R4 + R7
    (joao,) = _detalhes_do_ultimo(texto).transmitentes
    assert joao.qualificado_em == "R-4"
    assert (joao.estado_civil, joao.profissao) == ("divorciado", "piloto")


def test_a_company_resolves_by_its_cnpj():
    texto = ABERTURA + R2_PJ + R3
    (alfa,) = _detalhes_do_ultimo(texto).transmitentes
    assert alfa.cpf_cnpj == CNPJ_ALFA
    assert alfa.qualificado_em == "R-2"
    assert alfa.rg is None and alfa.estado_civil is None


def test_spouse_pair_resolves_each_spouse_casado_com_form():
    r5 = (
        "R-5/12.345 - Em 10 de março de 2015. Por escritura de 02/03/2015, o proprietário JOÃO "
        "CARLOS PEREIRA, já qualificado, vendeu o imóvel desta matrícula a PEDRO HENRIQUE LIMA, "
        f"brasileiro, empresário, RG nº 22.222.222-2-SSP/SP, CPF nº {CPF_PEDRO}, casado com "
        "MARIA CLARA LIMA, brasileira, do lar, RG nº 33.333.333-3-SSP/SP, CPF nº "
        f"{CPF_MARIA}, residentes na Rua C, 3, pelo valor de R$ 300.000,00.\n"
    )
    r7 = (
        "R-7/12.345 - Em 15 de abril de 2024. Por escritura de 01/04/2024, os proprietários "
        "PEDRO HENRIQUE LIMA e sua mulher MARIA CLARA LIMA, já qualificados, venderam o imóvel "
        "desta matrícula a MARCOS ANTÔNIO SOUZA, brasileiro, solteiro, maior, psicólogo, RG nº "
        f"12.345.678-9-SSP/SP, CPF nº {CPF_MARCOS}, residente na Rua B, 2.\n"
    )
    pedro, maria = _detalhes_do_ultimo(ABERTURA + R3 + r5 + r7).transmitentes
    assert (pedro.cpf_cnpj, pedro.qualificado_em) == (CPF_PEDRO, "R-5")
    assert (maria.cpf_cnpj, maria.rg, maria.qualificado_em) == (CPF_MARIA, "33.333.333-3", "R-5")


def test_casado_com_cue_never_steals_the_husbands_own_document():
    # The CPF after "casado com BELTRANA" is FULANO's: his own formula
    # (nationality) sits before the cue.
    texto = (
        "R-1 - vendeu a FULANO DE TAL SOUZA, brasileiro, casado com BELTRANA DE TAL, "
        f"empresário, RG nº 22.222.222-2-SSP/SP, CPF nº {CPF_PEDRO}, residente na Rua X."
    )
    (q,) = extrair_qualificacoes(texto, 0, len(texto))
    assert q.nome == "FULANO DE TAL SOUZA"
    assert q.cpf_cnpj == CPF_PEDRO


def test_no_back_reference_means_no_resolution():
    sem_marcador = R7.replace(", já qualificado,", ",")
    (joao,) = _detalhes_do_ultimo(ABERTURA + R3 + sem_marcador).transmitentes
    assert joao.cpf_cnpj is None and joao.qualificado_em is None


def test_a_name_no_earlier_act_qualified_stays_without_document():
    (joao,) = _detalhes_do_ultimo(ABERTURA + R2_PJ + R7).transmitentes
    assert joao.cpf_cnpj is None and joao.qualificado_em is None


def test_two_homonyms_in_the_most_recent_act_are_never_picked():
    indice = (
        ("R-1", extrair_qualificacoes(R3, 0, len(R3))),
        (
            "R-2",
            extrair_qualificacoes(R3 + R3.replace(CPF_JOAO, CPF_PEDRO), 0, 2 * len(R3)),
        ),
    )
    assert qualificacao_por_nome("JOÃO CARLOS PEREIRA", indice) is None


def test_name_match_folds_accents_case_and_hyphen_wraps():
    indice = qualificacoes_anteriores(ABERTURA + R3)
    ref, q = qualificacao_por_nome("Joao Carlos Pe-\nreira", indice)
    assert (ref, q.cpf_cnpj) == ("R-3", CPF_JOAO)


def test_a_party_with_its_own_document_is_never_rewritten():
    propria = Parte(nome="JOÃO CARLOS PEREIRA", cpf_cnpj=CPF_PEDRO)
    ((saida,),) = qualificar_por_referencia(((propria,),), R7, ABERTURA + R3)
    assert saida == propria


def test_resolved_party_round_trips_through_the_stored_json():
    texto = ABERTURA + R3 + R7
    d = _detalhes_do_ultimo(texto)
    assert parse_detalhes_json(d.to_json()) == d
