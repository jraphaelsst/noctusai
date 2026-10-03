"""The amending sections' wording — reviewable text, one function per
amendment tipo, measured against the office's 5 aditivo deals (REDACTED
corpus, clause catalog §1).

Every section is `Secao(titulo_house, titulo_formal, paragrafos)`; the two
templates (`modelo_texto`) differ only in how they head and number it. The
data-dependent pieces are the generator's own: `contrato_gerador.frases.
texto_parcela` for each restated parcela, `concordancia` for every article,
`estilo` for emphasis, `texto_ptbr` for money/dates/ordinals — never a
second copy.

🔴 A citation of the ORIGINAL's clause/parcela always goes through
`ref_clausula_original` / `ref_parcela_original` — the post-render lint
(`documento.lint_aditivo`) recognises exactly those shapes as "about the
other instrument" and keeps every other clause/parcela reference under the
generator's own lint rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from noctusai_lib.domain.texto_ptbr import (
    brl_por_extenso,
    formatar_data_br,
    ordinal_por_extenso,
)

from app.modules.card_hub.contrato_gerador import frases as frases_contrato
from app.modules.card_hub.contrato_gerador.concordancia import Concordancia, lado, normalizar_genero
from app.modules.card_hub.contrato_gerador.dados import DadosContrato, Favorecido, Parcela, signatarios
from app.modules.card_hub.contrato_gerador.estilo import negrito
from app.modules.card_hub.contrato_gerador.numeracao import num2

#: How each style names the other instrument (corpus: house "Contrato
#: original", formal "instrumento originário").
ORIGINAL_POR_ESTILO = {"house": "do contrato original", "formal": "do instrumento originário"}


def ref_clausula_original(n: int, estilo: str) -> str:
    """"Cláusula Segunda do contrato original"."""
    return f"Cláusula {ordinal_por_extenso(n, feminino=True).title()} {ORIGINAL_POR_ESTILO[estilo]}"


def ref_parcela_original(n: int, estilo: str) -> str:
    """"Parcela 03 do contrato original"."""
    return f"Parcela {num2(n)} {ORIGINAL_POR_ESTILO[estilo]}"


def titulo_clausula_original(n: int) -> str:
    """"CLÁUSULA SEGUNDA" — the formal style's section heading cites it."""
    return f"CLÁUSULA {ordinal_por_extenso(n, feminino=True).upper()}"


def brl(valor: Decimal) -> str:
    return negrito(brl_por_extenso(valor))


@dataclass
class Secao:
    titulo_house: str
    titulo_formal: str
    paragrafos: list[str] = field(default_factory=list)
    #: Indexes of `paragrafos` that are SUB-ITEMS in the formal style — they
    #: print "N.k." there (867's "1.1." shape) and plain in the house style.
    subitens: tuple[int, ...] = ()
    #: True = an `outro` (operator text) — named in the legal review.
    livre: bool = False


def lados(d: DadosContrato) -> tuple[Concordancia, Concordancia]:
    def gen(ps):
        return [normalizar_genero(p.genero) or "m" for p in ps]

    return lado(gen(signatarios(d.vendedores)), "vendedor"), lado(gen(signatarios(d.compradores)), "comprador")


def secao_pagamento(
    alt,
    d: DadosContrato,
    parcelas: list[Parcela],
    preco: Decimal,
    *,
    estilo: str,
) -> Secao:
    V, C = lados(d)
    ref = ref_clausula_original(alt.clausula_alvo, estilo)
    favorecidos: dict[str, Favorecido] = {f.id: f for f in d.favorecidos}
    cpf_vendedor = {frases_contrato.so_digitos(p.cpf): p for p in signatarios(d.vendedores) if p.cpf}
    tem_financiamento = any(p.tipo == "financiamento" for p in parcelas)
    ref_financiamento = ", ".join(num2(i) for i, p in enumerate(parcelas, start=1) if p.tipo == "financiamento")

    paragrafos = [
        "Por força do presente Aditivo, as Partes resolvem de comum acordo alterar a forma de "
        f"pagamento estabelecida na {ref}, que passa a vigorar com a seguinte redação:"
    ]
    if alt.novo_valor is not None and d.valor_negociado is not None and alt.novo_valor != d.valor_negociado:
        paragrafos.append(
            f"O preço ajustado de {brl(d.valor_negociado)} fica alterado para {brl(preco)}, que "
            "deverá ser pago em moeda corrente nacional conforme a seguir estipulado:"
        )
    else:
        paragrafos.append(
            f"O preço de {brl(preco)} deverá ser pago em moeda corrente nacional conforme a seguir estipulado:"
        )
    ja_usados: set[str] = set()
    for i, p in enumerate(parcelas, start=1):
        fav = favorecidos.get(p.favorecido_id or "") if p.tipo in {"sinal", "intermediaria", "direta", "saldo"} else None
        texto = frases_contrato.texto_parcela(
            p,
            V=V,
            C=C,
            tem_financiamento=tem_financiamento,
            fgts=d.financiamento.fgts,
            ref_financiamento=ref_financiamento,
            favorecido=fav,
            favorecido_repetido=bool(fav and fav.id in ja_usados),
            vendedor_favorecido=cpf_vendedor.get(frases_contrato.so_digitos(fav.cpf_cnpj)) if fav else None,
            juros_am=d.termos.confissao_juros_am if p.confissao_divida else None,
        )
        paragrafos.append(f"**Parcela {num2(i)}:**{texto}")
        if fav is not None:
            ja_usados.add(fav.id)
    indice_sub = len(paragrafos)
    paragrafos.append(
        "As parcelas acima substituem integralmente o cronograma de pagamento previsto na "
        f"{ref}, permanecendo inalteradas as demais disposições dessa cláusula."
    )
    return Secao(
        titulo_house="DA ALTERAÇÃO DA FORMA DE PAGAMENTO",
        titulo_formal=f"DA ALTERAÇÃO DA {titulo_clausula_original(alt.clausula_alvo)} – DO PREÇO E FORMA DE PAGAMENTO",
        paragrafos=paragrafos,
        subitens=(indice_sub,),
    )


def secao_posse(alt, d: DadosContrato, *, estilo: str) -> Secao:
    V, C = lados(d)
    ref = ref_clausula_original(alt.clausula_alvo, estilo)
    data = formatar_data_br(alt.data)
    if alt.precaria:
        texto = (
            f"Por força do presente Aditivo, as Partes, de comum acordo, ajustam que {C.art} "
            f"**{C.NOME}** {C.pl('passará', 'passarão')} a deter a posse precária do imóvel a partir de "
            f"{data}, exclusivamente para fins de acesso ao bem, com o objetivo de realizar "
            f"{alt.finalidade.strip().rstrip('.')}."
        )
        sub = (
            "A posse precária ora ajustada não importa a transmissão da posse definitiva, que "
            f"permanece regida pela {ref}."
        )
    else:
        texto = (
            f"As Partes resolvem alterar a {ref}, que trata da posse sobre o imóvel, convencionando "
            f"que a posse será outorgada {V.pelos} **{V.NOME}** {C.aos} **{C.NOME}**, mediante a "
            f"entrega das chaves, na data de {data}."
        )
        sub = f"Permanecem inalteradas as demais disposições da {ref}."
    return Secao(
        titulo_house="DA ALTERAÇÃO DA POSSE DO IMÓVEL",
        titulo_formal=f"DA ALTERAÇÃO DA {titulo_clausula_original(alt.clausula_alvo)} – POSSE DO IMÓVEL",
        paragrafos=[texto, sub],
        subitens=(1,),
    )


def secao_comissao(alt, d: DadosContrato, *, estilo: str, com_novo_cronograma: bool) -> Secao:
    ref = ref_clausula_original(alt.clausula_alvo, estilo)
    if alt.marco == "parcela":
        alvo = (
            f"Parcela {num2(alt.parcela_numero)}"
            if com_novo_cronograma
            else ref_parcela_original(alt.parcela_numero, estilo)
        )
        quando = f"por ocasião da quitação integral da {alvo}"
    elif alt.marco == "data":
        quando = f"em {formatar_data_br(alt.data)}"
    else:
        quando = "na data da assinatura do Contrato de Financiamento Imobiliário"
    ordinal = ordinal_por_extenso(alt.parcela_corretagem, feminino=True)
    return Secao(
        titulo_house="DA COMISSÃO",
        titulo_formal=f"DA ALTERAÇÃO DA {titulo_clausula_original(alt.clausula_alvo)} – INTERMEDIAÇÃO",
        paragrafos=[
            f"Fica estabelecido que o pagamento da {ordinal} parcela da corretagem, prevista na "
            f"{ref}, será realizado {quando}.",
            "Permanecem inalteradas as demais condições da corretagem, inclusive valores e favorecidos.",
        ],
        subitens=(1,),
    )


def secao_outro(alt, *, estilo: str) -> Secao:
    titulo = alt.titulo.strip().upper()
    formal = (
        f"DA ALTERAÇÃO DA {titulo_clausula_original(alt.clausula_alvo)} – {titulo}"
        if alt.clausula_alvo
        else titulo
    )
    paragrafos = [linha.strip() for linha in alt.texto.splitlines() if linha.strip()]
    return Secao(titulo_house=titulo, titulo_formal=formal, paragrafos=paragrafos, livre=True)


def secoes(
    alteracoes: list,
    d: DadosContrato,
    parcelas: list[Parcela],
    preco: Optional[Decimal],
    *,
    estilo: str,
) -> list[Secao]:
    """Sections in a fixed order (pagamento → posse → comissão → outro), the
    corpus' own order (827: prazo then posse; 867: parcela, documentação,
    posse, intermediação), so the same amendments always print alike."""
    ordem = {"pagamento": 0, "posse": 1, "comissao": 2, "outro": 3}
    com_cronograma = any(a.tipo == "pagamento" for a in alteracoes)
    saida: list[Secao] = []
    for alt in sorted(alteracoes, key=lambda a: ordem[a.tipo]):
        if alt.tipo == "pagamento":
            saida.append(secao_pagamento(alt, d, parcelas, preco, estilo=estilo))  # type: ignore[arg-type] — gated
        elif alt.tipo == "posse":
            saida.append(secao_posse(alt, d, estilo=estilo))
        elif alt.tipo == "comissao":
            saida.append(secao_comissao(alt, d, estilo=estilo, com_novo_cronograma=com_cronograma))
        else:
            saida.append(secao_outro(alt, estilo=estilo))
    return saida


def ordinal_aditivo(n: int) -> str:
    """"PRIMEIRO", "SEGUNDO", … (masculine: "o Primeiro Termo Aditivo")."""
    return ordinal_por_extenso(n).upper()


def data_original_texto(d: date) -> str:
    return formatar_data_br(d)


__all__ = [
    "ORIGINAL_POR_ESTILO",
    "Secao",
    "brl",
    "lados",
    "data_original_texto",
    "ordinal_aditivo",
    "ref_clausula_original",
    "ref_parcela_original",
    "secao_comissao",
    "secao_outro",
    "secao_pagamento",
    "secao_posse",
    "secoes",
    "titulo_clausula_original",
]
