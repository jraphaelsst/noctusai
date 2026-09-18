"""`extrair_qualificacoes` / `mesclar_qualificacoes` — parties anchored by
their DOCUMENT NUMBER, not a label.

🔴 WHAT THESE PIN
-----------------
1. Every text field is a literal substring of the fixture (or `None`); every
   offset satisfies `0 <= start <= end <= len(texto)`.
2. A checksum-valid CPF/CNPJ finds its owner by walking BACK across the
   qualification formula to the name, not forward from a label — real
   matrícula prose almost never carries `TRANSMITENTE:`/`ADQUIRENTE:` labels.
3. A `selo digital` / `protocolo` number that happens to pass the CPF
   checksum is never mistaken for a party.
4. `genero` is read off Portuguese grammatical agreement, never guessed.
5. `mesclar_qualificacoes` merges one extraction's per-act readings by
   CPF/CNPJ, first-writer-wins per field, with per-field provenance.

Every name, CPF, CNPJ, RG and address below is invented; the CPF/CNPJ
numbers are check-digit-valid synthetic values (`_cpf_sintetico` /
`_cnpj_sintetico` below — the seed-side equivalent of
`social-wiring`'s `contrato_gerador_fixtures.cpf_sintetico`; not imported
across the product/seed boundary).
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.matricula_qualificacao import (
    Qualificacao,
    extrair_qualificacoes,
    mesclar_qualificacoes,
)

# ─── synthetic, check-digit-valid documents ────────────────────────────────


def _cpf_sintetico(base9: str) -> str:
    """Append valid check digits to 9 fictional digits."""
    digitos = [int(c) for c in base9]
    for tamanho in (9, 10):
        soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(digitos[:tamanho]))
        resto = (soma * 10) % 11
        digitos.append(0 if resto == 10 else resto)
    return "".join(str(d) for d in digitos)


def _fmt_cpf(d: str) -> str:
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _cnpj_sintetico(base12: str) -> str:
    digitos = [int(c) for c in base12]
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(d * p for d, p in zip(digitos, pesos1))
    resto = soma % 11
    digitos.append(0 if resto < 2 else 11 - resto)
    pesos2 = [6] + pesos1
    soma2 = sum(d * p for d, p in zip(digitos, pesos2))
    resto2 = soma2 % 11
    digitos.append(0 if resto2 < 2 else 11 - resto2)
    return "".join(str(d) for d in digitos)


def _fmt_cnpj(d: str) -> str:
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


CPF_MARIA = _fmt_cpf(_cpf_sintetico("111222333"))  # 111.222.333-96
CPF_JOSE = _fmt_cpf(_cpf_sintetico("222333444"))  # 222.333.444-05
CPF_CLARA = _fmt_cpf(_cpf_sintetico("333444555"))  # 333.444.555-08
CPF_MARCELO = _fmt_cpf(_cpf_sintetico("444555666"))  # 444.555.666-19
CPF_ROBERTO = _fmt_cpf(_cpf_sintetico("555666777"))  # 555.666.777-20
CPF_CAMILA = _fmt_cpf(_cpf_sintetico("666777888"))  # 666.777.888-30
CNPJ_EMPRESA = _fmt_cnpj(_cnpj_sintetico("112233445566"))  # 11.223.344/5566-13
SELO_DIGITAL = _cpf_sintetico("999888777")  # checksum-valid, undotted — the decoy

# One CPF per real RG shape (`RG_SHAPES` below), plus one for the plural
# nacionalidade / profissão / epicene genero fixtures.
CPF_RG_1 = _fmt_cpf(_cpf_sintetico("888111222"))
CPF_RG_2 = _fmt_cpf(_cpf_sintetico("888222333"))
CPF_RG_3 = _fmt_cpf(_cpf_sintetico("888333444"))
CPF_RG_4 = _fmt_cpf(_cpf_sintetico("888444555"))
CPF_RG_5 = _fmt_cpf(_cpf_sintetico("888555666"))
CPF_RG_SELO = _fmt_cpf(_cpf_sintetico("888666777"))
CPF_FLAVIA = _fmt_cpf(_cpf_sintetico("888777888"))
CPF_FRANCES = _fmt_cpf(_cpf_sintetico("888888999"))
CPF_MARCOS = _fmt_cpf(_cpf_sintetico("888999111"))


# ─── fixtures ───────────────────────────────────────────────────────────────

#: 1) / 2) transmitentes, already qualified (no CPF restated), "transmitiram
#: por permuta" — the exact real-world shape that motivated the CPF anchor.
PERMUTA_JA_QUALIFICADOS = (
    "R-4/33.222 - Em 10/09/2020. PERMUTA. Por escritura pública datada de 10 de "
    "setembro de 2020, do 3º Tabelião de Notas de Cotia, livro 200, fls. 55, "
    "1) RODRIGO EXEMPLO SOUZA, residente e domiciliado na Rua Amostra, nº 12, "
    "Cotia-SP; e 2) TAUANE EXEMPLO SOUZA, residente e domiciliada na Rua Amostra, "
    "nº 12, Cotia-SP, ambos já qualificados, transmitiram por permuta o imóvel "
    f"matriculado a MARIA FICTÍCIA ROCHA, brasileira, divorciada, secretária "
    f"executiva, RG nº 22.333.444-SSP/SP, CPF nº {CPF_MARIA}, residente e "
    "domiciliada na Avenida Modelo, nº 500, Cotia-SP, pelo valor de R$ 250.000,00.\n"
)

#: `portador da cédula de identidade, RG nº ... e inscrito no CPF/MF nº ...`.
CEDULA_DE_IDENTIDADE = (
    "R-3/77.888 - Em 01/02/2021. COMPRA E VENDA. Por escritura pública de compra "
    "e venda, o imóvel foi vendido a JOSÉ EXEMPLO LIMA, brasileiro, casado, "
    "comerciante, portador da cédula de identidade, RG nº 11.222.333 e inscrito "
    f"no CPF/MF nº {CPF_JOSE}, residente e domiciliado na Rua Fictícia, nº 45, "
    "Cotia-SP.\n"
)

#: A legal entity: razão social, `sociedade anônima`, `CNPJ/MF`, `com sede em`.
PESSOA_JURIDICA = (
    "R-5/44.555 - Em 15/05/2021. COMPRA E VENDA. Por escritura pública de "
    "compra e venda, o imóvel foi vendido a EMPRESA EXEMPLO PARTICIPAÇÕES S.A., "
    f"sociedade anônima, inscrita no CNPJ/MF sob o nº {CNPJ_EMPRESA}, com sede "
    "em Cotia-SP.\n"
)

#: Spouse chain — each spouse keeps their OWN CPF and full qualification.
CONJUGES = (
    "R-6/55.666 - Em 20/06/2021. VENDA. Por escritura pública, o imóvel foi "
    "vendido a CLARA EXEMPLO PIRES, brasileira, corretora de imóveis, RG nº "
    f"33.444.555-SSP/SP, CPF/MF nº {CPF_CLARA}, e seu cônjuge MARCELO EXEMPLO "
    "PIRES, brasileiro, engenheiro civil, RG nº 33.444.556-SSP/SP, CPF/MF nº "
    f"{CPF_MARCELO}, residentes e domiciliados na Rua Amostra, nº 20, "
    "Cotia-SP.\n"
)

#: A legacy transcription row wraps the name in `**bold**` markup.
NOME_COM_ASTERISCOS = (
    "R-7/66.777 - Em 25/07/2021. VENDA. Por escritura pública, o imóvel foi "
    "vendido a **ROBERTO EXEMPLO ANDRADE**, brasileiro, solteiro, autônomo, RG "
    f"nº 44.555.666-SSP/SP, CPF nº {CPF_ROBERTO}, residente e domiciliado na "
    "Rua Amostra, nº 30, Cotia-SP.\n"
)

#: A `Selo digital:` number that passes the CPF checksum by chance, right
#: next to a real party — the guard must drop the former, keep the latter.
COM_SELO_DIGITAL = (
    CEDULA_DE_IDENTIDADE.rstrip("\n")
    + f" Selo digital: {SELO_DIGITAL}. Prenotação nº 555.666.\n"
)

#: EARLIER act: José fully qualified. LATER act: José is only "já
#: qualificado" (no CPF restated) — nothing to extract for him there; the
#: NEW buyer, Camila, still gets her own full qualification.
ATO_ANTERIOR = CEDULA_DE_IDENTIDADE
ATO_POSTERIOR = (
    "R-5/77.888 - Em 10/03/2022. VENDA. Por escritura pública, JOSÉ EXEMPLO "
    "LIMA, já qualificado, vendeu o imóvel a CAMILA EXEMPLO BRITO, brasileira, "
    "solteira, arquiteta, RG nº 66.777.888-SSP/SP, CPF nº "
    f"{CPF_CAMILA}, residente e domiciliada na Avenida Modelo, nº 90, "
    "Cotia-SP.\n"
)

#: The 5 real RG shapes the production corpus carries, an invented digit
#: run per shape (`_ato_com_rg` builds a full act around one), and the
#: (rg, órgão) each must round-trip to.
def _ato_com_rg(cpf: str, rg_clausula: str) -> str:
    return (
        "R-9/44.111 - Em 01/01/2022. VENDA. Por escritura pública, o imóvel "
        "foi vendido a REGINA AMOSTRA AZEVEDO, brasileira, divorciada, "
        f"professora, {rg_clausula}, CPF nº {cpf}, residente e domiciliada "
        "na Rua Amostra, nº 1, Cotia-SP.\n"
    )


RG_SHAPES: tuple[tuple[str, str, str, Optional[str]], ...] = (
    ("dv_digito_com_ssp", "RG nº 13.045.678-4-SSP/SP", "13.045.678-4", "SSP/SP"),
    ("sem_dv_com_ssp", "RG nº 7.123.456-SSP/SP", "7.123.456", "SSP/SP"),
    ("sem_pontos", "RG nº 7123456-SSP/SP", "7123456", "SSP/SP"),
    ("dv_letra_x", "RG nº 13.045.678-X-SSP/SP", "13.045.678-X", "SSP/SP"),
    ("dv_digito_uf_nua", "RG nº 13.045.678-4-SP", "13.045.678-4", "SP"),
)

#: `RG nº ... .\nSelo digital: N` — the real corpus's most common shape
#: right after an RG match (measured: ~9/14 acts). No dash joins them, so
#: this is already safe by construction; kept as a regression fixture.
COM_RG_E_SELO_SEM_TRACO = _ato_com_rg(
    CPF_RG_SELO, "RG nº 9.876.543.\nSelo digital: 12345678901"
)

#: A hyphen-joined OCR artifact — the adversarial construction that
#: specifically exercises `_ORGAO_INVALIDO` (see its own docstring): the
#: decoy is shaped EXACTLY like a valid órgão (2+ uppercase letters right
#: after a dash) and must still never be absorbed.
COM_RG_E_SELO_COM_TRACO = _ato_com_rg(
    CPF_RG_SELO, "RG nº 9.876.543-SELO DIGITAL: 12345678901"
)

#: A collectively-phrased ("ambos/ambas") nationality bleeding into an
#: individual restatement is a real transcription inconsistency — the
#: plural spelling must not silently drop an otherwise unambiguous signal.
NACIONALIDADE_PLURAL = (
    "R-9/55.222 - Em 03/03/2022. VENDA. Por escritura pública, o imóvel foi "
    "vendido a FLÁVIA EXEMPLO ROCHA, brasileiras, solteira, comerciante, RG "
    f"nº 12.345.678-SSP/SP, CPF nº {CPF_FLAVIA}, residente e domiciliada na "
    "Rua Amostra, nº 40, Cotia-SP.\n"
)

#: `francês`/`inglês`/`japonês`/`chinês` are masculine nationalities that do
#: NOT end in "o" — nacionalidade alone gives no gender signal here, so
#: `genero` must come from the (also gendered) profissão instead.
GENERO_SO_DA_PROFISSAO = (
    "R-9/66.333 - Em 04/04/2022. VENDA. Por escritura pública, o imóvel foi "
    "vendido a MARCOS EXEMPLO DUARTE, francês, engenheiro, RG nº "
    f"22.333.444-SSP/SP, CPF nº {CPF_FRANCES}, residente e domiciliado na "
    "Rua Amostra, nº 50, Cotia-SP.\n"
)

#: Same neutral nationality, the profissão is EPICENE (`motorista` — `o/a
#: motorista`), and the address uses the `residente NA` phrasing that
#: carries no gendered `domiciliad[oa]` word either — every signal genuinely
#: gives nothing, so `genero` must stay `None`, not guess.
GENERO_EPICENO_FICA_NONE = (
    "R-9/77.444 - Em 05/05/2022. VENDA. Por escritura pública, o imóvel foi "
    "vendido a PAULO EXEMPLO NUNES, francês, motorista, RG nº "
    f"33.444.555-SSP/SP, CPF nº {CPF_MARCOS}, residente na Rua Amostra, nº "
    "60, Cotia-SP.\n"
)

TODAS = [
    PERMUTA_JA_QUALIFICADOS,
    CEDULA_DE_IDENTIDADE,
    PESSOA_JURIDICA,
    CONJUGES,
    NOME_COM_ASTERISCOS,
    COM_SELO_DIGITAL,
    ATO_POSTERIOR,
    COM_RG_E_SELO_SEM_TRACO,
    COM_RG_E_SELO_COM_TRACO,
    NACIONALIDADE_PLURAL,
    GENERO_SO_DA_PROFISSAO,
    GENERO_EPICENO_FICA_NONE,
] + [_ato_com_rg(cpf, clausula) for cpf, (_id, clausula, _rg, _org) in zip(
    (CPF_RG_1, CPF_RG_2, CPF_RG_3, CPF_RG_4, CPF_RG_5), RG_SHAPES
)]


# ─── invariants ─────────────────────────────────────────────────────────────


def test_every_offset_is_a_valid_span_into_the_text():
    for texto in TODAS:
        for q in extrair_qualificacoes(texto, 0, len(texto)):
            assert 0 <= q.nome_inicio <= q.nome_fim <= len(texto)
            assert texto[q.nome_inicio : q.nome_fim] == q.nome
            for campo in (q.nacionalidade, q.profissao, q.rg, q.rg_orgao_expedidor, q.endereco):
                if campo is not None:
                    assert campo in texto


def test_start_offset_rebases_into_the_callers_text():
    """`start` is not always 0 — a caller passing a whole matrícula plus an
    act's own `[start, end)` span must get offsets into ITS buffer."""
    prefixo = "ALGO ANTES DO ATO. "
    texto = prefixo + CEDULA_DE_IDENTIDADE
    (q,) = extrair_qualificacoes(texto, len(prefixo), len(texto))
    assert texto[q.nome_inicio : q.nome_fim] == "JOSÉ EXEMPLO LIMA"


def test_empty_window_is_no_parties():
    assert extrair_qualificacoes("qualquer coisa", 0, 0) == ()
    assert extrair_qualificacoes("   ", 0, 3) == ()


# ─── the já-qualificado shape that motivated the CPF anchor ────────────────


def test_narrative_permuta_finds_only_the_cpf_anchored_party():
    """RODRIGO and TAUANE are named but carry no CPF in THIS act — a
    label-based reader finds nothing here at all; this one still resolves
    MARIA off her own document."""
    (q,) = extrair_qualificacoes(PERMUTA_JA_QUALIFICADOS, 0, len(PERMUTA_JA_QUALIFICADOS))
    assert q.nome == "MARIA FICTÍCIA ROCHA"
    assert q.cpf_cnpj == CPF_MARIA
    assert q.nacionalidade == "brasileira"
    assert q.estado_civil == "divorciado"
    assert q.profissao == "secretária executiva"
    assert q.rg == "22.333.444"
    assert q.rg_orgao_expedidor == "SSP/SP"
    assert q.endereco == "Avenida Modelo, nº 500, Cotia-SP"
    assert q.genero == "f"
    assert q.confianca == "alta"


# ─── the cédula-de-identidade variant ───────────────────────────────────────


def test_portador_da_cedula_de_identidade_variant():
    (q,) = extrair_qualificacoes(CEDULA_DE_IDENTIDADE, 0, len(CEDULA_DE_IDENTIDADE))
    assert q.nome == "JOSÉ EXEMPLO LIMA"
    assert q.cpf_cnpj == CPF_JOSE
    assert q.nacionalidade == "brasileiro"
    assert q.estado_civil == "casado"
    assert q.profissao == "comerciante"
    assert q.rg == "11.222.333"
    assert q.rg_orgao_expedidor is None  # this variant never prints one
    assert q.genero == "m"
    assert q.confianca == "alta"  # RG + nacionalidade both anchored — an
    # órgão expedidor is not required for `alta`, see the module docstring


# ─── a legal entity ─────────────────────────────────────────────────────────


def test_pessoa_juridica_reads_the_razao_social():
    (q,) = extrair_qualificacoes(PESSOA_JURIDICA, 0, len(PESSOA_JURIDICA))
    assert q.nome == "EMPRESA EXEMPLO PARTICIPAÇÕES S.A."
    assert q.cpf_cnpj == CNPJ_EMPRESA
    assert q.nacionalidade is None
    assert q.estado_civil is None
    assert q.rg is None
    assert q.genero is None


# ─── spouse chain ───────────────────────────────────────────────────────────


def test_spouse_chain_is_two_people_each_with_their_own_document():
    qs = extrair_qualificacoes(CONJUGES, 0, len(CONJUGES))
    assert len(qs) == 2
    clara, marcelo = qs
    assert clara.nome == "CLARA EXEMPLO PIRES"
    assert clara.cpf_cnpj == CPF_CLARA
    assert clara.profissao == "corretora de imóveis"
    assert clara.estado_civil is None  # never stated for her — not guessed
    assert clara.genero == "f"
    assert marcelo.nome == "MARCELO EXEMPLO PIRES"
    assert marcelo.cpf_cnpj == CPF_MARCELO
    assert marcelo.profissao == "engenheiro civil"
    assert marcelo.genero == "m"


# ─── legacy **NOME** markup ─────────────────────────────────────────────────


def test_asterisk_markup_is_stripped_from_the_name():
    (q,) = extrair_qualificacoes(NOME_COM_ASTERISCOS, 0, len(NOME_COM_ASTERISCOS))
    assert q.nome == "ROBERTO EXEMPLO ANDRADE"
    assert "*" not in q.nome
    assert q.cpf_cnpj == CPF_ROBERTO


# ─── the selo digital decoy ─────────────────────────────────────────────────


def test_a_checksum_valid_selo_digital_is_never_a_party():
    qs = extrair_qualificacoes(COM_SELO_DIGITAL, 0, len(COM_SELO_DIGITAL))
    assert len(qs) == 1
    assert qs[0].nome == "JOSÉ EXEMPLO LIMA"
    formatados = {q.cpf_cnpj for q in qs}
    assert SELO_DIGITAL not in formatados
    assert all(SELO_DIGITAL not in (q.cpf_cnpj or "") for q in qs)


# ─── merge across acts ──────────────────────────────────────────────────────


def test_ja_qualificado_act_contributes_nothing_and_merge_keeps_the_earlier_record():
    anteriores = extrair_qualificacoes(ATO_ANTERIOR, 0, len(ATO_ANTERIOR))
    posteriores = extrair_qualificacoes(ATO_POSTERIOR, 0, len(ATO_POSTERIOR))
    # José has no CPF in the later act — nothing is extracted for him there.
    assert all(q.nome != "JOSÉ EXEMPLO LIMA" for q in posteriores)

    mesclado = mesclar_qualificacoes([("R-3", anteriores), ("R-5", posteriores)])
    por_documento = {c.qualificacao.cpf_cnpj: c for c in mesclado}

    jose = por_documento[CPF_JOSE]
    assert jose.qualificacao.nome == "JOSÉ EXEMPLO LIMA"
    assert jose.qualificacao.profissao == "comerciante"
    assert jose.qualificacao.endereco is not None
    assert set(jose.origem.values()) == {"R-3"}  # every field traces to R-3

    camila = por_documento[CPF_CAMILA]
    assert camila.qualificacao.nome == "CAMILA EXEMPLO BRITO"
    assert camila.origem["nome"] == "R-5"


def test_merge_is_first_writer_wins_per_field_with_provenance():
    """Direct unit test of the merge rule, isolated from the regex pipeline:
    a field already set by an earlier act is never overwritten by a later,
    less complete (or simply different) mention — and each field records
    which act it came from."""
    completa = Qualificacao(
        nome="ANA EXEMPLO SOUZA",
        cpf_cnpj=CPF_MARIA,
        nacionalidade="brasileira",
        estado_civil="solteiro",
        profissao="médica",
        rg="12.345.678",
        rg_orgao_expedidor="SSP/SP",
        endereco="Rua Um, 10",
        genero="f",
        nome_inicio=0,
        nome_fim=17,
        confianca="alta",
    )
    # a later act restates her, wrongly, as "casada" — first writer wins.
    parcial_divergente = Qualificacao(
        nome="ANA EXEMPLO SOUZA",
        cpf_cnpj=CPF_MARIA,
        nacionalidade=None,
        estado_civil="casado",
        profissao=None,
        rg=None,
        rg_orgao_expedidor=None,
        endereco=None,
        genero=None,
        nome_inicio=100,
        nome_fim=117,
        confianca="baixa",
    )
    mesclado = mesclar_qualificacoes(
        [("ato-1", (completa,)), ("ato-2", (parcial_divergente,))]
    )
    assert len(mesclado) == 1
    consolidada = mesclado[0]
    assert consolidada.qualificacao.estado_civil == "solteiro"  # ato-1 wins
    assert consolidada.qualificacao.nome_inicio == 0  # offsets travel with nome
    assert consolidada.origem == {
        "nome": "ato-1",
        "nacionalidade": "ato-1",
        "estado_civil": "ato-1",
        "profissao": "ato-1",
        "rg": "ato-1",
        "rg_orgao_expedidor": "ato-1",
        "endereco": "ato-1",
        "genero": "ato-1",
    }


def test_merge_fills_gaps_from_a_later_act():
    parcial = Qualificacao(
        nome="BRUNO EXEMPLO LIMA",
        cpf_cnpj=CPF_JOSE,
        nacionalidade=None,
        estado_civil=None,
        profissao=None,
        rg=None,
        rg_orgao_expedidor=None,
        endereco=None,
        genero=None,
        nome_inicio=0,
        nome_fim=18,
        confianca="baixa",
    )
    completa_depois = Qualificacao(
        nome="BRUNO EXEMPLO LIMA",
        cpf_cnpj=CPF_JOSE,
        nacionalidade="brasileiro",
        estado_civil="casado",
        profissao="professor",
        rg="98.765.432",
        rg_orgao_expedidor="SSP/SP",
        endereco="Rua Dois, 20",
        genero="m",
        nome_inicio=200,
        nome_fim=218,
        confianca="alta",
    )
    mesclado = mesclar_qualificacoes([("ato-1", (parcial,)), ("ato-2", (completa_depois,))])
    consolidada = mesclado[0]
    assert consolidada.qualificacao.nacionalidade == "brasileiro"
    assert consolidada.origem["nacionalidade"] == "ato-2"
    assert consolidada.origem["nome"] == "ato-1"


def test_merge_never_mixes_two_different_documents():
    a = Qualificacao(
        nome="CARLA EXEMPLO DIAS",
        cpf_cnpj=CPF_MARIA,
        nacionalidade=None,
        estado_civil=None,
        profissao=None,
        rg=None,
        rg_orgao_expedidor=None,
        endereco=None,
        genero=None,
        nome_inicio=0,
        nome_fim=19,
        confianca="baixa",
    )
    b = Qualificacao(
        nome="DANIEL EXEMPLO ROCHA",
        cpf_cnpj=CPF_JOSE,
        nacionalidade=None,
        estado_civil=None,
        profissao=None,
        rg=None,
        rg_orgao_expedidor=None,
        endereco=None,
        genero=None,
        nome_inicio=0,
        nome_fim=20,
        confianca="baixa",
    )
    mesclado = mesclar_qualificacoes([("ato-1", (a, b))])
    assert {c.qualificacao.cpf_cnpj for c in mesclado} == {CPF_MARIA, CPF_JOSE}


def test_to_json_round_trips_the_shape():
    (q,) = extrair_qualificacoes(CEDULA_DE_IDENTIDADE, 0, len(CEDULA_DE_IDENTIDADE))
    dados = q.to_json()
    assert dados["nome"] == q.nome
    assert dados["cpf_cnpj"] == q.cpf_cnpj
    mesclado = mesclar_qualificacoes([("R-3", (q,))])[0]
    assert mesclado.to_json()["origem"]["nome"] == "R-3"


# ─── RG shapes: the check digit is part of the number, never dropped ───────


@pytest.mark.parametrize("caso, clausula, rg_esperado, orgao_esperado", RG_SHAPES)
def test_every_real_rg_shape_round_trips(caso, clausula, rg_esperado, orgao_esperado):
    cpf = {
        "dv_digito_com_ssp": CPF_RG_1,
        "sem_dv_com_ssp": CPF_RG_2,
        "sem_pontos": CPF_RG_3,
        "dv_letra_x": CPF_RG_4,
        "dv_digito_uf_nua": CPF_RG_5,
    }[caso]
    texto = _ato_com_rg(cpf, clausula)
    (q,) = extrair_qualificacoes(texto, 0, len(texto))
    assert q.rg == rg_esperado, caso
    assert q.rg_orgao_expedidor == orgao_esperado, caso


def test_rg_without_a_dash_before_selo_digital_stays_clean():
    (q,) = extrair_qualificacoes(COM_RG_E_SELO_SEM_TRACO, 0, len(COM_RG_E_SELO_SEM_TRACO))
    assert q.rg == "9.876.543"
    assert q.rg_orgao_expedidor is None


def test_a_hyphen_joined_selo_digital_is_never_absorbed_as_orgao():
    """The adversarial case: `RG nº 9.876.543-SELO DIGITAL: ...` is shaped
    EXACTLY like a valid `-ÓRGÃO` suffix (a dash then 2+ uppercase letters)
    — `_ORGAO_INVALIDO` is the only thing standing between this and a
    fabricated órgão."""
    (q,) = extrair_qualificacoes(COM_RG_E_SELO_COM_TRACO, 0, len(COM_RG_E_SELO_COM_TRACO))
    assert q.rg == "9.876.543"
    assert q.rg_orgao_expedidor is None


# ─── genero: widened, still never guessed ──────────────────────────────────


def test_plural_nacionalidade_still_resolves_gender():
    (q,) = extrair_qualificacoes(NACIONALIDADE_PLURAL, 0, len(NACIONALIDADE_PLURAL))
    assert q.nacionalidade == "brasileiras"
    assert q.genero == "f"


def test_genero_falls_back_to_profissao_when_nacionalidade_is_gender_neutral():
    (q,) = extrair_qualificacoes(GENERO_SO_DA_PROFISSAO, 0, len(GENERO_SO_DA_PROFISSAO))
    assert q.nacionalidade == "francês"  # `francês` carries no -o/-a agreement
    assert q.profissao == "engenheiro"
    assert q.genero == "m"


def test_genero_stays_none_when_every_signal_is_epicene_or_neutral():
    (q,) = extrair_qualificacoes(GENERO_EPICENO_FICA_NONE, 0, len(GENERO_EPICENO_FICA_NONE))
    assert q.nacionalidade == "francês"
    assert q.profissao == "motorista"  # `o/a motorista` — no gendered form
    assert q.genero is None
