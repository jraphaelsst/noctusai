"""The aditivo's readiness gate — the SAME refusal shape as the contract's
(`contrato_gerador.derivacao.Avaliacao`: pronto / faltando / bloqueios /
avisos), so the FE renders it with the component it already has.

What it REUSES rather than re-states:
- `derivacao._partes` — every party's qualification (an aditivo re-qualifies
  every party, corpus 5/5), cônjuge reciprocity, CPF validity;
- `derivacao._negociacao` — the restated schedule's sum-equals-price,
  one-sinal, vencimentos-in-order, favorecido and confissão rules, run over a
  copy of the original's data whose `parcelas` are the aditivo's and whose
  price is the amended one. Its posse sub-check (`_posse`, about the
  ORIGINAL's posse terms) is filtered out by name — a posse change is its
  own amendment here.

🔴 Both are private names of `derivacao`; this module is a sibling consumer.
The public seam that would remove the leading underscore is reported in this
slice's delivery note — contrato_gerador/ is being changed by two other
slices, so it was not edited here.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Optional

from noctusai_lib.integrations.documents import has_raw_markup
from noctusai_lib.integrations.documents.cpf import is_valid as cpf_valido

from app.modules.card_hub.contrato_aditivo.dados import DadosAditivo
from app.modules.card_hub.contrato_gerador.dados import DadosContrato, Parcela
from app.modules.card_hub.contrato_gerador.derivacao import (
    Avaliacao,
    Destinos,
    _negociacao,
    _partes,
    derivar_switches,
    resolver_endereco_posse,
)
from app.modules.card_hub.contrato_gerador.numeracao import numerar_clausulas
from app.modules.card_hub.contrato_gerador.politica import MIN_TESTEMUNHAS, Politica

#: `derivacao._posse`'s outputs — about the ORIGINAL's posse terms, never the
#: aditivo's; dropped from the scratch payment evaluation.
_CAMPOS_POSSE_ORIGINAL = frozenset({"negociacao.posse_prazo_dias", "negociacao.posse_marco"})
_CODIGOS_POSSE_ORIGINAL = frozenset({"POSSE_MARCO_INVALIDO", "POSSE_MARCO_PARCELA_DESCONHECIDA"})

#: The original-contract clause each amendment tipo is ABOUT — checked (as an
#: aviso) against a GENERATED original's own numbering.
_CLAUSULA_DO_TIPO = {"pagamento": "preco", "posse": "posse", "comissao": "intermediacao"}

#: Prefixes of `_negociacao` faltas that describe the SCHEDULE (now the
#: aditivo's) — re-pointed at the aditivo; a favorecido's bank data still
#: lives on the negociação screen and keeps its own destino.
_PREFIXOS_DO_CRONOGRAMA = ("negociacao.parcela.", "negociacao.parcelas", "negociacao.parcela_sinal")


def alvo(aditivo_id: str) -> str:
    """DOM id of the aditivo's editor on the card's contratos screen."""
    return f"aditivo-{aditivo_id}"


def preco_aditivo(d: DadosContrato, ad: DadosAditivo):
    """The price the restated schedule must sum to: the amended one when the
    payment amendment changes it, else the original's."""
    pag = ad.pagamento
    if pag is not None and pag.novo_valor is not None:
        return pag.novo_valor
    return d.valor_negociado


def _original(av: Avaliacao, ad: DadosAditivo, assinatura: date) -> None:
    if ad.original_status == "cancelado":
        av.bloqueia("ORIGINAL_CANCELADO", "O contrato original está cancelado; não admite aditivo.")
    elif ad.original_status != "assinado" and ad.original_assinatura_data is None:
        av.bloqueia(
            "ORIGINAL_NAO_ASSINADO",
            "O contrato original ainda não foi assinado — um aditivo altera um instrumento firmado.",
        )
    if ad.original_assinatura_data is None:
        av.falta(
            "contrato.assinatura_data",
            "Data de assinatura do contrato original (o aditivo a cita)",
            "contrato",
        )
    elif assinatura < ad.original_assinatura_data:
        av.bloqueia(
            "ADITIVO_ANTERIOR_AO_ORIGINAL",
            "A data do aditivo é anterior à assinatura do contrato original.",
        )
    if ad.status == "cancelado":
        av.bloqueia("ADITIVO_CANCELADO", "Este aditivo está cancelado.")


def _imovel(av: Avaliacao, d: DadosContrato) -> None:
    im = d.imovel
    if im is None:
        av.falta("negociacao.imovel", "Imóvel negociado no card", "negociacao")
        return
    for valor, campo, rotulo in (
        (im.endereco.cidade, "cidade", "Cidade do imóvel"),
        (im.endereco.uf, "uf", "UF do imóvel"),
        (im.numero_matricula, "numero_matricula", "Número da matrícula"),
        (im.numero_registro_imoveis, "numero_registro_imoveis", "Cartório de registro de imóveis"),
        (im.inscricao_municipal, "inscricao_municipal", "Inscrição municipal (cadastro na prefeitura)"),
    ):
        if not valor:
            av.falta(f"imovel.{campo}", rotulo, "imovel")
    texto = d.matricula.descricao_imovel_texto or d.matricula.texto
    if not (texto or "").strip():
        av.falta("matricula.atos", "Descrição do imóvel na matrícula (atos selecionados)", "matricula")
        return
    if has_raw_markup(texto):
        av.bloqueia(
            "MATRICULA_COM_MARCACAO_BRUTA",
            "O texto da matrícula contém marcação de formatação bruta (** ou <u>).",
        )
    if resolver_endereco_posse(im.endereco_registro_texto, texto, d.matricula.texto) is None:
        av.falta(
            "imovel.endereco_registro_texto",
            "Endereço do imóvel conforme a matrícula (título do aditivo)",
            "imovel",
        )


def _assinatura(av: Avaliacao, d: DadosContrato, ad: DadosAditivo) -> None:
    if not d.imobiliaria.endereco.cidade:
        av.falta(
            "imobiliaria.endereco_cidade",
            "Cidade da imobiliária (local de assinatura)",
            "imobiliaria",
        )
    if len(d.testemunhas) < MIN_TESTEMUNHAS:
        av.falta(
            "imobiliaria.testemunhas",
            f"Ao menos {MIN_TESTEMUNHAS} testemunhas selecionadas no contrato",
            "contrato",
        )
    for i, t in enumerate(d.testemunhas, start=1):
        if not t.nome:
            av.falta(f"imobiliaria.testemunha.{i}.nome", f"Nome da testemunha {i}", "imobiliaria")
        if not t.cpf:
            av.falta(f"imobiliaria.testemunha.{i}.cpf", f"CPF da testemunha {i}", "imobiliaria")
        elif not cpf_valido(t.cpf):
            av.bloqueia("CPF_INVALIDO", f"O CPF da testemunha {i} não confere (dígitos verificadores).")
        if not t.email and ad.modalidade_assinatura != "fisica":
            av.falta(f"imobiliaria.testemunha.{i}.email", f"E-mail da testemunha {i}", "imobiliaria")


def _cronograma(
    av: Avaliacao,
    d: DadosContrato,
    ad: DadosAditivo,
    politica: Politica,
    assinatura: date,
    referencia: date,
) -> None:
    """The restated schedule through the generator's OWN payment gate."""
    pag = ad.pagamento
    if pag is None:
        if ad.parcelas:
            av.bloqueia(
                "PARCELAS_SEM_ALTERACAO_DE_PAGAMENTO",
                "O aditivo tem parcelas, mas nenhuma alteração de pagamento que as use.",
            )
        return
    if not ad.parcelas:
        av.falta("aditivo.parcelas", "Novas parcelas do preço (alteração de pagamento)", "contrato", alvo=alvo(ad.aditivo_id))
        return
    preco = preco_aditivo(d, ad)
    if preco is None:
        av.falta("negociacao.valor_negociado", "Valor negociado do contrato original", "negociacao")
        return
    if pag.novo_valor is not None and d.valor_negociado is not None and pag.novo_valor == d.valor_negociado:
        av.avisa("NOVO_VALOR_IGUAL_AO_ORIGINAL", "O novo preço informado é igual ao do contrato original.")

    copia = replace(d, parcelas=list(ad.parcelas), valor_negociado=preco)
    rascunho = Avaliacao(destinos=av.destinos)
    _negociacao(rascunho, copia, derivar_switches(copia, politica, referencia), assinatura)

    for f in rascunho.faltando:
        if f["campo"] in _CAMPOS_POSSE_ORIGINAL:
            continue
        if f["campo"].startswith(_PREFIXOS_DO_CRONOGRAMA):
            av.falta(
                "aditivo." + f["campo"].removeprefix("negociacao."),
                f"{f['rotulo']} (aditivo)",
                "contrato",
                alvo=alvo(ad.aditivo_id),
            )
        else:
            av.faltando.append(f)
    for b in rascunho.bloqueios:
        if b["codigo"] not in _CODIGOS_POSSE_ORIGINAL:
            av.bloqueia(b["codigo"], b["mensagem"])
    for a in rascunho.avisos:
        av.avisa(a["codigo"], a["mensagem"])


def _alteracoes(
    av: Avaliacao,
    d: DadosContrato,
    ad: DadosAditivo,
    politica: Politica,
    assinatura: date,
    referencia: date,
) -> None:
    if not ad.alteracoes:
        av.falta(
            "aditivo.alteracoes",
            "Ao menos uma alteração (pagamento, posse, comissão ou outra)",
            "contrato",
            alvo=alvo(ad.aditivo_id),
        )
        return

    if ad.original_origem == "gerado":
        # A GENERATED original's clause numbers are computable — an
        # amendment aimed at the wrong clause is flagged (aviso: the office
        # may have edited the signed copy by hand).
        numeros = {c.chave: c.n for c in numerar_clausulas(derivar_switches(d, politica, referencia)).values()}
        for a in ad.alteracoes:
            chave = _CLAUSULA_DO_TIPO.get(a.tipo)
            if chave and chave in numeros and a.clausula_alvo != numeros[chave]:
                av.avisa(
                    "CLAUSULA_ALVO_DIVERGENTE",
                    f"A alteração de {a.tipo} cita a cláusula {a.clausula_alvo}, mas no contrato "
                    f"original gerado esse assunto é a cláusula {numeros[chave]}.",
                )

    n_novas = len(ad.parcelas)
    for a in ad.alteracoes_do_tipo("posse"):
        if a.data < assinatura:
            av.avisa("POSSE_DATA_ANTERIOR_AO_ADITIVO", "A data da posse é anterior à data do aditivo.")
    for a in ad.alteracoes_do_tipo("comissao"):
        if not d.intermediarios:
            av.bloqueia(
                "COMISSAO_SEM_INTERMEDIACAO",
                "O contrato original não tem intermediação; não há comissão a alterar.",
            )
        if a.marco == "parcela":
            limite = n_novas if ad.pagamento is not None else len(d.parcelas)
            if a.parcela_numero > limite:
                av.bloqueia(
                    "COMISSAO_PARCELA_INEXISTENTE",
                    f"A alteração de comissão cita a Parcela {a.parcela_numero:02d}, que não existe "
                    + ("no novo cronograma." if ad.pagamento is not None else "no contrato original."),
                )
        if a.marco == "financiamento" and not any(
            p.tipo == "financiamento" for p in (ad.parcelas if ad.pagamento is not None else d.parcelas)
        ):
            av.bloqueia(
                "COMISSAO_SEM_FINANCIAMENTO",
                "A comissão foi vinculada ao financiamento, mas não há parcela de financiamento.",
            )
    for i, a in enumerate(ad.alteracoes_do_tipo("outro"), start=1):
        if has_raw_markup(a.titulo) or has_raw_markup(a.texto):
            av.bloqueia(
                "OUTRO_COM_MARCACAO",
                f"A cláusula livre {i} contém marcação de formatação (** ou <u>).",
            )
        av.avisa(
            "OUTRO_EXIGE_REVISAO_JURIDICA",
            f"A cláusula livre '{a.titulo}' é texto do operador — sairá marcada para a revisão jurídica.",
        )


def avaliar(
    d: DadosContrato,
    ad: DadosAditivo,
    politica: Politica,
    assinatura: date,
    referencia: Optional[date] = None,
) -> Avaliacao:
    referencia = referencia or assinatura
    av = Avaliacao(
        destinos=Destinos(
            cliente_id=d.cliente_id,
            contrato_id=d.contrato_id,
            imovel_codigo=d.imovel.codigo if d.imovel else None,
        )
    )
    # The aditivo's own modalidade decides the e-mail avisos `_partes` emits.
    _original(av, ad, assinatura)
    _partes(av, replace(d, modalidade_assinatura=ad.modalidade_assinatura))
    _imovel(av, d)
    _assinatura(av, d, ad)
    _alteracoes(av, d, ad, politica, assinatura, referencia)
    _cronograma(av, d, ad, politica, assinatura, referencia)
    return av


def parcelas_ordenadas(ad: DadosAditivo) -> list[Parcela]:
    return sorted(ad.parcelas, key=lambda p: p.ordem)


__all__ = ["alvo", "avaliar", "parcelas_ordenadas", "preco_aditivo"]
