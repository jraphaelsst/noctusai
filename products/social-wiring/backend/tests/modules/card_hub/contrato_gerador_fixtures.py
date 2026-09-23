"""Synthetic `DadosContrato` builders for the 6 variants of spec §1.3.

🔴 SYNTHETIC ONLY. Every name, CPF, RG, address and amount here is invented
(CPFs are generated with valid check digits from fictional bases). Nothing is
copied from the real contracts in `products/social-wiring/contracts/`.

V1 financiamento + intermediária + intermediação + itens        (compra_venda)
V2 V1 + FGTS (in the financiamento parcela) + saldo devedor      (compra_venda)
V3 V1 − itens + ad corpus                                       (compra_venda)
V4 à vista + saldo devedor paid by a parcela + intermediação    (compra_venda_a_vista)
V5 financiamento + permuta + diretas/confissão + saldo devedor  (compra_venda_permuta)
V6 financiamento + intermediária + permuta + declaração + ad corpus (compra_venda_permuta)

Every variant carries the data the office's policy answers require (spec §6.2,
answered 2026-09-15): estado-civil certidão < 90 days, certidões < 30 days, the
last compra e venda ≥ 5 years ago (no previous owner required), the office's
posse multa diária + signing platform, witnesses with CPF.

🔴 A PERMUTA IS A PARCELA (migration 114). V5/V6 carry a `tipo='permuta'`
parcela linked to a `permuta_ativos` id, plus the `PermutaImovel` that ativo
resolves to — not a side-car value added to the price on the side. That is why
Σ parcelas == valor_negociado holds by construction in every variant.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from app.modules.card_hub.contrato_gerador.dados import (
    AtoCitado,
    Certidao,
    CertidaoImovel,
    DadosContrato,
    Endereco,
    Favorecido,
    Financiamento,
    Imobiliaria,
    Imovel,
    Intermediario,
    Matricula,
    Parcela,
    PermutaImovel,
    Pessoa,
    Termos,
    Testemunha,
)
from app.modules.card_hub.contrato_gerador.frases import CERTIDOES
from app.modules.card_hub.contrato_gerador.politica import (
    PAPEL_ANTIGO_PROPRIETARIO,
    POLITICA_PADRAO,
)

ASSINATURA = date(2026, 9, 14)

MATRICULA_TEXTO = (
    "MATRÍCULA Nº 12.345 - IMÓVEL: O apartamento nº 11 do Edifício Exemplo, situado na Rua "
    "Fictícia, nº 100, Bairro Modelo, com área privativa de 80,00m2.\n"
    "R.1/12.345 - Prot. 1.000 - Por escritura pública, o imóvel foi transmitido a FULANO DE TAL."
)

MATRICULA_PERMUTA_TEXTO = (
    "MATRÍCULA Nº 54.321 - IMÓVEL: A casa situada na Avenida Amostra, nº 5."
)

#: The permuta ativo every permuta variant swaps (migration 114's link).
PERMUTA_ATIVO_ID = "permuta-1"


def cpf_sintetico(base9: str) -> str:
    """Append valid check digits to 9 fictional digits."""
    digitos = [int(c) for c in base9]
    for tamanho in (9, 10):
        soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(digitos[:tamanho]))
        resto = (soma * 10) % 11
        digitos.append(0 if resto == 10 else resto)
    return "".join(str(d) for d in digitos)


def certidoes_completas(emitida: date = date(2026, 9, 1)) -> list[Certidao]:
    return [
        Certidao(
            tipo=tipo,
            resultado="negativa",
            numero=f"SIM-{i:04d}",
            emitida_em=emitida,
            validade_ate=date(2026, 12, 1),
        )
        for i, (tipo, *_resto) in enumerate(CERTIDOES, start=1)
    ]


def certidoes_pj(
    documento: str,
    nome: str,
    situacao: str | None,
    data_situacao: date | None = None,
    emitida: date = date(2026, 9, 1),
) -> list[Certidao]:
    """The PJ-column certidões of ONE company (CNPJ consulta) of a parte."""
    return [
        Certidao(
            tipo=tipo,
            resultado="negativa",
            numero=f"PJ-{i:04d}",
            emitida_em=emitida,
            validade_ate=date(2026, 12, 1),
            consulta_tipo_documento="cnpj",
            consulta_nome=nome,
            consulta_documento=documento,
            consulta_situacao_cadastral=situacao,
            consulta_data_situacao=data_situacao,
        )
        for i, (tipo, _r, _n, _pf, pj, _s) in enumerate(CERTIDOES, start=1)
        if pj
    ]


def certidoes_do_imovel(emitida: date | None = None) -> tuple[CertidaoImovel, ...]:
    """The imóvel's own certidão group (migration 118). NOT on `base_v1`: the
    default variant exercises the `onus_certidao_em`-only path every card that
    predates 118 still uses, so both sources stay covered."""
    emitida = emitida or dias_antes(5)
    return (
        CertidaoImovel(tipo="matricula", numero="12345", emitida_em=emitida, confirmado=True),
        CertidaoImovel(
            tipo="cnd_iptu",
            numero="IPTU-0001",
            emitida_em=emitida,
            resultado="negativa",
            inscricao_imobiliaria="000.000.0000-0",
            confirmado=True,
        ),
        CertidaoImovel(
            tipo="cnd_condominio", emitida_em=emitida, resultado="negativa", confirmado=True
        ),
    )


def dias_antes(dias: int) -> date:
    return ASSINATURA - timedelta(days=dias)


def endereco(n: str = "10") -> Endereco:
    return Endereco(
        logradouro="Rua das Amostras",
        numero=n,
        complemento=None,
        bairro="Bairro Teste",
        cidade="Cidade Exemplo",
        uf="SP",
        cep="01000000",
    )


def pessoa(
    cliente_id: str,
    lado: str,
    papel: str,
    nome: str,
    genero: str,
    cpf_base: str,
    rg: str,
    **extra,
) -> Pessoa:
    base = dict(
        cliente_id=cliente_id,
        lado=lado,
        papel=papel,
        parte_id=f"parte-{cliente_id}",
        nome=nome,
        nacionalidade="Brasileiro(a)",
        genero=genero,
        estado_civil="solteiro",
        regime_bens=None,
        profissao="Analista",
        cpf=cpf_sintetico(cpf_base),
        rg=rg,
        rg_orgao="SSP/SP",
        email=f"{cliente_id}@exemplo.test",
        endereco=endereco(),
        certidoes=certidoes_completas(),
        certidao_estado_civil_emitida_em=date(2026, 8, 1),
    )
    base.update(extra)
    return Pessoa(**base)


def vendedor() -> Pessoa:
    return pessoa("v1", "vendedor", "proprietario", "Fulano de Tal", "Masculino", "123456789", "11.111.111-1")


def compradora() -> Pessoa:
    return pessoa("c1", "comprador", "comprador", "Beltrana Exemplo", "Feminino", "987654321", "22.222.222-2")


def antiga_proprietaria() -> Pessoa:
    """A previous owner — lado vendedor, not a signatory."""
    return pessoa("a1", "vendedor", PAPEL_ANTIGO_PROPRIETARIO, "Antiga Dona Exemplo", "Feminino", "222333444", "66.666.666-6")


def parcela(pid: str, tipo: str, valor: str, ordem: int, **extra) -> Parcela:
    base = dict(
        id=pid,
        tipo=tipo,
        valor=Decimal(valor),
        vencimento=None,
        evento=None,
        forma_pagamento=None,
        favorecido_id=None,
        confissao_divida=False,
        ordem=ordem,
    )
    base.update(extra)
    return Parcela(**base)


def permuta_imovel(ativo_id: str = PERMUTA_ATIVO_ID) -> PermutaImovel:
    """The imóvel a permuta parcela is paid with, as the loader assembles it:
    the ativo's matrícula quote (`papel='permuta'`) + that imóvel's own dados."""
    return PermutaImovel(
        permuta_ativo_id=ativo_id,
        descricao_matricula=MATRICULA_PERMUTA_TEXTO,
        endereco=Endereco(
            logradouro="Avenida Amostra",
            numero="5",
            complemento=None,
            bairro="Bairro Modelo",
            cidade="Cidade Exemplo",
            uf="SP",
            cep="01000000",
        ),
        inscricao_municipal="111.111.1111-1",
        matricula_numero="54321",
        cartorio="1º Oficial de Registro de Imóveis de Cidade Exemplo",
        num_atos=1,
    )


def _termos_base() -> Termos:
    """`atendimento_negociacao_termos` as the office fills it for V1 — posse
    counted from the financiamento parcela, which the marco NAMES by id."""
    return Termos(
        itens_integrantes="armários planejados da cozinha e dos dormitórios.",
        ad_corpus=False,
        posse_prazo_dias=30,
        posse_marco="parcela",
        posse_marco_parcela_id="p3",
        corretagem_contratantes="vendedores",
        corretagem_num_parcelas=1,
    )


def base_v1() -> DadosContrato:
    return DadosContrato(
        contrato_id="contrato-1",
        cliente_id="c1",
        modelo="compra_venda",
        vendedores=[vendedor()],
        compradores=[compradora()],
        imovel=Imovel(
            codigo="EX001",
            titulo="Apartamento",
            empreendimento="Edifício Exemplo",
            endereco=Endereco(
                logradouro="Rua Fictícia", numero="100", complemento="Apto 11",
                bairro="Bairro Modelo", cidade="Cidade Exemplo", uf="SP", cep="01000000",
            ),
            numero_matricula="12345",
            numero_registro_imoveis="1º Oficial de Registro de Imóveis de Cidade Exemplo",
            inscricao_municipal="000.000.0000-0",
            situacao_onus="livre",
            onus_certidao_em=date(2026, 9, 2),
            titulo_aquisitivo_confirmado=True,
            titulo_aquisitivo_texto=(
                "pela escritura pública lavrada aos 10 de janeiro de 2020 no 1º Tabelionato de "
                "Notas de Cidade Exemplo"
            ),
            ultima_transferencia_em=date(2020, 1, 10),
        ),
        matricula=Matricula(
            codigo="EX001", texto=MATRICULA_TEXTO, num_atos=2,
            # [Owner directive, 2026-09-23] Resolved (in real carregamento)
            # from the matrícula's own text — the fixture supplies the
            # RESULT directly rather than embedding the phrase into
            # `MATRICULA_TEXTO`, which byte-for-byte contract-quote
            # assertions elsewhere key on. `comarca_de_texto` itself is
            # tested directly (see TestComarcaDaMatricula).
            comarca="Cidade Exemplo/SP",
        ),
        valor_negociado=Decimal("500000.00"),
        pct_comissao=Decimal("6"),
        parcelas=[
            parcela("p1", "sinal", "50000.00", 1, evento="no ato da assinatura do presente instrumento",
                    forma_pagamento="PIX", favorecido_id="fav-v", dispara_corretagem=True),
            parcela("p2", "intermediaria", "50000.00", 2, evento="na assinatura do financiamento",
                    forma_pagamento="Transferência", favorecido_id="fav-v"),
            parcela("p3", "financiamento", "400000.00", 3,
                    evento="com prazo máximo de pagamento de 90 (noventa) dias corridos, a contar da assinatura do presente instrumento"),
        ],
        favorecidos=[
            Favorecido(id="fav-v", nome="Fulano de Tal", cpf_cnpj=cpf_sintetico("123456789"),
                       banco="Banco Exemplo", agencia="0001", conta="12345-6", pix="fulano@exemplo.test"),
            Favorecido(id="fav-org", nome="Imobiliária Exemplo Ltda", cpf_cnpj="11222333000181",
                       banco="Banco Exemplo", agencia="0002", conta="65432-1"),
        ],
        intermediarios=[
            Intermediario(id="int-1", corretor_id="user-1", nome="Corretor Exemplo", creci="000001-F",
                          tipo="percentual", valor=Decimal("6"), favorecido_id="fav-org"),
        ],
        financiamento=Financiamento(existe=True, situacao="aprovado", fgts=False),
        imobiliaria=Imobiliaria(
            razao_social="Imobiliária Exemplo Ltda",
            nome_fantasia="Exemplo Imóveis",
            cnpj="11222333000181",
            creci_pj="00001-J",
            responsavel_nome="Sicrano Responsável",
            responsavel_creci="000002-F",
            email="contato@exemplo.test",
            endereco=endereco("200"),
            posse_multa_diaria=Decimal("500.00"),
            plataforma_assinatura_nome="Plataforma Exemplo",
            plataforma_assinatura_url="https://assinatura.exemplo.test",
        ),
        # [Owner directive, 2026-09-23] `email` now blocks readiness (see
        # `derivacao._imobiliaria`), so the base fixture must carry one for
        # every variant to stay `pronto` by default; the dedicated
        # `test_a_witness_with_no_email_blocks` clears it explicitly.
        testemunhas=[
            Testemunha(nome="Testemunha Um", rg="33.333.333-3", cpf=cpf_sintetico("321654987"),
                       email="testemunha.um@exemplo.test"),
            Testemunha(nome="Testemunha Dois", rg="44.444.444-4", cpf=cpf_sintetico("456789123"),
                       email="testemunha.dois@exemplo.test"),
        ],
        termos=_termos_base(),
    )


def _saldo_devedor(d: DadosContrato, quitacao: str, **termos_extra) -> DadosContrato:
    im = replace(
        d.imovel,
        situacao_onus="alienacao_fiduciaria",
        onus_fonte_atos=[AtoCitado("AV", 2)],
        onus_credor="Banco Credor Exemplo S.A.",
    )
    termos = replace(d.termos, onus_quitacao=quitacao, **termos_extra)
    return replace(d, imovel=im, termos=termos)


def _permuta(d: DadosContrato, valor: str, *, ordem: int) -> DadosContrato:
    """Add the `tipo='permuta'` parcela (114) + the imóvel it is paid with."""
    parcelas = d.parcelas + [
        parcela("p-permuta", "permuta", valor, ordem, permuta_ativo_ids=(PERMUTA_ATIVO_ID,))
    ]
    termos = replace(d.termos, permuta_posse_prazo_dias=60, permuta_posse_marco="assinatura")
    return replace(
        d,
        parcelas=parcelas,
        modelo="compra_venda_permuta",
        termos=termos,
        permuta_imoveis=[permuta_imovel()],
    )


def variante(n: int) -> DadosContrato:
    d = base_v1()
    if n == 1:
        return d
    if n == 2:
        # [Q6] ONE parcela: the FGTS is worded inside the financiamento parcela.
        d = replace(d, financiamento=Financiamento(True, "aprovado", True))
        return _saldo_devedor(d, "interveniente_quitante")
    if n == 3:
        return replace(
            d,
            termos=replace(
                d.termos, itens_integrantes=None,
                itens_integrantes_ausente_confirmado=True, ad_corpus=True,
            ),
        )
    if n == 4:
        parcelas = [
            parcela("p1", "sinal", "100000.00", 1, evento="no ato da assinatura do presente instrumento",
                    forma_pagamento="PIX", favorecido_id="fav-v", dispara_corretagem=True),
            parcela("p2", "saldo", "400000.00", 2, evento="mediante boleto emitido pelo credor, na data da escritura",
                    forma_pagamento="Boleto", favorecido_id="fav-v"),
        ]
        d = replace(d, modelo="compra_venda_a_vista", parcelas=parcelas, financiamento=Financiamento(),
                    termos=replace(d.termos, posse_marco="assinatura", posse_marco_parcela_id=None))
        return _saldo_devedor(d, "parcela")
    if n == 5:
        parcelas = [
            d.parcelas[0],
            parcela("p3", "financiamento", "250000.00", 2, evento="na liberação do financiamento"),
            parcela("p5", "direta", "50000.00", 3, vencimento=date(2027, 1, 10), forma_pagamento="PIX",
                    favorecido_id="fav-v", confissao_divida=True),
            parcela("p6", "direta", "50000.00", 4, vencimento=date(2027, 2, 10), forma_pagamento="PIX",
                    favorecido_id="fav-v", confissao_divida=True),
        ]
        d = replace(d, parcelas=parcelas, intermediarios=[], valor_negociado=Decimal("550000.00"),
                    termos=replace(d.termos, confissao_juros_am=Decimal("1"), itens_integrantes=None,
                                   itens_integrantes_ausente_confirmado=True))
        d = _saldo_devedor(_permuta(d, "150000.00", ordem=5), "compradores_prazo", onus_prazo_dias=30)
        return d
    if n == 6:
        parcelas = [d.parcelas[0], d.parcelas[1], replace(d.parcelas[2], valor=Decimal("300000.00"))]
        d = replace(d, parcelas=parcelas, intermediarios=[],
                    termos=replace(d.termos, ad_corpus=True, itens_integrantes=None,
                                   itens_integrantes_ausente_confirmado=True))
        return _permuta(d, "100000.00", ordem=4)
    raise ValueError(n)


def politica_variante(n: int):
    """V6 turns on the (non-standard [Q1]) Declaração das Partes."""
    if n == 6:
        return replace(POLITICA_PADRAO, tem_declaracao_partes=True)
    return POLITICA_PADRAO


def sem_termos(d: DadosContrato) -> DadosContrato:
    """A deal whose `termos` form was never filled — every per-deal clause of
    migration 114 absent, everything else present."""
    return replace(d, termos=Termos())
