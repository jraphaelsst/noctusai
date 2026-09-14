"""Synthetic `DadosContrato` builders for the 6 variants of spec §1.3.

🔴 SYNTHETIC ONLY. Every name, CPF, RG, address and amount here is invented
(CPFs are generated with valid check digits from fictional bases). Nothing is
copied from the real contracts in `products/social-wiring/contracts/`.

V1 financiamento + intermediária + intermediação + itens        (compra_venda)
V2 V1 + FGTS + saldo devedor (interveniente quitante)           (compra_venda)
V3 V1 − itens + ad corpus                                       (compra_venda)
V4 à vista + saldo devedor paid by a parcela + intermediação    (compra_venda_a_vista)
V5 financiamento + permuta + diretas/confissão + saldo devedor  (compra_venda_permuta)
V6 financiamento + intermediária + permuta + declaração + ad corpus (compra_venda_permuta)
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.modules.card_hub.contrato_gerador.dados import (
    AtoCitado,
    Certidao,
    Complementos,
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
    Testemunha,
)
from app.modules.card_hub.contrato_gerador.frases import CERTIDOES
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO

ASSINATURA = date(2026, 9, 14)

MATRICULA_TEXTO = (
    "MATRÍCULA Nº 12.345 - IMÓVEL: O apartamento nº 11 do Edifício Exemplo, situado na Rua "
    "Fictícia, nº 100, Bairro Modelo, com área privativa de 80,00m2.\n"
    "R.1/12.345 - Prot. 1.000 - Por escritura pública, o imóvel foi transmitido a FULANO DE TAL."
)


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
    )
    base.update(extra)
    return Pessoa(**base)


def vendedor() -> Pessoa:
    return pessoa("v1", "vendedor", "proprietario", "Fulano de Tal", "Masculino", "123456789", "11.111.111-1")


def compradora() -> Pessoa:
    return pessoa("c1", "comprador", "comprador", "Beltrana Exemplo", "Feminino", "987654321", "22.222.222-2")


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


def _complementos_base() -> Complementos:
    return Complementos(
        titulo_aquisitivo_texto=(
            "pela escritura pública lavrada aos 10 de janeiro de 2020 no 1º Tabelionato de "
            "Notas de Cidade Exemplo"
        ),
        itens_integrantes="armários planejados da cozinha e dos dormitórios.",
        ad_corpus=False,
        plataforma_assinatura_nome="Plataforma Exemplo",
        plataforma_assinatura_url="https://assinatura.exemplo.test",
        posse_prazo_dias=30,
        posse_marco="parcela_financiamento",
        corretagem_contratantes="vendedores",
        corretagem_parcelas_marco=(1,),
        corretagem_num_parcelas=1,
        corretagem_favorecidos={"int-1": "fav-org"},
    )


def base_v1() -> DadosContrato:
    return DadosContrato(
        contrato_id="contrato-1",
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
        ),
        matricula=Matricula(codigo="EX001", texto=MATRICULA_TEXTO, num_atos=2),
        valor_negociado=Decimal("500000.00"),
        pct_comissao=Decimal("6"),
        parcelas=[
            parcela("p1", "sinal", "50000.00", 1, evento="no ato da assinatura do presente instrumento",
                    forma_pagamento="PIX", favorecido_id="fav-v"),
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
                          tipo="percentual", valor=Decimal("6")),
        ],
        permuta_ativo_id=None,
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
        ),
        testemunhas=[Testemunha(nome="Testemunha Um", rg="33.333.333-3"),
                     Testemunha(nome="Testemunha Dois", rg="44.444.444-4")],
        complementos=_complementos_base(),
    )


def _saldo_devedor(d: DadosContrato, quitacao: str, **comp_extra) -> DadosContrato:
    im = replace(d.imovel, situacao_onus="alienacao_fiduciaria", onus_fonte_atos=[AtoCitado("AV", 2)])
    comp = replace(d.complementos, onus_credor="Banco Credor Exemplo S.A.", onus_quitacao=quitacao, **comp_extra)
    return replace(d, imovel=im, complementos=comp)


def _permuta(d: DadosContrato, valor: str) -> DadosContrato:
    comp = replace(
        d.complementos,
        permuta_parcela_valor=Decimal(valor),
        permuta_imoveis=(
            PermutaImovel(
                descricao_matricula="MATRÍCULA Nº 54.321 - IMÓVEL: A casa situada na Avenida Amostra, nº 5.",
                cidade="Cidade Exemplo",
                inscricao_municipal="111.111.1111-1",
                matricula_numero="54321",
                cartorio="1º Oficial de Registro de Imóveis de Cidade Exemplo",
                endereco_curto="Avenida Amostra, nº 5",
            ),
        ),
        permuta_posse_prazo_dias=60,
        permuta_posse_marco="assinatura",
    )
    return replace(d, permuta_ativo_id="permuta-1", modelo="compra_venda_permuta", complementos=comp)


def variante(n: int) -> DadosContrato:
    d = base_v1()
    if n == 1:
        return d
    if n == 2:
        parcelas = [d.parcelas[0], d.parcelas[1],
                    replace(d.parcelas[2], valor=Decimal("300000.00")),
                    parcela("p4", "fgts", "100000.00", 4, evento="na liberação do FGTS pelo agente financeiro")]
        d = replace(d, parcelas=parcelas, financiamento=Financiamento(True, "aprovado", True))
        return _saldo_devedor(d, "interveniente_quitante")
    if n == 3:
        return replace(d, complementos=replace(d.complementos, itens_integrantes=None, ad_corpus=True))
    if n == 4:
        parcelas = [
            parcela("p1", "sinal", "100000.00", 1, evento="no ato da assinatura do presente instrumento",
                    forma_pagamento="PIX", favorecido_id="fav-v"),
            parcela("p2", "saldo", "400000.00", 2, evento="mediante boleto emitido pelo credor, na data da escritura",
                    forma_pagamento="Boleto", favorecido_id="fav-v"),
        ]
        d = replace(d, modelo="compra_venda_a_vista", parcelas=parcelas, financiamento=Financiamento(),
                    complementos=replace(d.complementos, posse_marco="assinatura"))
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
                    complementos=replace(d.complementos, juros_am_confissao=Decimal("1"),
                                         corretagem_favorecidos={}, itens_integrantes=None))
        d = _saldo_devedor(_permuta(d, "150000.00"), "compradores_prazo", onus_prazo_dias=30)
        return d
    if n == 6:
        parcelas = [d.parcelas[0], d.parcelas[1], replace(d.parcelas[2], valor=Decimal("300000.00"))]
        d = replace(d, parcelas=parcelas, intermediarios=[],
                    complementos=replace(d.complementos, ad_corpus=True, itens_integrantes=None,
                                         corretagem_favorecidos={}))
        return _permuta(d, "100000.00")
    raise ValueError(n)


def politica_variante(n: int):
    """V5/V6 need the permuta despesas answer [Q13]; V6 carries the declaração [Q1]."""
    if n == 5:
        return replace(POLITICA_PADRAO, permuta_despesas="compradores")
    if n == 6:
        return replace(POLITICA_PADRAO, permuta_despesas="cada_parte", tem_declaracao_partes=True)
    return POLITICA_PADRAO


def sem_complementos(d: DadosContrato) -> DadosContrato:
    """What production passes today: every §6.1 field absent."""
    return replace(d, complementos=Complementos())
